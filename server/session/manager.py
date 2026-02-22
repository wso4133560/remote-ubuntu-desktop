"""会话管理器"""
import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.models import Session as SessionModel, Device, User
from ..database.database import get_database
from ..database.transactions import immediate_transaction
from ..protocol.states import SessionState
from ..protocol.message_types import MessageType
from ..protocol.error_codes import ErrorCode
from ..websocket.connection_manager import connection_manager


class SessionManager:
    """会话管理器"""

    def __init__(self):
        self.active_sessions: Dict[str, dict] = {}
        self.session_timeouts: Dict[str, asyncio.Task] = {}

    async def create_session_request(
        self,
        device_id: str,
        operator_id: str,
        requested_session_id: Optional[str],
        operator_connection_id: Optional[str],
        session: AsyncSession,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """创建会话请求"""
        result = await session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()

        if not device:
            return False, None, "Device not found"

        if device.status == "busy":
            return False, None, "Device is busy"

        if device.status == "offline":
            return False, None, "Device is offline"

        session_id = requested_session_id or secrets.token_urlsafe(16)

        async with immediate_transaction(session):
            db_session = SessionModel(
                session_id=session_id,
                device_id=device.id,
                operator_id=int(operator_id),
                state=SessionState.PENDING,
            )
            session.add(db_session)

        self.active_sessions[session_id] = {
            "session_id": session_id,
            "device_id": device_id,
            "operator_id": operator_id,
            "operator_connection_id": operator_connection_id,
            "state": SessionState.PENDING,
            "created_at": datetime.utcnow(),
        }

        timeout_task = asyncio.create_task(
            self._session_timeout(session_id, timeout=30)
        )
        self.session_timeouts[session_id] = timeout_task

        message = {
            "type": MessageType.SESSION_REQUEST,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "device_id": device_id,
            "operator_id": operator_id,
        }

        print(f"[DEBUG] Attempting to send SESSION_REQUEST to device: {device_id}", flush=True)
        sent = await connection_manager.send_to_device(device_id, message)
        print(f"[DEBUG] Send result: {sent}", flush=True)
        if not sent:
            # 设备未连接，清理会话
            print(f"[DEBUG] Device {device_id} not connected, cleaning up session", flush=True)
            if session_id in self.session_timeouts:
                self.session_timeouts[session_id].cancel()
                del self.session_timeouts[session_id]
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            return False, None, "Device not connected to signaling server"

        return True, session_id, None

    async def accept_session(
        self,
        session_id: str,
        device_id: str,
        db_session: AsyncSession,
    ) -> tuple[bool, Optional[str]]:
        """接受会话"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return False, "Session not found"

        if session_info["state"] != SessionState.PENDING:
            return False, "Invalid session state"

        if session_id in self.session_timeouts:
            self.session_timeouts[session_id].cancel()
            del self.session_timeouts[session_id]

        session_info["state"] = SessionState.NEGOTIATING

        async with immediate_transaction(db_session):
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            db_session_obj = result.scalar_one_or_none()
            if db_session_obj:
                db_session_obj.state = SessionState.NEGOTIATING
                db_session.add(db_session_obj)

        message = {
            "type": MessageType.SESSION_ACCEPT,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
        }

        operator_conn_id = session_info.get("operator_connection_id")
        if operator_conn_id:
            await connection_manager.send_message(operator_conn_id, message)
        else:
            operator_id = session_info["operator_id"]
            await connection_manager.send_to_user(operator_id, message)

        return True, None

    async def reject_session(
        self,
        session_id: str,
        reason: str,
        db_session: AsyncSession,
    ) -> tuple[bool, Optional[str]]:
        """拒绝会话"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return False, "Session not found"

        if session_id in self.session_timeouts:
            self.session_timeouts[session_id].cancel()
            del self.session_timeouts[session_id]

        async with immediate_transaction(db_session):
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            db_session_obj = result.scalar_one_or_none()
            if db_session_obj:
                db_session_obj.state = SessionState.ENDING
                db_session_obj.ended_at = datetime.utcnow()
                db_session_obj.end_reason = reason
                db_session.add(db_session_obj)

        message = {
            "type": MessageType.SESSION_REJECT,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "reason": reason,
        }

        operator_conn_id = session_info.get("operator_connection_id")
        if operator_conn_id:
            await connection_manager.send_message(operator_conn_id, message)
        else:
            operator_id = session_info["operator_id"]
            await connection_manager.send_to_user(operator_id, message)

        del self.active_sessions[session_id]

        return True, None

    async def activate_session(
        self,
        session_id: str,
        db_session: AsyncSession,
    ) -> tuple[bool, Optional[str]]:
        """激活会话（WebRTC 连接建立后）"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return False, "Session not found"

        session_info["state"] = SessionState.ACTIVE

        updated_device = None
        async with immediate_transaction(db_session):
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            db_session_obj = result.scalar_one_or_none()
            if db_session_obj:
                db_session_obj.state = SessionState.ACTIVE
                db_session.add(db_session_obj)

            device_id = session_info["device_id"]
            result = await db_session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = result.scalar_one_or_none()
            if device:
                device.status = "busy"
                db_session.add(device)
                updated_device = device

        if updated_device:
            await connection_manager.broadcast_device_status_update(
                device_id=updated_device.device_id,
                status=updated_device.status,
                last_seen=(
                    updated_device.last_seen.isoformat()
                    if updated_device.last_seen
                    else None
                ),
                device_name=updated_device.device_name,
                os_info=updated_device.os_info,
            )

        return True, None

    async def end_session(
        self,
        session_id: str,
        reason: Optional[str],
        db_session: AsyncSession,
    ) -> tuple[bool, Optional[str]]:
        """结束会话"""
        session_info = self.active_sessions.get(session_id)
        if not session_info:
            return False, "Session not found"

        updated_device = None
        async with immediate_transaction(db_session):
            result = await db_session.execute(
                select(SessionModel).where(SessionModel.session_id == session_id)
            )
            db_session_obj = result.scalar_one_or_none()
            if db_session_obj:
                db_session_obj.state = SessionState.ENDING
                db_session_obj.ended_at = datetime.utcnow()
                db_session_obj.end_reason = reason
                db_session.add(db_session_obj)

            device_id = session_info["device_id"]
            result = await db_session.execute(
                select(Device).where(Device.device_id == device_id)
            )
            device = result.scalar_one_or_none()
            if device:
                device.status = "online"
                db_session.add(device)
                updated_device = device

        message = {
            "type": MessageType.SESSION_END,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "reason": reason,
        }

        operator_id = session_info["operator_id"]
        operator_conn_id = session_info.get("operator_connection_id")
        device_id = session_info["device_id"]
        if operator_conn_id:
            await connection_manager.send_message(operator_conn_id, message)
        else:
            await connection_manager.send_to_user(operator_id, message)
        await connection_manager.send_to_device(device_id, message)

        if updated_device:
            await connection_manager.broadcast_device_status_update(
                device_id=updated_device.device_id,
                status=updated_device.status,
                last_seen=(
                    updated_device.last_seen.isoformat()
                    if updated_device.last_seen
                    else None
                ),
                device_name=updated_device.device_name,
                os_info=updated_device.os_info,
            )

        del self.active_sessions[session_id]

        return True, None

    async def _session_timeout(self, session_id: str, timeout: int):
        """会话超时处理"""
        await asyncio.sleep(timeout)

        db = get_database()
        async with db.session() as session:
            await self.end_session(session_id, "timeout", session)

    def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """获取会话状态"""
        session_info = self.active_sessions.get(session_id)
        if session_info:
            return session_info["state"]
        return None


# 全局会话管理器实例
session_manager = SessionManager()
