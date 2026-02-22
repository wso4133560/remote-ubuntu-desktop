"""wlr-screencopy 屏幕捕获实现 (wlroots)"""
import asyncio
import subprocess
from typing import Optional, Tuple
from pathlib import Path
import tempfile


class WlrScreencopyCapture:
    """wlr-screencopy 屏幕捕获"""

    def __init__(self):
        self.capturing = False
        self.capture_task: Optional[asyncio.Task] = None
        self.temp_dir = None
        self.frame_callback = None

    async def initialize(self) -> bool:
        """初始化捕获"""
        result = subprocess.run(
            ["which", "wf-recorder"],
            capture_output=True
        )

        if result.returncode != 0:
            print("wf-recorder not found, trying grim")
            result = subprocess.run(
                ["which", "grim"],
                capture_output=True
            )
            if result.returncode != 0:
                print("Neither wf-recorder nor grim found")
                return False

        self.temp_dir = tempfile.mkdtemp(prefix="remote-control-")
        print(f"wlr-screencopy initialized, temp dir: {self.temp_dir}")
        return True

    async def start_capture(self, fps: int = 30) -> bool:
        """开始捕获"""
        if self.capturing:
            return False

        self.capturing = True
        self.capture_task = asyncio.create_task(self._capture_loop(fps))
        print(f"wlr-screencopy capture started at {fps} fps")
        return True

    async def _capture_loop(self, fps: int):
        """捕获循环"""
        frame_interval = 1.0 / fps
        frame_count = 0

        try:
            while self.capturing:
                start_time = asyncio.get_event_loop().time()

                frame_path = Path(self.temp_dir) / f"frame_{frame_count:06d}.png"

                result = await asyncio.create_subprocess_exec(
                    "grim",
                    str(frame_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                await result.wait()

                if result.returncode == 0 and self.frame_callback:
                    await self.frame_callback(frame_path)

                if frame_path.exists():
                    frame_path.unlink()

                frame_count += 1

                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in capture loop: {e}")

    async def stop_capture(self):
        """停止捕获"""
        self.capturing = False
        if self.capture_task:
            self.capture_task.cancel()
            try:
                await self.capture_task
            except asyncio.CancelledError:
                pass
            self.capture_task = None

        if self.temp_dir:
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

        print("wlr-screencopy capture stopped")

    def set_frame_callback(self, callback):
        """设置帧回调"""
        self.frame_callback = callback

    async def get_output_info(self) -> Optional[dict]:
        """获取输出信息"""
        try:
            result = await asyncio.create_subprocess_exec(
                "swaymsg",
                "-t",
                "get_outputs",
                "-r",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await result.communicate()

            if result.returncode == 0:
                import json
                outputs = json.loads(stdout.decode())
                if outputs:
                    active = next((o for o in outputs if o.get('active')), outputs[0])
                    return {
                        'name': active.get('name'),
                        'width': active.get('current_mode', {}).get('width'),
                        'height': active.get('current_mode', {}).get('height'),
                        'refresh': active.get('current_mode', {}).get('refresh')
                    }
        except Exception as e:
            print(f"Failed to get output info: {e}")

        return None
