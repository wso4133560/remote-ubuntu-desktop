/**
 * 信令消息类型枚举
 */
export enum MessageType {
  // 认证和会话管理
  AUTH = "auth",
  AUTH_SUCCESS = "auth_success",
  AUTH_FAILURE = "auth_failure",

  // 会话控制
  SESSION_REQUEST = "session_request",
  SESSION_ACCEPT = "session_accept",
  SESSION_REJECT = "session_reject",
  SESSION_END = "session_end",

  // WebRTC 信令
  SDP_OFFER = "sdp_offer",
  SDP_ANSWER = "sdp_answer",
  ICE_CANDIDATE = "ice_candidate",

  // 心跳和状态
  HEARTBEAT = "heartbeat",
  HEARTBEAT_ACK = "heartbeat_ack",
  STATUS_UPDATE = "status_update",

  // 性能监控
  METRICS_UPDATE = "metrics_update",

  // 错误处理
  ERROR = "error",
  ACK = "ack",
}
