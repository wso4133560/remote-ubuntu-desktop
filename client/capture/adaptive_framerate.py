"""帧率自适应控制"""
import asyncio
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class FrameRateStats:
    """帧率统计"""
    target_fps: int
    actual_fps: float
    dropped_frames: int
    total_frames: int
    avg_encode_time: float


class AdaptiveFrameRate:
    """自适应帧率控制器"""

    def __init__(self, target_fps: int = 30, min_fps: int = 10, max_fps: int = 60):
        self.target_fps = target_fps
        self.min_fps = min_fps
        self.max_fps = max_fps
        self.current_fps = target_fps

        self.frame_times = []
        self.encode_times = []
        self.dropped_frames = 0
        self.total_frames = 0

        self.last_adjust_time = time.time()
        self.adjust_interval = 5.0

    def record_frame(self, encode_time: float):
        """记录帧处理时间"""
        current_time = time.time()
        self.frame_times.append(current_time)
        self.encode_times.append(encode_time)
        self.total_frames += 1

        if len(self.frame_times) > 100:
            self.frame_times.pop(0)
            self.encode_times.pop(0)

    def record_dropped_frame(self):
        """记录丢帧"""
        self.dropped_frames += 1

    def get_stats(self) -> FrameRateStats:
        """获取统计信息"""
        actual_fps = self._calculate_actual_fps()
        avg_encode_time = sum(self.encode_times) / len(self.encode_times) if self.encode_times else 0

        return FrameRateStats(
            target_fps=self.target_fps,
            actual_fps=actual_fps,
            dropped_frames=self.dropped_frames,
            total_frames=self.total_frames,
            avg_encode_time=avg_encode_time
        )

    def _calculate_actual_fps(self) -> float:
        """计算实际帧率"""
        if len(self.frame_times) < 2:
            return 0.0

        time_span = self.frame_times[-1] - self.frame_times[0]
        if time_span > 0:
            return (len(self.frame_times) - 1) / time_span
        return 0.0

    def should_adjust(self) -> bool:
        """是否应该调整帧率"""
        current_time = time.time()
        if current_time - self.last_adjust_time < self.adjust_interval:
            return False

        if len(self.frame_times) < 10:
            return False

        return True

    def adjust(self) -> Optional[int]:
        """调整帧率"""
        if not self.should_adjust():
            return None

        stats = self.get_stats()
        new_fps = self.current_fps

        drop_rate = self.dropped_frames / max(self.total_frames, 1)
        avg_encode_time = stats.avg_encode_time
        target_frame_time = 1.0 / self.target_fps

        if drop_rate > 0.1:
            new_fps = max(self.min_fps, int(self.current_fps * 0.8))
            print(f"High drop rate ({drop_rate:.2%}), reducing FPS to {new_fps}")

        elif avg_encode_time > target_frame_time * 0.9:
            new_fps = max(self.min_fps, int(self.current_fps * 0.9))
            print(f"High encode time ({avg_encode_time:.3f}s), reducing FPS to {new_fps}")

        elif drop_rate < 0.01 and avg_encode_time < target_frame_time * 0.5:
            new_fps = min(self.max_fps, int(self.current_fps * 1.1))
            print(f"Good performance, increasing FPS to {new_fps}")

        if new_fps != self.current_fps:
            self.current_fps = new_fps
            self.last_adjust_time = time.time()
            self.dropped_frames = 0
            return new_fps

        self.last_adjust_time = time.time()
        return None

    def reset(self):
        """重置统计"""
        self.frame_times.clear()
        self.encode_times.clear()
        self.dropped_frames = 0
        self.total_frames = 0
        self.current_fps = self.target_fps

    def get_frame_interval(self) -> float:
        """获取当前帧间隔"""
        return 1.0 / self.current_fps
