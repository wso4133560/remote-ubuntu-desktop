"""消息模式定义和验证"""
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator
from .message_types import MessageType
from .error_codes import ErrorCode
from .states import SessionState, DeviceStatus


class BaseMessage(BaseModel):
    """基础消息模型"""

    type: MessageType
    message_id: str = Field(..., min_length=1, max_length=64)
    timestamp: float = Field(..., gt=0)


class AuthMessage(BaseMessage):
    """认证消息"""

    type: MessageType = MessageType.AUTH
    token: str = Field(..., min_length=1)


class AuthSuccessMessage(BaseMessage):
    """认证成功消息"""

    type: MessageType = MessageType.AUTH_SUCCESS
    device_id: Optional[str] = None
    user_id: Optional[str] = None


class AuthFailureMessage(BaseMessage):
    """认证失败消息"""

    type: MessageType = MessageType.AUTH_FAILURE
    error_code: ErrorCode
    error_message: str


class SessionRequestMessage(BaseMessage):
    """会话请求消息"""

    type: MessageType = MessageType.SESSION_REQUEST
    session_id: str = Field(..., min_length=1, max_length=64)
    device_id: str = Field(..., min_length=1, max_length=64)
    operator_id: str = Field(..., min_length=1, max_length=64)


class SessionAcceptMessage(BaseMessage):
    """会话接受消息"""

    type: MessageType = MessageType.SESSION_ACCEPT
    session_id: str = Field(..., min_length=1, max_length=64)


class SessionRejectMessage(BaseMessage):
    """会话拒绝消息"""

    type: MessageType = MessageType.SESSION_REJECT
    session_id: str = Field(..., min_length=1, max_length=64)
    reason: str


class SessionEndMessage(BaseMessage):
    """会话结束消息"""

    type: MessageType = MessageType.SESSION_END
    session_id: str = Field(..., min_length=1, max_length=64)
    reason: Optional[str] = None


class SDPOfferMessage(BaseMessage):
    """SDP Offer 消息"""

    type: MessageType = MessageType.SDP_OFFER
    session_id: str = Field(..., min_length=1, max_length=64)
    sdp: str = Field(..., min_length=1)


class SDPAnswerMessage(BaseMessage):
    """SDP Answer 消息"""

    type: MessageType = MessageType.SDP_ANSWER
    session_id: str = Field(..., min_length=1, max_length=64)
    sdp: str = Field(..., min_length=1)


class ICECandidateMessage(BaseMessage):
    """ICE 候选消息"""

    type: MessageType = MessageType.ICE_CANDIDATE
    session_id: str = Field(..., min_length=1, max_length=64)
    candidate: str
    sdp_mid: Optional[str] = None
    sdp_m_line_index: Optional[int] = None


class HeartbeatMessage(BaseMessage):
    """心跳消息"""

    type: MessageType = MessageType.HEARTBEAT
    device_id: Optional[str] = None


class HeartbeatAckMessage(BaseMessage):
    """心跳确认消息"""

    type: MessageType = MessageType.HEARTBEAT_ACK


class StatusUpdateMessage(BaseMessage):
    """状态更新消息"""

    type: MessageType = MessageType.STATUS_UPDATE
    device_id: str = Field(..., min_length=1, max_length=64)
    status: DeviceStatus
    session_state: SessionState


class MetricsUpdateMessage(BaseMessage):
    """性能指标更新消息"""

    type: MessageType = MessageType.METRICS_UPDATE
    session_id: str = Field(..., min_length=1, max_length=64)
    fps: float = Field(..., ge=0, le=120)
    bitrate: int = Field(..., ge=0)
    rtt: float = Field(..., ge=0)
    packet_loss: float = Field(..., ge=0, le=1)
    cpu_usage: float = Field(..., ge=0, le=1)


class ErrorMessage(BaseMessage):
    """错误消息"""

    type: MessageType = MessageType.ERROR
    error_code: ErrorCode
    error_message: str
    details: Optional[dict[str, Any]] = None


class AckMessage(BaseMessage):
    """确认消息"""

    type: MessageType = MessageType.ACK
    ack_message_id: str = Field(..., min_length=1, max_length=64)


def validate_message(data: dict[str, Any]) -> BaseMessage:
    """验证并解析消息"""
    msg_type = data.get("type")
    if not msg_type:
        raise ValueError("Missing message type")

    message_classes = {
        MessageType.AUTH: AuthMessage,
        MessageType.AUTH_SUCCESS: AuthSuccessMessage,
        MessageType.AUTH_FAILURE: AuthFailureMessage,
        MessageType.SESSION_REQUEST: SessionRequestMessage,
        MessageType.SESSION_ACCEPT: SessionAcceptMessage,
        MessageType.SESSION_REJECT: SessionRejectMessage,
        MessageType.SESSION_END: SessionEndMessage,
        MessageType.SDP_OFFER: SDPOfferMessage,
        MessageType.SDP_ANSWER: SDPAnswerMessage,
        MessageType.ICE_CANDIDATE: ICECandidateMessage,
        MessageType.HEARTBEAT: HeartbeatMessage,
        MessageType.HEARTBEAT_ACK: HeartbeatAckMessage,
        MessageType.STATUS_UPDATE: StatusUpdateMessage,
        MessageType.METRICS_UPDATE: MetricsUpdateMessage,
        MessageType.ERROR: ErrorMessage,
        MessageType.ACK: AckMessage,
    }

    message_class = message_classes.get(MessageType(msg_type))
    if not message_class:
        raise ValueError(f"Unknown message type: {msg_type}")

    return message_class.model_validate(data)
