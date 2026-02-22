/**
 * 消息模式定义和验证
 */
import { MessageType } from "./messageTypes";
import { ErrorCode } from "./errorCodes";
import { SessionState, DeviceStatus } from "./states";

export interface BaseMessage {
  type: MessageType;
  message_id: string;
  timestamp: number;
}

export interface AuthMessage extends BaseMessage {
  type: MessageType.AUTH;
  token: string;
}

export interface AuthSuccessMessage extends BaseMessage {
  type: MessageType.AUTH_SUCCESS;
  device_id?: string;
  user_id?: string;
}

export interface AuthFailureMessage extends BaseMessage {
  type: MessageType.AUTH_FAILURE;
  error_code: ErrorCode;
  error_message: string;
}

export interface SessionRequestMessage extends BaseMessage {
  type: MessageType.SESSION_REQUEST;
  session_id: string;
  device_id: string;
  operator_id: string;
}

export interface SessionAcceptMessage extends BaseMessage {
  type: MessageType.SESSION_ACCEPT;
  session_id: string;
}

export interface SessionRejectMessage extends BaseMessage {
  type: MessageType.SESSION_REJECT;
  session_id: string;
  reason: string;
}

export interface SessionEndMessage extends BaseMessage {
  type: MessageType.SESSION_END;
  session_id: string;
  reason?: string;
}

export interface SDPOfferMessage extends BaseMessage {
  type: MessageType.SDP_OFFER;
  session_id: string;
  sdp: string;
}

export interface SDPAnswerMessage extends BaseMessage {
  type: MessageType.SDP_ANSWER;
  session_id: string;
  sdp: string;
}

export interface ICECandidateMessage extends BaseMessage {
  type: MessageType.ICE_CANDIDATE;
  session_id: string;
  candidate: string;
  sdp_mid?: string;
  sdp_m_line_index?: number;
}

export interface HeartbeatMessage extends BaseMessage {
  type: MessageType.HEARTBEAT;
  device_id?: string;
}

export interface HeartbeatAckMessage extends BaseMessage {
  type: MessageType.HEARTBEAT_ACK;
}

export interface StatusUpdateMessage extends BaseMessage {
  type: MessageType.STATUS_UPDATE;
  device_id: string;
  status: DeviceStatus;
  session_state: SessionState;
}

export interface MetricsUpdateMessage extends BaseMessage {
  type: MessageType.METRICS_UPDATE;
  session_id: string;
  fps: number;
  bitrate: number;
  rtt: number;
  packet_loss: number;
  cpu_usage: number;
}

export interface ErrorMessage extends BaseMessage {
  type: MessageType.ERROR;
  error_code: ErrorCode;
  error_message: string;
  details?: Record<string, any>;
}

export interface AckMessage extends BaseMessage {
  type: MessageType.ACK;
  ack_message_id: string;
}

export type SignalingMessage =
  | AuthMessage
  | AuthSuccessMessage
  | AuthFailureMessage
  | SessionRequestMessage
  | SessionAcceptMessage
  | SessionRejectMessage
  | SessionEndMessage
  | SDPOfferMessage
  | SDPAnswerMessage
  | ICECandidateMessage
  | HeartbeatMessage
  | HeartbeatAckMessage
  | StatusUpdateMessage
  | MetricsUpdateMessage
  | ErrorMessage
  | AckMessage;

export function validateMessage(data: any): SignalingMessage {
  if (!data.type) {
    throw new Error("Missing message type");
  }
  if (!data.message_id) {
    throw new Error("Missing message_id");
  }
  if (!data.timestamp || data.timestamp <= 0) {
    throw new Error("Invalid timestamp");
  }
  return data as SignalingMessage;
}
