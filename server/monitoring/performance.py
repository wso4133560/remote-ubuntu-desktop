"""性能监控服务"""
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import PerformanceMetric, Session as SessionModel
from ..database.database import get_database


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.monitoring_tasks = {}

    async def start_monitoring(self, session_id: str):
        """开始监控会话"""
        if session_id in self.monitoring_tasks:
            return

        task = asyncio.create_task(self._monitor_session(session_id))
        self.monitoring_tasks[session_id] = task
        print(f"Started monitoring session: {session_id}")

    async def stop_monitoring(self, session_id: str):
        """停止监控会话"""
        if session_id in self.monitoring_tasks:
            self.monitoring_tasks[session_id].cancel()
            del self.monitoring_tasks[session_id]
            print(f"Stopped monitoring session: {session_id}")

    async def _monitor_session(self, session_id: str):
        """监控会话性能"""
        db = get_database()

        try:
            while True:
                await asyncio.sleep(30)  # 每 30 秒计算一次平均值

                async with db.session() as session:
                    # 获取会话
                    result = await session.execute(
                        select(SessionModel).where(SessionModel.session_id == session_id)
                    )
                    session_obj = result.scalar_one_or_none()

                    if not session_obj:
                        break

                    # 计算最近 30 秒的平均值
                    result = await session.execute(
                        select(
                            func.avg(PerformanceMetric.fps),
                            func.avg(PerformanceMetric.bitrate),
                            func.avg(PerformanceMetric.rtt),
                            func.avg(PerformanceMetric.packet_loss),
                        )
                        .where(PerformanceMetric.session_id == session_obj.id)
                        .where(
                            PerformanceMetric.timestamp
                            >= datetime.utcnow().timestamp() - 30
                        )
                    )
                    avg_data = result.one_or_none()

                    if avg_data and avg_data[0]:
                        # 更新会话的平均值
                        session_obj.avg_fps = float(avg_data[0])
                        session_obj.avg_bitrate = int(avg_data[1])
                        session_obj.avg_rtt = float(avg_data[2])
                        session_obj.avg_packet_loss = float(avg_data[3])
                        await session.commit()

                        print(
                            f"Session {session_id}: "
                            f"FPS={session_obj.avg_fps:.1f}, "
                            f"Bitrate={session_obj.avg_bitrate/1000:.1f}kbps, "
                            f"RTT={session_obj.avg_rtt:.1f}ms"
                        )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error monitoring session {session_id}: {e}")


# 全局性能监控器实例
performance_monitor = PerformanceMonitor()
