"""X11 输入注入实现 (通过 XTest)。"""
from __future__ import annotations

import os
from typing import Optional

from Xlib import X, XK, display
from Xlib.ext.xtest import fake_input


class X11Injector:
    """X11 输入注入器。"""

    def __init__(self):
        self.display = None
        self.screen_width = 1
        self.screen_height = 1

    async def initialize(self) -> bool:
        """初始化 X11 连接。"""
        try:
            display_name = os.environ.get("DISPLAY")
            self.display = display.Display(display_name)
            screen = self.display.screen()
            self.screen_width = max(1, int(screen.width_in_pixels))
            self.screen_height = max(1, int(screen.height_in_pixels))
            print(
                f"X11 injector connected: DISPLAY={display_name} "
                f"resolution={self.screen_width}x{self.screen_height}"
            )
            return True
        except Exception as e:
            print(f"Failed to connect X11 display for input injection: {e}")
            self.display = None
            return False

    def _normalize_to_pixels(self, x: float, y: float) -> tuple[int, int]:
        """将前端归一化坐标转换为屏幕像素坐标。"""
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            px = int(round(x * (self.screen_width - 1)))
            py = int(round(y * (self.screen_height - 1)))
        else:
            px = int(round(x))
            py = int(round(y))

        px = max(0, min(self.screen_width - 1, px))
        py = max(0, min(self.screen_height - 1, py))
        return px, py

    async def inject_mouse_move(self, x: float, y: float):
        """注入鼠标移动。"""
        if not self.display:
            return

        px, py = self._normalize_to_pixels(float(x), float(y))
        self.display.screen().root.warp_pointer(px, py)
        self.display.sync()

    async def inject_mouse_button(self, button: int, pressed: bool):
        """注入鼠标按键。"""
        if not self.display:
            return

        button_map = {0: 1, 1: 2, 2: 3}
        x11_button = button_map.get(button, 1)
        event_type = X.ButtonPress if pressed else X.ButtonRelease
        fake_input(self.display, event_type, detail=x11_button)
        self.display.sync()

    def _js_code_to_keysym_name(self, key_code: str) -> Optional[str]:
        if key_code.startswith("Key") and len(key_code) == 4:
            return key_code[-1].lower()

        if key_code.startswith("Digit") and len(key_code) == 6:
            return key_code[-1]

        special = {
            "Enter": "Return",
            "Escape": "Escape",
            "Backspace": "BackSpace",
            "Tab": "Tab",
            "Space": "space",
            "Backquote": "grave",
            "Minus": "minus",
            "Equal": "equal",
            "BracketLeft": "bracketleft",
            "BracketRight": "bracketright",
            "Backslash": "backslash",
            "Semicolon": "semicolon",
            "Quote": "apostrophe",
            "Comma": "comma",
            "Period": "period",
            "Slash": "slash",
            "IntlBackslash": "backslash",
            "ArrowUp": "Up",
            "ArrowDown": "Down",
            "ArrowLeft": "Left",
            "ArrowRight": "Right",
            "ShiftLeft": "Shift_L",
            "ShiftRight": "Shift_R",
            "ControlLeft": "Control_L",
            "ControlRight": "Control_R",
            "AltLeft": "Alt_L",
            "AltRight": "Alt_R",
            "MetaLeft": "Super_L",
            "MetaRight": "Super_R",
            "CapsLock": "Caps_Lock",
            "Delete": "Delete",
            "Home": "Home",
            "End": "End",
            "PageUp": "Page_Up",
            "PageDown": "Page_Down",
            "Insert": "Insert",
            "Numpad0": "KP_0",
            "Numpad1": "KP_1",
            "Numpad2": "KP_2",
            "Numpad3": "KP_3",
            "Numpad4": "KP_4",
            "Numpad5": "KP_5",
            "Numpad6": "KP_6",
            "Numpad7": "KP_7",
            "Numpad8": "KP_8",
            "Numpad9": "KP_9",
            "NumpadDecimal": "KP_Decimal",
            "NumpadAdd": "KP_Add",
            "NumpadSubtract": "KP_Subtract",
            "NumpadMultiply": "KP_Multiply",
            "NumpadDivide": "KP_Divide",
            "NumpadEnter": "KP_Enter",
        }
        if key_code in special:
            return special[key_code]

        if key_code.startswith("F") and key_code[1:].isdigit():
            return key_code

        return None

    async def inject_key_by_js_code(self, key_code: str, pressed: bool):
        """按 JS `KeyboardEvent.code` 注入键盘事件。"""
        if not self.display:
            return

        keysym_name = self._js_code_to_keysym_name(key_code)
        if not keysym_name:
            print(f"Unknown key code for X11 injector: {key_code}")
            return

        keysym = XK.string_to_keysym(keysym_name)
        if not keysym:
            print(f"Unknown keysym for X11 injector: {keysym_name}")
            return

        keycode = self.display.keysym_to_keycode(keysym)
        if not keycode:
            print(f"No X11 keycode for keysym: {keysym_name}")
            return

        event_type = X.KeyPress if pressed else X.KeyRelease
        fake_input(self.display, event_type, detail=keycode)
        self.display.sync()

    async def inject_key(self, keycode: int, pressed: bool):
        """兼容接口：按 evdev keycode 注入键盘事件。"""
        if not self.display:
            return

        # Xorg 常见映射近似为 evdev + 8。
        x11_keycode = max(8, int(keycode) + 8)
        event_type = X.KeyPress if pressed else X.KeyRelease
        fake_input(self.display, event_type, detail=x11_keycode)
        self.display.sync()

    async def cleanup(self):
        """清理资源。"""
        if self.display:
            try:
                self.display.close()
            except Exception:
                pass
            self.display = None
