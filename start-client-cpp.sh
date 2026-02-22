#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_CPP_DIR="$SCRIPT_DIR/client-cpp"
BUILD_DIR="$CLIENT_CPP_DIR/build"
BINARY="$BUILD_DIR/remote-desktop-client"
CONFIG_FILE="${1:-$SCRIPT_DIR/client/config.json}"
FORCE_REBUILD="${RC_FORCE_REBUILD:-0}"
DISPLAY_PROBE_FILE="/tmp/rc-display-probe.png"

# 默认策略：优先硬件编码，无法使用时回退到兼容软件编码。
: "${RC_VIDEO_CODEC:=auto}"
: "${RC_PREFER_HW_ENCODER:=1}"
export RC_VIDEO_CODEC
export RC_PREFER_HW_ENCODER

fix_nvenc_caps_permissions() {
    local cap1="/dev/nvidia-caps/nvidia-cap1"
    local cap2="/dev/nvidia-caps/nvidia-cap2"

    if [ ! -e "$cap1" ]; then
        return
    fi

    if [ -r "$cap1" ]; then
        return
    fi

    # Some sandboxed shells may not expose /dev/nvidia-caps readability accurately.
    # Trust real encoder probe first to avoid false alarms.
    if command -v gst-inspect-1.0 >/dev/null 2>&1; then
        if gst-inspect-1.0 nvh264enc >/dev/null 2>&1; then
            echo "检测到 nvh264enc 可用，跳过 nvidia-cap 权限告警"
            return
        fi
    fi

    echo "检测到 NVENC 设备权限不足: $cap1 当前用户不可读"
    if [ "${RC_AUTO_FIX_NVENC_CAPS:-1}" = "1" ] && command -v sudo >/dev/null 2>&1; then
        if sudo -n true >/dev/null 2>&1; then
            sudo chgrp video "$cap1" "$cap2" >/dev/null 2>&1 || true
            sudo chmod 660 "$cap1" "$cap2" >/dev/null 2>&1 || true
        fi
    fi

    if [ ! -r "$cap1" ]; then
        echo "警告: NVENC 仍不可用。请执行以下命令后重试:"
        echo "  sudo chgrp video /dev/nvidia-caps/nvidia-cap1 /dev/nvidia-caps/nvidia-cap2"
        echo "  sudo chmod 660 /dev/nvidia-caps/nvidia-cap1 /dev/nvidia-caps/nvidia-cap2"
    else
        echo "已修复 NVENC 设备权限: $cap1"
    fi
}

# 检查配置文件
if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$SCRIPT_DIR/client/config.example.json" ]; then
        echo "配置文件不存在，从示例创建..."
        cp "$SCRIPT_DIR/client/config.example.json" "$SCRIPT_DIR/client/config.json"
        CONFIG_FILE="$SCRIPT_DIR/client/config.json"
        echo "已创建配置文件: $CONFIG_FILE，请根据需要修改后重新运行"
        exit 1
    else
        echo "错误: 找不到配置文件"
        exit 1
    fi
fi

# 检查二进制，必要时编译
NEED_BUILD=0
if [ "$FORCE_REBUILD" = "1" ] || [ ! -f "$BINARY" ] || [ ! -d "$BUILD_DIR" ]; then
    NEED_BUILD=1
else
    if [ "$CLIENT_CPP_DIR/CMakeLists.txt" -nt "$BINARY" ]; then
        NEED_BUILD=1
    elif find "$CLIENT_CPP_DIR/src" -type f \( -name "*.cpp" -o -name "*.h" \) -newer "$BINARY" | head -n 1 | grep -q .; then
        NEED_BUILD=1
    fi
fi

if [ "$NEED_BUILD" = "1" ]; then
    echo "检测到构建产物缺失或源码已更新，开始编译..."
    mkdir -p "$BUILD_DIR"
    cmake -S "$CLIENT_CPP_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
    make -C "$BUILD_DIR" -j"$(nproc)"
    echo "编译完成"
fi

# 设置 X11 环境
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
    if ls /tmp/.X11-unix/X* >/dev/null 2>&1; then
        if [ -z "${DISPLAY:-}" ] || [[ "${DISPLAY}" == localhost:* ]]; then
            FIRST_X_SOCKET="$(ls /tmp/.X11-unix/X* 2>/dev/null | head -n 1)"
            if [ -n "${FIRST_X_SOCKET}" ]; then
                export DISPLAY=":${FIRST_X_SOCKET##*X}"
            fi
        fi

        if [ -z "${XAUTHORITY:-}" ]; then
            if [ -f "/run/user/$(id -u)/gdm/Xauthority" ]; then
                export XAUTHORITY="/run/user/$(id -u)/gdm/Xauthority"
            elif [ -f "${HOME}/.Xauthority" ]; then
                export XAUTHORITY="${HOME}/.Xauthority"
            fi
        fi
    fi
fi

probe_display_mean() {
    local disp="$1"
    rm -f "$DISPLAY_PROBE_FILE"

    if ! DISPLAY="$disp" XAUTHORITY="${XAUTHORITY:-}" timeout 8s \
        gst-launch-1.0 -q ximagesrc use-damage=0 num-buffers=1 \
        ! videoconvert ! videoscale ! video/x-raw,width=320,height=180 \
        ! pngenc ! filesink location="$DISPLAY_PROBE_FILE" >/dev/null 2>&1; then
        echo ""
        return
    fi

    if [ ! -s "$DISPLAY_PROBE_FILE" ]; then
        echo ""
        return
    fi

    if command -v convert >/dev/null 2>&1; then
        convert "$DISPLAY_PROBE_FILE" -colorspace Gray -format "%[fx:mean]" info: 2>/dev/null || true
        return
    fi

    # Fallback when imagemagick is unavailable: use file size as weak signal.
    local size
    size="$(stat -c%s "$DISPLAY_PROBE_FILE" 2>/dev/null || echo 0)"
    if [ "$size" -gt 10000 ]; then
        echo "0.02"
    else
        echo "0"
    fi
}

if [ -n "${XAUTHORITY:-}" ] && ls /tmp/.X11-unix/X* >/dev/null 2>&1; then
    BEST_DISPLAY=""
    BEST_MEAN="-1"
    for x_socket in /tmp/.X11-unix/X*; do
        disp=":${x_socket##*X}"
        mean="$(probe_display_mean "$disp")"
        if [ -z "$mean" ]; then
            echo "显示探测: ${disp} -> 无法抓图"
            continue
        fi
        echo "显示探测: ${disp} -> mean=${mean}"
        if awk -v a="$mean" -v b="$BEST_MEAN" 'BEGIN { exit !(a > b) }'; then
            BEST_MEAN="$mean"
            BEST_DISPLAY="$disp"
        fi
    done

    if [ -n "$BEST_DISPLAY" ]; then
        export DISPLAY="$BEST_DISPLAY"
        echo "自动选择显示: DISPLAY=$DISPLAY (mean=$BEST_MEAN)"
        if awk -v m="$BEST_MEAN" 'BEGIN { exit !(m < 0.01) }'; then
            echo "警告: 捕获源画面接近全黑，可能处于锁屏/黑屏状态"
        fi
    fi
fi

# 尽量避免系统节能导致的黑屏捕获
if [ -n "${DISPLAY:-}" ] && [ -n "${XAUTHORITY:-}" ] && command -v xset >/dev/null 2>&1; then
    DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" xset s off -dpms s noblank >/dev/null 2>&1 || true
fi

fix_nvenc_caps_permissions

# 对本地开发环境做后端健康等待，避免 client 先启动导致直接退出
SERVER_URL_RAW="$(sed -n 's/.*"server_url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$CONFIG_FILE" | head -n 1)"
SERVER_URL="${SERVER_URL_RAW}"
SERVER_URL="${SERVER_URL/http:\/\/localhost/http:\/\/127.0.0.1}"
SERVER_URL="${SERVER_URL/https:\/\/localhost/https:\/\/127.0.0.1}"
HEALTH_URL="${SERVER_URL%/}/health"

if [[ "$SERVER_URL" == http://127.0.0.1* ]] || [[ "$SERVER_URL" == http://localhost* ]]; then
    echo "等待后端就绪: $HEALTH_URL"
    READY=0
    for i in $(seq 1 30); do
        if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
            READY=1
            break
        fi
        sleep 1
    done
    if [ "$READY" != "1" ]; then
        echo "警告: 后端健康检查超时，继续启动 client-cpp（可能会连接失败）"
    fi
fi

echo "显示环境: DISPLAY=${DISPLAY:-<unset>} XAUTHORITY=${XAUTHORITY:-<unset>}"
echo "编码策略: RC_VIDEO_CODEC=${RC_VIDEO_CODEC} RC_PREFER_HW_ENCODER=${RC_PREFER_HW_ENCODER} RC_VIDEO_ENCODER=${RC_VIDEO_ENCODER:-<unset>}"
echo "启动 C++ 客户端，配置文件: $CONFIG_FILE"

exec "$BINARY" "$CONFIG_FILE"
