"""客户端性能监控"""
import asyncio
import psutil
import time
from typing import Optional, Dict
from datetime import datetime


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, sample_interval: int = 5):
        self.sample_interval = sample_interval
        self.monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.metrics: Dict = {}
        self.on_metrics_update: Optional[callable] = None

    async def start_monitoring(self):
        """开始监控"""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        print(f"Performance monitoring started (interval: {self.sample_interval}s)")

    async def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None
        print("Performance monitoring stopped")

    async def _monitor_loop(self):
        """监控循环"""
        try:
            while self.monitoring:
                metrics = await self._sample_metrics()
                self.metrics = metrics

                if self.on_metrics_update:
                    await self.on_metrics_update(metrics)

                await asyncio.sleep(self.sample_interval)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in performance monitor: {e}")

    async def _sample_metrics(self) -> Dict:
        """采样性能指标"""
        process = psutil.Process()

        cpu_percent = process.cpu_percent(interval=0.1)
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)

        system_cpu = psutil.cpu_percent(interval=0.1)
        system_memory = psutil.virtual_memory()

        net_io = psutil.net_io_counters()

        metrics = {
            "timestamp": datetime.utcnow().timestamp(),
            "process": {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_mb, 2),
                "threads": process.num_threads(),
            },
            "system": {
                "cpu_percent": round(system_cpu, 2),
                "memory_percent": round(system_memory.percent, 2),
                "memory_available_mb": round(system_memory.available / (1024 * 1024), 2),
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
            }
        }

        return metrics

    def set_metrics_handler(self, handler: callable):
        """设置指标更新处理器"""
        self.on_metrics_update = handler

    def get_current_metrics(self) -> Dict:
        """获取当前指标"""
        return self.metrics

    def check_degradation(self) -> Optional[str]:
        """检测性能降级"""
        if not self.metrics:
            return None

        process_metrics = self.metrics.get("process", {})
        system_metrics = self.metrics.get("system", {})

        cpu_percent = process_metrics.get("cpu_percent", 0)
        memory_mb = process_metrics.get("memory_mb", 0)
        system_cpu = system_metrics.get("cpu_percent", 0)
        system_memory = system_metrics.get("memory_percent", 0)

        if cpu_percent > 80:
            return f"HIGH_CPU_USAGE: Process CPU at {cpu_percent}%"

        if memory_mb > 1024:
            return f"HIGH_MEMORY_USAGE: Process memory at {memory_mb} MB"

        if system_cpu > 90:
            return f"SYSTEM_CPU_OVERLOAD: System CPU at {system_cpu}%"

        if system_memory > 90:
            return f"SYSTEM_MEMORY_OVERLOAD: System memory at {system_memory}%"

        return None
