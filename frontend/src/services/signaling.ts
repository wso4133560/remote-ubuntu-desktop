import { MessageType } from '../protocol/messageTypes'
import { SignalingMessage } from '../protocol/schemas'

export class SignalingClient {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 6
  private messageHandlers: Map<MessageType, (message: any) => void> = new Map()
  private shouldReconnect = true

  constructor(private token: string) {}

  connect(timeoutMs = 15000): Promise<void> {
    this.shouldReconnect = true
    const deadline = Date.now() + timeoutMs

    return new Promise((resolve, reject) => {
      let settled = false

      const attemptConnect = () => {
        const wsUrl = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
        const wsHost = window.location.host
        const ws = new WebSocket(`${wsUrl}${wsHost}/ws?token=${this.token}`)
        this.ws = ws

        let opened = false
        const attemptTimeout = window.setTimeout(() => {
          if (!opened && ws.readyState !== WebSocket.CLOSED) {
            ws.close()
          }
        }, 4000)

        ws.onopen = () => {
          window.clearTimeout(attemptTimeout)
          opened = true
          this.reconnectAttempts = 0
          console.log('WebSocket connected')
          if (!settled) {
            settled = true
            resolve()
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
        }

        ws.onclose = () => {
          window.clearTimeout(attemptTimeout)

          if (opened) {
            console.log('WebSocket closed')
            if (this.shouldReconnect) {
              this.handleReconnect()
            }
            return
          }

          if (Date.now() >= deadline) {
            if (!settled) {
              settled = true
              reject(new Error('WebSocket connection timeout'))
            }
            return
          }

          const delay = Math.min(Math.pow(2, this.reconnectAttempts) * 500, 2000)
          this.reconnectAttempts++
          console.warn(`WebSocket connect attempt failed, retrying in ${delay}ms...`)
          window.setTimeout(attemptConnect, delay)
        }

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data)
            this.handleMessage(message)
          } catch (err) {
            console.error('Failed to parse message:', err)
          }
        }
      }

      attemptConnect()
    })
  }

  disconnect() {
    this.shouldReconnect = false
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
    if (!this.shouldReconnect) {
      return
    }

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
