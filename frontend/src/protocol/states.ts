/**
 * 会话状态机定义
 */
export enum SessionState {
  IDLE = "idle",
  PENDING = "pending",
  NEGOTIATING = "negotiating",
  ACTIVE = "active",
  ENDING = "ending",
}

/**
 * 状态转换规则
 */
export const STATE_TRANSITIONS: Record<SessionState, Set<SessionState>> = {
  [SessionState.IDLE]: new Set([SessionState.PENDING]),
  [SessionState.PENDING]: new Set([SessionState.NEGOTIATING, SessionState.IDLE]),
  [SessionState.NEGOTIATING]: new Set([SessionState.ACTIVE, SessionState.ENDING]),
  [SessionState.ACTIVE]: new Set([SessionState.ENDING]),
  [SessionState.ENDING]: new Set([SessionState.IDLE]),
};

/**
 * 检查状态转换是否有效
 */
export function isValidTransition(
  fromState: SessionState,
  toState: SessionState
): boolean {
  return STATE_TRANSITIONS[fromState]?.has(toState) ?? false;
}

/**
 * 设备状态枚举
 */
export enum DeviceStatus {
  ONLINE = "online",
  OFFLINE = "offline",
  BUSY = "busy",
  ERROR = "error",
}
