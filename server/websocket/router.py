"""WebSocket 消息路由和转发"""
import asyncio
import secrets
from datetime import datetime
from typing import Dict, Optional
from ..protocol.message_types import MessageType
from ..protocol.schemas import validate_message, ErrorMessage
from ..protocol.error_codes import ErrorCode
from .connection_manager import connection_manager
from ..session.manager import session_manager
from ..database.database import get_database


class MessageRouter:
    """消息路由器"""

    def __init__(self):
        self.pending_acks: Dict[str, asyncio.Event] = {}
        self.session_routes: Dict[str, tuple[str, str]] = {}

    async def route_message(
        self, message: dict, sender_id: str, sender_type: str, sender_connection_id: str
    ) -> Optional[dict]:
        """路由消息"""
        print(f"[DEBUG] route_message: type={message.get('type')}, sender={sender_id}, sender_type={sender_type}", flush=True)
        try:
            validated_msg = validate_message(message)
            msg_type = validated_msg.type
            print(f"[DEBUG] validated msg_type: {msg_type}", flush=True)

            if msg_type == MessageType.HEARTBEAT:
                return await self._handle_heartbeat(sender_id)

            elif msg_type == MessageType.HEARTBEAT_ACK:
                # 心跳确认，不需要处理
                return None

            elif msg_type == MessageType.SESSION_REQUEST:
                print(f"[DEBUG] Routing to _route_session_request", flush=True)
                return await self._route_session_request(
                    validated_msg, sender_id, sender_connection_id
                )

            elif msg_type in [
                MessageType.SESSION_ACCEPT,
                MessageType.SESSION_REJECT,
            ]:
                return await self._route_session_response(validated_msg, sender_id)

            elif msg_type in [
                MessageType.SDP_OFFER,
                MessageType.SDP_ANSWER,
                MessageType.ICE_CANDIDATE,
            ]:
                return await self._route_webrtc_message(
                    validated_msg, sender_id, sender_type, sender_connection_id
                )

            elif msg_type == MessageType.SESSION_END:
                return await self._route_session_end(
                    validated_msg, sender_id, sender_type, sender_connection_id
                )

            elif msg_type == MessageType.METRICS_UPDATE:
                return await self._handle_metrics(validated_msg)

            else:
                return self._create_error_message(
                    ErrorCode.UNSUPPORTED_MESSAGE_TYPE,
                    f"Unsupported message type: {msg_type}",
                )

        except Exception as e:
            print(f"[DEBUG] Exception in route_message: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return self._create_error_message(
                ErrorCode.MESSAGE_VALIDATION_FAILED,
                str(e),
            )

    async def _handle_heartbeat(self, sender_id: str) -> dict:
        """处理心跳"""
        return {
            "type": MessageType.HEARTBEAT_ACK,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
        }

    async def _route_session_request(
        self, message, operator_id: str, operator_connection_id: str
    ) -> Optional[dict]:
        """路由会话请求"""
        device_id = message.device_id
        session_id = message.session_id
        print(f"[DEBUG] _route_session_request: device_id={device_id}, operator_id={operator_id}", flush=True)

        db = get_database()
        async with db.session() as session:
            success, new_session_id, error = await session_manager.create_session_request(
                device_id, operator_id, session_id, operator_connection_id, session
            )
            print(f"[DEBUG] create_session_request result: success={success}, error={error}", flush=True)

        if not success:
            return self._create_error_message(
                ErrorCode.DEVICE_OFFLINE if "offline" in error else ErrorCode.DEVICE_BUSY,
                error,
            )

        return None

    async def _route_session_response(self, message, device_id: str) -> Optional[dict]:
        """路由会话响应"""
        session_id = message.session_id
        msg_type = message.type

        db = get_database()
        async with db.session() as session:
            if msg_type == MessageType.SESSION_ACCEPT:
                success, error = await session_manager.accept_session(
                    session_id, device_id, session
                )
            else:
                reason = getattr(message, "reason", "rejected")
                success, error = await session_manager.reject_session(
                    session_id, reason, session
                )

        if not success:
            return self._create_error_message(
                ErrorCode.SESSION_NOT_FOUND,
                error,
            )

        return None

    async def _route_webrtc_message(
        self, message, sender_id: str, sender_type: str, sender_connection_id: str
    ) -> Optional[dict]:
        """路由 WebRTC 消息"""
        session_id = message.session_id
        print(f"[DEBUG] _route_webrtc_message: session_id={session_id}, sender_type={sender_type}", flush=True)
        print(f"[DEBUG] Active sessions: {list(session_manager.active_sessions.keys())}", flush=True)

        session_info = session_manager.active_sessions.get(session_id)
        if not session_info:
            print(f"[DEBUG] Session {session_id} not found in active_sessions", flush=True)
            return self._create_error_message(
                ErrorCode.SESSION_NOT_FOUND,
                "Session not found",
            )

        operator_id = session_info["operator_id"]
        device_id = session_info["device_id"]
        operator_conn_id = session_info.get("operator_connection_id")
        # validate_message() 返回的是 Pydantic 模型，发送前需转为可 JSON 序列化的 dict
        payload = message.model_dump(mode="json") if hasattr(message, "model_dump") else message

        if sender_type == "user":
            if operator_conn_id and sender_connection_id != operator_conn_id:
                return self._create_error_message(
                    ErrorCode.SESSION_NOT_FOUND,
                    "Session does not belong to this connection",
                )
            await connection_manager.send_to_device(device_id, payload)
        elif sender_type == "device":
            if operator_conn_id:
                await connection_manager.send_message(operator_conn_id, payload)
            else:
                await connection_manager.send_to_user(operator_id, payload)
            # 当设备返回 SDP Answer，认为会话进入 ACTIVE 状态
            if message.type == MessageType.SDP_ANSWER:
                db = get_database()
                async with db.session() as session:
                    await session_manager.activate_session(session_id, session)

        return None

    async def _route_session_end(
        self, message, sender_id: str, sender_type: str, sender_connection_id: str
    ) -> Optional[dict]:
        """路由会话结束"""
        session_id = message.session_id
        reason = getattr(message, "reason", None)
        session_info = session_manager.active_sessions.get(session_id)

        if sender_type == "user" and session_info:
            operator_conn_id = session_info.get("operator_connection_id")
            if operator_conn_id and sender_connection_id != operator_conn_id:
                return self._create_error_message(
                    ErrorCode.SESSION_NOT_FOUND,
                    "Session does not belong to this connection",
                )

        db = get_database()
        async with db.session() as session:
            success, error = await session_manager.end_session(session_id, reason, session)

        if not success:
            return self._create_error_message(
                ErrorCode.SESSION_NOT_FOUND,
                error,
            )

        return None

    async def _handle_metrics(self, message) -> Optional[dict]:
        """处理性能指标"""
        from ..api.v1.metrics import store_metrics
        from ..database.database import get_database

        session_id = message.session_id
        fps = message.fps
        bitrate = message.bitrate
        rtt = message.rtt
        packet_loss = message.packet_loss
        cpu_usage = message.cpu_usage

        db = get_database()
        async with db.session() as session:
            await store_metrics(session_id, fps, bitrate, rtt, packet_loss, cpu_usage, session)

        return None

    def _create_error_message(self, error_code: ErrorCode, error_message: str) -> dict:
        """创建错误消息"""
        return {
            "type": MessageType.ERROR,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "error_code": error_code,
            "error_message": error_message,
        }


# 全局消息路由器实例
message_router = MessageRouter()
