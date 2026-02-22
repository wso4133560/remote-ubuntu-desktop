"""WebSocket 认证和心跳"""
import asyncio
import secrets
from datetime import datetime
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.jwt import verify_token
from ..models.models import Device, User
from ..database.database import get_database
from ..protocol.message_types import MessageType
from ..protocol.schemas import HeartbeatMessage, HeartbeatAckMessage


async def authenticate_websocket(
    token: str, expected_type: str
) -> Optional[dict]:
    """WebSocket 认证"""
    payload = verify_token(token, expected_type)
    return payload


async def handle_heartbeat(
    websocket: WebSocket,
    connection_id: str,
    client_id: str,
    client_type: str,
    interval: int = 30,
):
    """处理心跳"""
    db = get_database()

    while True:
        try:
            await asyncio.sleep(interval)

            heartbeat_msg = {
                "type": MessageType.HEARTBEAT,
                "message_id": secrets.token_urlsafe(16),
                "timestamp": datetime.utcnow().timestamp(),
            }

            await websocket.send_json(heartbeat_msg)

            async with db.session() as session:
                if client_type == "device":
                    result = await session.execute(
                        select(Device).where(Device.device_id == client_id)
                    )
                    device = result.scalar_one_or_none()
                    if device:
                        device.last_seen = datetime.utcnow()
                        # 确保设备状态为 online（除非正在会话中）
                        if device.status == "offline":
                            device.status = "online"
                        session.add(device)
                        await session.commit()

        except (WebSocketDisconnect, asyncio.CancelledError):
            break
        except Exception:
            break


async def send_heartbeat_ack(websocket: WebSocket):
    """发送心跳确认"""
    ack_msg = {
        "type": MessageType.HEARTBEAT_ACK,
        "message_id": secrets.token_urlsafe(16),
        "timestamp": datetime.utcnow().timestamp(),
    }
    await websocket.send_json(ack_msg)
