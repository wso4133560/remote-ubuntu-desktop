import { MessageType } from '../protocol/messageTypes'
import { SignalingMessage } from '../protocol/schemas'

export class SignalingClient {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 6
  private messageHandlers: Map<MessageType, (message: any) => void> = new Map()

  constructor(private token: string) {}

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const wsUrl = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
      const wsHost = window.location.host
      this.ws = new WebSocket(`${wsUrl}${wsHost}/ws?token=${this.token}`)

      this.ws.onopen = () => {
        console.log('WebSocket connected')
        this.reconnectAttempts = 0
        resolve()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        reject(error)
      }

      this.ws.onclose = () => {
        console.log('WebSocket closed')
        this.handleReconnect()
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (err) {
          console.error('Failed to parse message:', err)
        }
      }
    })
  }

  disconnect() {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  on(messageType: MessageType, handler: (message: any) => void) {
    this.messageHandlers.set(messageType, handler)
  }

  off(messageType: MessageType) {
    this.messageHandlers.delete(messageType)
  }

  send(message: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('Sending message:', message.type)
      this.ws.send(JSON.stringify(message))
    } else {
      console.error('WebSocket not connected, readyState:', this.ws?.readyState)
    }
  }

  sendSessionRequest(deviceId: string, sessionId: string) {
    this.send({
      type: MessageType.SESSION_REQUEST,
      message_id: this.generateMessageId(),
      timestamp: Date.now() / 1000,
      session_id: sessionId,
      device_id: deviceId,
      operator_id: 'current_user',
    })
  }

  sendSDPOffer(sessionId: string, sdp: string) {
    this.send({
      type: MessageType.SDP_OFFER,
      message_id: this.generateMessageId(),
      timestamp: Date.now() / 1000,
      session_id: sessionId,
      sdp: sdp,
    })
  }

  sendICECandidate(sessionId: string, candidate: RTCIceCandidate) {
    this.send({
      type: MessageType.ICE_CANDIDATE,
      message_id: this.generateMessageId(),
      timestamp: Date.now() / 1000,
      session_id: sessionId,
      candidate: candidate.candidate,
      sdp_mid: candidate.sdpMid,
      sdp_m_line_index: candidate.sdpMLineIndex,
    })
  }

  sendSessionEnd(sessionId: string, reason?: string) {
    this.send({
      type: MessageType.SESSION_END,
      message_id: this.generateMessageId(),
      timestamp: Date.now() / 1000,
      session_id: sessionId,
      reason: reason,
    })
  }

  private handleMessage(message: SignalingMessage) {
    console.log('Received message:', message.type, message)
    const handler = this.messageHandlers.get(message.type as MessageType)
    if (handler) {
      handler(message)
    } else {
      console.warn('No handler for message type:', message.type)
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached')
      return
    }

    this.reconnectAttempts++
    const delay = Math.min(Math.pow(2, this.reconnectAttempts) * 1000, 32000)
    console.log(`Reconnecting in ${delay}ms...`)

    setTimeout(() => {
      this.connect().catch(console.error)
    }, delay)
  }

  private generateMessageId(): string {
    return Math.random().toString(36).substring(2, 15)
  }
}
