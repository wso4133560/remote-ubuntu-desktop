"""设备管理 API 端点"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.database import get_session
from ...database.transactions import immediate_transaction
from ...models.models import Device, Session as SessionModel
from ...auth.jwt import create_device_token, verify_token
from ...auth.password import hash_password

router = APIRouter(prefix="/devices", tags=["devices"])


class DeviceRegisterRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=128)
    os_info: Optional[str] = None
    capabilities: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    device_id: str
    device_token: str
    message: str


class DeviceInfo(BaseModel):
    device_id: str
    device_name: str
    status: str
    last_seen: Optional[datetime]
    registered_at: datetime
    ip_address: Optional[str]
    os_info: Optional[str]


class DeviceListResponse(BaseModel):
    devices: list[DeviceInfo]
    total: int


class SessionHistory(BaseModel):
    session_id: str
    operator_username: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    avg_fps: Optional[float]


class DeviceHistoryResponse(BaseModel):
    device_id: str
    sessions: list[SessionHistory]


@router.post("/register", response_model=DeviceRegisterResponse)
async def register_device(
    request: DeviceRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviceRegisterResponse:
    """注册新设备"""
    import secrets

    device_id = secrets.token_urlsafe(16)
    device_token = create_device_token(device_id)

    async with immediate_transaction(session):
        device = Device(
            device_id=device_id,
            device_name=request.device_name,
            device_token_hash=hash_password(device_token),
            status="offline",
            os_info=request.os_info,
            capabilities=request.capabilities,
        )
        session.add(device)

    return DeviceRegisterResponse(
        device_id=device_id,
        device_token=device_token,
        message="Device registered successfully",
    )


@router.get("", response_model=DeviceListResponse)
async def list_devices(
    status: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
) -> DeviceListResponse:
    """获取设备列表"""
    query = select(Device)
    if status:
        query = query.where(Device.status == status)
    query = query.order_by(desc(Device.last_seen))

    result = await session.execute(query)
    devices = result.scalars().all()

    return DeviceListResponse(
        devices=[
            DeviceInfo(
                device_id=d.device_id,
                device_name=d.device_name,
                status=d.status,
                last_seen=d.last_seen,
                registered_at=d.registered_at,
                ip_address=d.ip_address,
                os_info=d.os_info,
            )
            for d in devices
        ],
        total=len(devices),
    )


@router.get("/{device_id}", response_model=DeviceInfo)
async def get_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
) -> DeviceInfo:
    """获取设备详情"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    return DeviceInfo(
        device_id=device.device_id,
        device_name=device.device_name,
        status=device.status,
        last_seen=device.last_seen,
        registered_at=device.registered_at,
        ip_address=device.ip_address,
        os_info=device.os_info,
    )


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除设备"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    async with immediate_transaction(session):
        await session.delete(device)

    return {"message": "Device deleted successfully"}


@router.get("/{device_id}/history", response_model=DeviceHistoryResponse)
async def get_device_history(
    device_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> DeviceHistoryResponse:
    """获取设备历史记录"""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    result = await session.execute(
        select(SessionModel)
        .where(SessionModel.device_id == device.id)
        .order_by(desc(SessionModel.started_at))
        .limit(limit)
    )
    sessions = result.scalars().all()

    return DeviceHistoryResponse(
        device_id=device_id,
        sessions=[
            SessionHistory(
                session_id=s.session_id,
                operator_username=s.operator.username,
                started_at=s.started_at,
                ended_at=s.ended_at,
                duration_seconds=(
                    int((s.ended_at - s.started_at).total_seconds())
                    if s.ended_at
                    else None
                ),
                avg_fps=s.avg_fps,
            )
            for s in sessions
        ],
    )
