"""PipeWire 音频流捕获"""
import asyncio
from typing import Optional, Callable


class PipeWireAudioCapture:
    """PipeWire 音频捕获"""

    def __init__(self, source_id: str):
        self.source_id = source_id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.audio_callback: Optional[Callable] = None
        self.running = False

    async def start_capture(
        self,
        sample_rate: int = 48000,
        channels: int = 2
    ) -> bool:
        """开始捕获音频"""
        try:
            cmd = [
                "pw-record",
                "--target", self.source_id,
                "--rate", str(sample_rate),
                "--channels", str(channels),
                "--format", "s16",
                "-"
            ]

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            self.running = True
            asyncio.create_task(self._read_audio_stream())

            print(f"Audio capture started: {sample_rate}Hz, {channels}ch")
            return True

        except Exception as e:
            print(f"Failed to start audio capture: {e}")
            return False

    async def _read_audio_stream(self):
        """读取音频流"""
        try:
            while self.running and self.process:
                chunk = await self.process.stdout.read(4096)
                if not chunk:
                    break

                if self.audio_callback:
                    await self.audio_callback(chunk)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error reading audio stream: {e}")

    async def stop_capture(self):
        """停止捕获"""
        self.running = False

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                print(f"Error stopping audio capture: {e}")

            self.process = None

        print("Audio capture stopped")

    def set_audio_callback(self, callback: Callable):
        """设置音频回调"""
        self.audio_callback = callback
