"""视频编码器"""
import asyncio
import subprocess
from typing import Optional, Callable
from enum import Enum


class EncoderType(Enum):
    """编码器类型"""
    VAAPI = "vaapi"
    NVENC = "nvenc"
    X264 = "x264"
    AUTO = "auto"


class VideoEncoder:
    """视频编码器"""

    def __init__(self, encoder_type: EncoderType = EncoderType.AUTO):
        self.encoder_type = encoder_type
        self.process: Optional[asyncio.subprocess.Process] = None
        self.frame_callback: Optional[Callable] = None
        self.running = False

    async def initialize(self, width: int, height: int, fps: int, bitrate: int) -> bool:
        """初始化编码器"""
        if self.encoder_type == EncoderType.AUTO:
            self.encoder_type = await self._detect_encoder()

        print(f"Using encoder: {self.encoder_type.value}")
        return True

    async def _detect_encoder(self) -> EncoderType:
        """检测可用编码器"""
        if await self._check_vaapi():
            return EncoderType.VAAPI
        elif await self._check_nvenc():
            return EncoderType.NVENC
        else:
            return EncoderType.X264

    async def _check_vaapi(self) -> bool:
        """检查 VAAPI 支持"""
        try:
            result = await asyncio.create_subprocess_exec(
                "vainfo",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(result.wait(), timeout=2.0)
            return result.returncode == 0
        except Exception:
            return False

    async def _check_nvenc(self) -> bool:
        """检查 NVENC 支持"""
        try:
            result = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(result.wait(), timeout=2.0)
            return result.returncode == 0
        except Exception:
            return False

    async def start_encoding(
        self,
        width: int,
        height: int,
        fps: int,
        bitrate: int,
        input_format: str = "rawvideo"
    ) -> bool:
        """开始编码"""
        try:
            cmd = self._build_ffmpeg_command(width, height, fps, bitrate, input_format)

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            self.running = True
            asyncio.create_task(self._read_encoded_stream())

            print(f"Encoding started: {width}x{height}@{fps}fps, {bitrate}bps")
            return True

        except Exception as e:
            print(f"Failed to start encoding: {e}")
            return False

    def _build_ffmpeg_command(
        self,
        width: int,
        height: int,
        fps: int,
        bitrate: int,
        input_format: str
    ) -> list:
        """构建 FFmpeg 命令"""
        base_cmd = [
            "ffmpeg",
            "-f", input_format,
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "pipe:0"
        ]

        if self.encoder_type == EncoderType.VAAPI:
            encoder_cmd = [
                "-vaapi_device", "/dev/dri/renderD128",
                "-vf", "format=nv12,hwupload",
                "-c:v", "h264_vaapi",
                "-b:v", str(bitrate)
            ]
        elif self.encoder_type == EncoderType.NVENC:
            encoder_cmd = [
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-b:v", str(bitrate)
            ]
        else:  # X264
            encoder_cmd = [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-b:v", str(bitrate)
            ]

        output_cmd = [
            "-f", "h264",
            "-movflags", "frag_keyframe+empty_moov",
            "pipe:1"
        ]

        return base_cmd + encoder_cmd + output_cmd

    async def encode_frame(self, frame_data: bytes):
        """编码一帧"""
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(frame_data)
                await self.process.stdin.drain()
            except Exception as e:
                print(f"Error encoding frame: {e}")

    async def _read_encoded_stream(self):
        """读取编码后的流"""
        try:
            while self.running and self.process:
                chunk = await self.process.stdout.read(65536)
                if not chunk:
                    break

                if self.frame_callback:
                    await self.frame_callback(chunk)

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

        print("Encoding stopped")

    def set_frame_callback(self, callback: Callable):
        """设置帧回调"""
        self.frame_callback = callback

    async def adjust_bitrate(self, new_bitrate: int):
        """动态调整码率"""
        print(f"Adjusting bitrate to {new_bitrate}bps")
