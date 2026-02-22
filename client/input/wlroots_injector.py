"""wlroots 输入注入实现 (通过 ydotool)"""
import asyncio
from typing import Optional


class WlrootsInjector:
    """wlroots 输入注入器 (使用 ydotool)"""

    def __init__(self):
        self.ydotool_available = False

    async def initialize(self) -> bool:
        """初始化注入器"""
        result = await asyncio.create_subprocess_exec(
            "which", "ydotool",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await result.wait()

        self.ydotool_available = result.returncode == 0

        if self.ydotool_available:
            print("ydotool available for input injection")
            return True
        else:
            print("ydotool not found")
            return False

    async def inject_mouse_move(self, x: float, y: float):
        """注入鼠标移动"""
        if not self.ydotool_available:
            return

        try:
            result = await asyncio.create_subprocess_exec(
                "ydotool", "mousemove", "--absolute",
                str(int(x)), str(int(y)),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

        except Exception as e:
            print(f"Failed to inject mouse move: {e}")

    async def inject_mouse_button(self, button: int, pressed: bool):
        """注入鼠标按键"""
        if not self.ydotool_available:
            return

        try:
            button_map = {0: "0x110", 1: "0x111", 2: "0x112"}
            button_code = button_map.get(button, "0x110")

            if pressed:
                cmd = ["ydotool", "click", button_code]
            else:
                return

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

        except Exception as e:
            print(f"Failed to inject mouse button: {e}")

    async def inject_key(self, keycode: int, pressed: bool):
        """注入键盘按键"""
        if not self.ydotool_available:
            return

        try:
            if pressed:
                cmd = ["ydotool", "key", f"{keycode}:1"]
            else:
                cmd = ["ydotool", "key", f"{keycode}:0"]

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await result.wait()

        except Exception as e:
            print(f"Failed to inject key: {e}")

    async def cleanup(self):
        """清理资源"""
        pass
