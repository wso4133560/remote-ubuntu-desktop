"""会话状态机定义"""
from enum import Enum
from typing import Set


class SessionState(str, Enum):
    """会话状态枚举"""

    IDLE = "idle"
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    ACTIVE = "active"
    ENDING = "ending"


# 状态转换规则
STATE_TRANSITIONS: dict[SessionState, Set[SessionState]] = {
    SessionState.IDLE: {SessionState.PENDING},
    SessionState.PENDING: {SessionState.NEGOTIATING, SessionState.IDLE},
    SessionState.NEGOTIATING: {SessionState.ACTIVE, SessionState.ENDING},
    SessionState.ACTIVE: {SessionState.ENDING},
    SessionState.ENDING: {SessionState.IDLE},
}


def is_valid_transition(from_state: SessionState, to_state: SessionState) -> bool:
    """检查状态转换是否有效"""
    return to_state in STATE_TRANSITIONS.get(from_state, set())


class DeviceStatus(str, Enum):
    """设备状态枚举"""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    ERROR = "error"
