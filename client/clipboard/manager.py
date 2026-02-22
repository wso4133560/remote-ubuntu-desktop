"""剪贴板同步基础框架"""
import asyncio
from typing import Optional, Callable
import subprocess
import shutil


class ClipboardManager:
    """剪贴板管理器"""

    def __init__(self):
        self.last_content: Optional[str] = None
        self.on_clipboard_change: Optional[Callable] = None
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.use_wl_clipboard = False
        self.use_xclip = False

    def check_dependencies(self) -> dict:
        """检查依赖项"""
        dependencies = {
            "wl-clipboard": False,
            "xclip": False,
        }

        # 检查 wl-clipboard (Wayland)
        dependencies["wl-clipboard"] = shutil.which("wl-paste") is not None and shutil.which("wl-copy") is not None

        # 检查 xclip (X11 fallback)
        dependencies["xclip"] = shutil.which("xclip") is not None

        return dependencies

    async def initialize(self) -> bool:
        """初始化剪贴板管理"""
        dependencies = self.check_dependencies()
        print("Clipboard dependencies:")
        for dep, available in dependencies.items():
            status = "✓" if available else "✗"
            print(f"  {status} {dep}")

        if dependencies["wl-clipboard"]:
            print("Using wl-clipboard for Wayland")
            self.use_wl_clipboard = True
            self.use_xclip = False
            return True
        elif dependencies["xclip"]:
            print("Using xclip (X11 fallback)")
            self.use_wl_clipboard = False
            self.use_xclip = True
            return True
        else:
            print("No clipboard tool available")
            self.use_wl_clipboard = False
            self.use_xclip = False
            return False

    async def start_monitoring(self):
        """开始监控剪贴板变化"""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        print("Started clipboard monitoring")

    async def stop_monitoring(self):
        """停止监控剪贴板"""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            self.monitor_task = None
        print("Stopped clipboard monitoring")

    async def _monitor_loop(self):
        """监控循环"""
        try:
            while self.monitoring:
                content = await self.get_clipboard()
                if content and content != self.last_content:
                    self.last_content = content
                    if self.on_clipboard_change:
                        await self.on_clipboard_change(content)
                    print(f"Clipboard changed: {len(content)} chars")

                await asyncio.sleep(1)  # 每秒检查一次

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in clipboard monitor: {e}")

    async def get_clipboard(self) -> Optional[str]:
        """获取剪贴板内容"""
        try:
            if self.use_wl_clipboard:
                result = subprocess.run(
                    ["wl-paste", "-n"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    return result.stdout

            if self.use_xclip:
                result = subprocess.run(
                    ["xclip", "-o", "-selection", "clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                if result.returncode == 0:
                    return result.stdout

        except Exception as e:
            print(f"Error getting clipboard: {e}")

        return None

    async def set_clipboard(self, content: str):
        """设置剪贴板内容"""
        try:
            if self.use_wl_clipboard:
                result = subprocess.run(
                    ["wl-copy"],
                    input=content,
                    text=True,
                    capture_output=True,
                    timeout=1
                )
                if result.returncode == 0:
                    self.last_content = content
                    print(f"Clipboard set: {len(content)} chars")
                    return

            if self.use_xclip:
                result = subprocess.run(
                    ["xclip", "-i", "-selection", "clipboard"],
                    input=content,
                    text=True,
                    capture_output=True,
                    timeout=1
                )
                if result.returncode == 0:
                    self.last_content = content
                    print(f"Clipboard set: {len(content)} chars")
                    return

        except Exception as e:
            print(f"Error setting clipboard: {e}")

    def set_change_handler(self, handler: Callable):
        """设置剪贴板变化处理器"""
        self.on_clipboard_change = handler
