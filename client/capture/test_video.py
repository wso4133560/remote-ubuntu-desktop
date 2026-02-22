"""虚拟视频轨道（用于测试）"""
import asyncio
import time
from aiortc import VideoStreamTrack
from av import VideoFrame
import numpy as np


class TestVideoTrack(VideoStreamTrack):
    """测试视频轨道 - 生成彩色测试图案"""

    def __init__(self, width=1920, height=1080, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = fps
        self.frame_count = 0

    async def recv(self):
        """生成测试帧"""
        pts, time_base = await self.next_timestamp()

        # 生成彩色测试图案
        hue = (self.frame_count % 360) / 360.0
        frame_data = self._generate_test_pattern(hue)

        frame = VideoFrame.from_ndarray(frame_data, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base

        self.frame_count += 1

        # 控制帧率
        await asyncio.sleep(1 / self.fps)

        return frame

    def _generate_test_pattern(self, hue):
        """生成测试图案"""
        # 创建渐变背景
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # HSV 转 RGB
        h = hue * 6
        c = 255
        x = int(c * (1 - abs(h % 2 - 1)))

        if h < 1:
            r, g, b = c, x, 0
        elif h < 2:
            r, g, b = x, c, 0
        elif h < 3:
            r, g, b = 0, c, x
        elif h < 4:
            r, g, b = 0, x, c
        elif h < 5:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        frame[:, :] = [r, g, b]

        # 添加文本信息（简单的像素绘制）
        text = f"Frame: {self.frame_count}"
        self._draw_text(frame, text, 50, 50)

        return frame

    def _draw_text(self, frame, text, x, y):
        """简单的文本绘制"""
        # 这里只是一个占位符，实际应该使用 PIL 或 OpenCV
        pass
