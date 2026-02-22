"""性能监控 API 端点"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.database import get_session
from ...database.transactions import immediate_transaction
from ...models.models import PerformanceMetric, Session as SessionModel

router = APIRouter(prefix="/metrics", tags=["metrics"])


class MetricsData(BaseModel):
    timestamp: datetime
    fps: float
    bitrate: int
    rtt: float
    packet_loss: float
    cpu_usage: float


class MetricsResponse(BaseModel):
    session_id: str
    metrics: list[MetricsData]
    avg_fps: Optional[float]
    avg_bitrate: Optional[int]
    avg_rtt: Optional[float]
    avg_packet_loss: Optional[float]


async def store_metrics(
    session_id: str,
    fps: float,
    bitrate: int,
    rtt: float,
    packet_loss: float,
    cpu_usage: float,
    db_session: AsyncSession,
) -> bool:
    """存储性能指标"""
    try:
        result = await db_session.execute(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        session_obj = result.scalar_one_or_none()

        if not session_obj:
            return False

        async with immediate_transaction(db_session):
            metric = PerformanceMetric(
                session_id=session_obj.id,
                fps=fps,
                bitrate=bitrate,
                rtt=rtt,
                packet_loss=packet_loss,
                cpu_usage=cpu_usage,
            )
            db_session.add(metric)

        return True
    except Exception:
        return False


@router.get("/{session_id}", response_model=MetricsResponse)
async def get_session_metrics(
    session_id: str,
    hours: int = 1,
    session: AsyncSession = Depends(get_session),
) -> MetricsResponse:
    """获取会话性能指标"""
    result = await session.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session_obj = result.scalar_one_or_none()

    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    since = datetime.utcnow() - timedelta(hours=hours)

    result = await session.execute(
        select(PerformanceMetric)
        .where(PerformanceMetric.session_id == session_obj.id)
        .where(PerformanceMetric.timestamp >= since)
        .order_by(PerformanceMetric.timestamp)
    )
    metrics = result.scalars().all()

    result = await session.execute(
        select(
            func.avg(PerformanceMetric.fps),
            func.avg(PerformanceMetric.bitrate),
            func.avg(PerformanceMetric.rtt),
            func.avg(PerformanceMetric.packet_loss),
        )
        .where(PerformanceMetric.session_id == session_obj.id)
        .where(PerformanceMetric.timestamp >= since)
    )
    avg_data = result.one_or_none()

    return MetricsResponse(
        session_id=session_id,
        metrics=[
            MetricsData(
                timestamp=m.timestamp,
                fps=m.fps,
                bitrate=m.bitrate,
                rtt=m.rtt,
                packet_loss=m.packet_loss,
                cpu_usage=m.cpu_usage,
            )
            for m in metrics
        ],
        avg_fps=float(avg_data[0]) if avg_data[0] else None,
        avg_bitrate=int(avg_data[1]) if avg_data[1] else None,
        avg_rtt=float(avg_data[2]) if avg_data[2] else None,
        avg_packet_loss=float(avg_data[3]) if avg_data[3] else None,
    )
