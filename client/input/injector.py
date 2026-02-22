"""输入注入基础框架"""
from __future__ import annotations

import os
import shutil
import subprocess
from importlib.util import find_spec
from typing import Optional

from .stuck_key_recovery import StuckKeyRecovery


class InputInjector:
    """输入注入管理器"""

    def __init__(self):
        self.compositor_type: Optional[str] = None
        self.injection_method: Optional[str] = None
        self.initialized = False
        self.actual_injector = None
        self.stuck_key_recovery: Optional[StuckKeyRecovery] = None

    async def detect_compositor(self) -> str:
        """检测 compositor 类型"""
        try:
            if self._is_process_running("gnome-shell"):
                self.compositor_type = "gnome"
                self.injection_method = "gnome-remote-desktop"
                return "GNOME"

            if self._is_process_running("sway") or self._is_process_running("Hyprland"):
                self.compositor_type = "wlroots"
                self.injection_method = "wlroots-protocols"
                return "wlroots"

            if self._can_try_x11():
                self.compositor_type = "x11"
                self.injection_method = "x11-xtest"
                return "X11"

            return "Unknown"

        except Exception as e:
            print(f"Error detecting compositor: {e}")
            return "Error"

    def check_dependencies(self) -> dict:
        """检查依赖项"""
        dependencies = {
            "python-gi": self._module_available("gi"),
            "python-dbus": self._module_available("dbus"),
            "ydotool": shutil.which("ydotool") is not None,
            "python-xlib": self._module_available("Xlib"),
            "x11-display": self._can_try_x11(),
        }

        return dependencies

    async def initialize(self) -> bool:
        """初始化输入注入"""
        compositor = await self.detect_compositor()
        print(f"Detected compositor for input: {compositor}")

        dependencies = self.check_dependencies()
        print("Input injection dependencies:")
        for dep, available in dependencies.items():
            status = "✓" if available else "✗"
            print(f"  {status} {dep}")

        candidates = []
        if self.injection_method == "gnome-remote-desktop":
            candidates.append(("gnome-remote-desktop", self._init_gnome_injection))
            candidates.append(("x11-xtest", self._init_x11_injection))
        elif self.injection_method == "wlroots-protocols":
            candidates.append(("wlroots-protocols", self._init_wlroots_injection))
            candidates.append(("x11-xtest", self._init_x11_injection))
        else:
            candidates.append(("x11-xtest", self._init_x11_injection))

        success = False
        for method, initializer in candidates:
            self.injection_method = method
            success = await initializer()
            if success:
                break

        if success:
            if not hasattr(self.actual_injector, "inject_key_by_js_code"):
                self.stuck_key_recovery = StuckKeyRecovery(self.actual_injector)
                await self.stuck_key_recovery.start_monitoring()
            self.initialized = True
            print(f"Input injection initialized with method: {self.injection_method}")
            return True

        print("No supported injection method available")
        return False

    async def _init_gnome_injection(self) -> bool:
        """初始化 GNOME Remote Desktop 注入"""
        print("Initializing GNOME Remote Desktop injection...")
        try:
            from .gnome_injector import GNOMERemoteDesktopInjector
            self.actual_injector = GNOMERemoteDesktopInjector()
            return await self.actual_injector.initialize()
        except Exception as e:
            print(f"Failed to initialize GNOME injector: {e}")
            return False

    async def _init_wlroots_injection(self) -> bool:
        """初始化 wlroots 协议注入"""
        print("Initializing wlroots protocol injection...")
        try:
            from .wlroots_injector import WlrootsInjector
            self.actual_injector = WlrootsInjector()
            return await self.actual_injector.initialize()
        except Exception as e:
            print(f"Failed to initialize wlroots injector: {e}")
            return False

    async def _init_x11_injection(self) -> bool:
        """初始化 X11 XTest 注入"""
        print("Initializing X11 XTest injection...")
        try:
            from .x11_injector import X11Injector
            self.actual_injector = X11Injector()
            return await self.actual_injector.initialize()
        except Exception as e:
            print(f"Failed to initialize X11 injector: {e}")
            return False

    def _module_available(self, module_name: str) -> bool:
        return find_spec(module_name) is not None

    def _is_process_running(self, process_name: str) -> bool:
        result = subprocess.run(["pgrep", "-x", process_name], capture_output=True)
        return result.returncode == 0

    def _can_try_x11(self) -> bool:
        if os.environ.get("DISPLAY"):
            return True
        x11_dir = "/tmp/.X11-unix"
        if os.path.isdir(x11_dir):
            for entry in os.listdir(x11_dir):
                if entry.startswith("X"):
                    return True
        return False

    async def inject_mouse_move(self, x: float, y: float):
        """注入鼠标移动事件"""
        if not self.initialized or not self.actual_injector:
            return

        await self.actual_injector.inject_mouse_move(x, y)

    async def inject_mouse_button(self, button: int, pressed: bool):
        """注入鼠标按钮事件"""
        if not self.initialized or not self.actual_injector:
            return

        await self.actual_injector.inject_mouse_button(button, pressed)

    async def inject_key(self, key_code: str, pressed: bool):
        """注入键盘事件"""
        if not self.initialized or not self.actual_injector:
            return

        if hasattr(self.actual_injector, "inject_key_by_js_code"):
            await self.actual_injector.inject_key_by_js_code(key_code, pressed)
            return

        evdev_keycode = KEYCODE_MAP.get(key_code)
        if evdev_keycode is None:
            print(f"Unknown key code: {key_code}")
            return

        if self.stuck_key_recovery:
            if pressed:
                self.stuck_key_recovery.record_key_press(evdev_keycode)
            else:
                self.stuck_key_recovery.record_key_release(evdev_keycode)

        await self.actual_injector.inject_key(evdev_keycode, pressed)

    async def cleanup(self):
        """清理资源"""
        if self.stuck_key_recovery:
            await self.stuck_key_recovery.stop_monitoring()

        if self.actual_injector:
            await self.actual_injector.cleanup()

        self.actual_injector = None
        self.stuck_key_recovery = None
        self.initialized = False


# 键盘映射表（JavaScript code -> Linux evdev keycode）
KEYCODE_MAP = {
    "KeyA": 30, "KeyB": 48, "KeyC": 46, "KeyD": 32, "KeyE": 18,
    "KeyF": 33, "KeyG": 34, "KeyH": 35, "KeyI": 23, "KeyJ": 36,
    "KeyK": 37, "KeyL": 38, "KeyM": 50, "KeyN": 49, "KeyO": 24,
    "KeyP": 25, "KeyQ": 16, "KeyR": 19, "KeyS": 31, "KeyT": 20,
    "KeyU": 22, "KeyV": 47, "KeyW": 17, "KeyX": 45, "KeyY": 21,
    "KeyZ": 44,
    "Digit0": 11, "Digit1": 2, "Digit2": 3, "Digit3": 4, "Digit4": 5,
    "Digit5": 6, "Digit6": 7, "Digit7": 8, "Digit8": 9, "Digit9": 10,
    "Enter": 28, "Escape": 1, "Backspace": 14, "Tab": 15, "Space": 57,
    "ShiftLeft": 42, "ShiftRight": 54, "ControlLeft": 29, "ControlRight": 97,
    "AltLeft": 56, "AltRight": 100,
    "ArrowUp": 103, "ArrowDown": 108, "ArrowLeft": 105, "ArrowRight": 106,
}


def map_keycode(js_code: str) -> Optional[int]:
    """映射 JavaScript keycode 到 Linux evdev keycode"""
    return KEYCODE_MAP.get(js_code)
