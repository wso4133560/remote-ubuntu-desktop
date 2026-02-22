#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/client"
CONFIG_FILE="${1:-$CLIENT_DIR/config.json}"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -f "$CONFIG_FILE" ]; then
    if [ -f "$CLIENT_DIR/config.example.json" ]; then
        echo "配置文件不存在，从示例创建..."
        cp "$CLIENT_DIR/config.example.json" "$CLIENT_DIR/config.json"
        CONFIG_FILE="$CLIENT_DIR/config.json"
        echo "已创建配置文件: $CONFIG_FILE"
        echo "请根据需要修改配置后重新运行"
        exit 1
    else
        echo "错误: 找不到配置文件"
        exit 1
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "错误: 未找到虚拟环境 $VENV_DIR"
    echo "请先在项目根目录创建并安装依赖：python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "激活虚拟环境..."
source "$VENV_DIR/bin/activate"
export PYTHONPATH="${PYTHONPATH}:$SCRIPT_DIR"

# 在 SSH/无 WAYLAND 的场景下，优先使用本机 X11 display，避免 DISPLAY=localhost:xx 导致抓屏失败
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
    if ls /tmp/.X11-unix/X* >/dev/null 2>&1; then
        if [ -z "${DISPLAY:-}" ] || [[ "${DISPLAY}" == localhost:* ]]; then
            FIRST_X_SOCKET="$(ls /tmp/.X11-unix/X* 2>/dev/null | head -n 1)"
            if [ -n "${FIRST_X_SOCKET}" ]; then
                DISPLAY_NUM="${FIRST_X_SOCKET##*X}"
                export DISPLAY=":${DISPLAY_NUM}"
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
echo "显示环境: DISPLAY=${DISPLAY:-<unset>} XAUTHORITY=${XAUTHORITY:-<unset>}"

echo "启动客户端..."
echo "使用配置文件: $CONFIG_FILE"
cd "$SCRIPT_DIR"
python -m client.main "$CONFIG_FILE"
