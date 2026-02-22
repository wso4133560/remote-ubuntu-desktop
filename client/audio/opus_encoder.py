"""Opus 音频编码"""
import asyncio
from typing import Optional, Callable


class OpusEncoder:
    """Opus 音频编码器"""

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        bitrate: int = 64000
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.bitrate = bitrate
        self.process: Optional[asyncio.subprocess.Process] = None
        self.encoded_callback: Optional[Callable] = None
        self.running = False

    async def start_encoding(self) -> bool:
        """开始编码"""
        try:
            cmd = [
                "ffmpeg",
                "-f", "s16le",
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                "-i", "pipe:0",
                "-c:a", "libopus",
                "-b:a", str(self.bitrate),
                "-vbr", "on",
                "-compression_level", "10",
                "-frame_duration", "20",
                "-application", "voip",
                "-f", "opus",
                "pipe:1"
            ]

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            self.running = True
            asyncio.create_task(self._read_encoded_stream())

            print(f"Opus encoding started: {self.sample_rate}Hz, {self.channels}ch, {self.bitrate}bps")
            return True

        except Exception as e:
            print(f"Failed to start Opus encoding: {e}")
            return False

    async def encode_audio(self, audio_data: bytes):
        """编码音频数据"""
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(audio_data)
                await self.process.stdin.drain()
            except Exception as e:
                print(f"Error encoding audio: {e}")

    async def _read_encoded_stream(self):
        """读取编码后的流"""
        try:
            while self.running and self.process:
                chunk = await self.process.stdout.read(4096)
                if not chunk:
                    break

                if self.encoded_callback:
                    await self.encoded_callback(chunk)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error reading encoded stream: {e}")

    async def stop(self):
        """停止编码"""
        self.running = False

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                    await self.process.stdin.wait_closed()

                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                print(f"Error stopping encoder: {e}")

            self.process = None

        print("Opus encoding stopped")

    def set_encoded_callback(self, callback: Callable):
        """设置编码回调"""
        self.encoded_callback = callback

    async def adjust_bitrate(self, new_bitrate: int):
        """动态调整码率"""
        self.bitrate = new_bitrate
        print(f"Adjusting audio bitrate to {new_bitrate}bps")
