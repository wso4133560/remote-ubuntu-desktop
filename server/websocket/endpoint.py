"""WebSocket 端点"""
import secrets
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from .connection_manager import connection_manager
from .auth import authenticate_websocket, handle_heartbeat
from .router import message_router
from ..models.models import Device, Session as SessionModel
from ..database.database import get_database
from ..protocol.states import SessionState

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket 连接端点"""
    connection_id = secrets.token_urlsafe(16)

    device_payload = await authenticate_websocket(token, "device")
    user_payload = await authenticate_websocket(token, "access")

    if device_payload:
        client_type = "device"
        client_id = device_payload["device_id"]
    elif user_payload:
        client_type = "user"
        client_id = user_payload["sub"]
    else:
        await websocket.close(code=1008, reason="Invalid token")
        return

    await connection_manager.connect(websocket, connection_id, client_type, client_id)
    print(f"[DEBUG] {client_type} connected: {client_id}", flush=True)

    # 设备连接时更新状态为 online
    if client_type == "device":
        db = get_database()
        async with db.session() as session:
            result = await session.execute(
                select(Device).where(Device.device_id == client_id)
            )
            device = result.scalar_one_or_none()
            if device:
                # Recover from stale sessions left by abrupt frontend/server exits.
                stale_sessions = await session.execute(
                    select(SessionModel).where(
                        SessionModel.device_id == device.id,
                        SessionModel.ended_at.is_(None),
                    )
                )
                for stale in stale_sessions.scalars().all():
                    if stale.ended_at is None and stale.state in (
                        SessionState.PENDING,
                        SessionState.NEGOTIATING,
                        SessionState.ACTIVE,
                    ):
                        stale.state = SessionState.ENDING
                        stale.ended_at = datetime.utcnow()
                        stale.end_reason = "device_reconnected_cleanup"
                        session.add(stale)

                device.status = "online"
                device.last_seen = datetime.utcnow()
                session.add(device)
                await session.commit()
                await connection_manager.broadcast_device_status_update(
                    device_id=device.device_id,
                    status=device.status,
                    last_seen=(
                        device.last_seen.isoformat()
                        if device.last_seen
                        else None
                    ),
                    device_name=device.device_name,
                    os_info=device.os_info,
                )

    heartbeat_task = None
    try:
        import asyncio
        heartbeat_task = asyncio.create_task(
            handle_heartbeat(websocket, connection_id, client_id, client_type)
        )
        connection_manager.heartbeat_tasks[connection_id] = heartbeat_task

        while True:
            data = await websocket.receive_json()
            response = await message_router.route_message(data, client_id, client_type)
            if response:
                await websocket.send_json(response)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        connection_manager.disconnect(connection_id)

        # 设备断开连接时更新状态为 offline
        if client_type == "device":
            db = get_database()
            async with db.session() as session:
                result = await session.execute(
                    select(Device).where(Device.device_id == client_id)
                )
                device = result.scalar_one_or_none()
                if device:
                    device.status = "offline"
                    device.last_seen = datetime.utcnow()
                    session.add(device)
                    await session.commit()
                    await connection_manager.broadcast_device_status_update(
                        device_id=device.device_id,
                        status=device.status,
                        last_seen=(
                            device.last_seen.isoformat()
                            if device.last_seen
                            else None
                        ),
                        device_name=device.device_name,
                        os_info=device.os_info,
                    )
