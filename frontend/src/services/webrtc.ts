import { SignalingClient } from './signaling'
import { MessageType } from '../protocol/messageTypes'

interface ExtendedIceCandidatePairStats extends RTCIceCandidatePairStats {
  selected?: boolean
}

export interface WebRTCPerformanceSnapshot {
  timestamp: number
  bytesReceived: number
  bytesSent: number
  packetsReceived: number
  packetsLost: number
  roundTripTimeMs: number | null
}

const isInboundVideoStats = (stat: RTCStats): stat is RTCInboundRtpStreamStats => {
  return stat.type === 'inbound-rtp' && (stat as RTCInboundRtpStreamStats).kind === 'video'
}

const isOutboundVideoStats = (stat: RTCStats): stat is RTCOutboundRtpStreamStats => {
  return stat.type === 'outbound-rtp' && (stat as RTCOutboundRtpStreamStats).kind === 'video'
}

const isSuccessfulCandidatePair = (stat: RTCStats): stat is ExtendedIceCandidatePairStats => {
  return stat.type === 'candidate-pair' && (stat as RTCIceCandidatePairStats).state === 'succeeded'
}

export class WebRTCManager {
  private peerConnection: RTCPeerConnection | null = null
  private signalingClient: SignalingClient
  private sessionId: string
  private onTrackCallback?: (stream: MediaStream) => void
  private controlChannel: RTCDataChannel | null = null
  private fileTransferChannel: RTCDataChannel | null = null

  constructor(signalingClient: SignalingClient, sessionId: string) {
    this.signalingClient = signalingClient
    this.sessionId = sessionId
  }

  async initialize(onTrack: (stream: MediaStream) => void) {
    this.onTrackCallback = onTrack

    const configuration: RTCConfiguration = {
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
      ],
    }

    this.peerConnection = new RTCPeerConnection(configuration)

    // Ensure offer always contains a stable video m-line for remote desktop stream.
    this.peerConnection.addTransceiver('video', { direction: 'recvonly' })

    this.peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        this.signalingClient.sendICECandidate(this.sessionId, event.candidate)
      }
    }

    this.peerConnection.ontrack = (event) => {
      console.log('Received remote track:', event.track.kind)
      if (this.onTrackCallback) {
        const stream = event.streams[0] ?? new MediaStream([event.track])
        this.onTrackCallback(stream)
      }
    }

    this.peerConnection.onconnectionstatechange = () => {
      console.log('Connection state:', this.peerConnection?.connectionState)
    }

    this.peerConnection.oniceconnectionstatechange = () => {
      console.log('ICE connection state:', this.peerConnection?.iceConnectionState)
    }

    // 创建 DataChannels
    this.controlChannel = this.peerConnection.createDataChannel('control')
    this.fileTransferChannel = this.peerConnection.createDataChannel('file-transfer')

    this.controlChannel.onopen = () => {
      console.log('Control DataChannel opened')
    }

    this.controlChannel.onmessage = (event) => {
      this.handleControlMessage(event.data)
    }

    this.fileTransferChannel.onopen = () => {
      console.log('File transfer DataChannel opened')
    }

    this.setupSignalingHandlers()
  }

  private setupSignalingHandlers() {
    this.signalingClient.on(MessageType.SDP_ANSWER, async (message) => {
      if (message.session_id === this.sessionId && this.peerConnection) {
        const answer = new RTCSessionDescription({
          type: 'answer',
          sdp: message.sdp,
        })
        await this.peerConnection.setRemoteDescription(answer)
        console.log('Set remote description (answer)')
      }
    })

    this.signalingClient.on(MessageType.ICE_CANDIDATE, async (message) => {
      if (message.session_id === this.sessionId && this.peerConnection) {
        const candidate = new RTCIceCandidate({
          candidate: message.candidate,
          sdpMid: message.sdp_mid,
          sdpMLineIndex: message.sdp_m_line_index,
        })
        await this.peerConnection.addIceCandidate(candidate)
        console.log('Added ICE candidate')
      }
    })
  }

  async createOffer() {
    if (!this.peerConnection) {
      throw new Error('PeerConnection not initialized')
    }

    const offer = await this.peerConnection.createOffer()

    await this.peerConnection.setLocalDescription(offer)
    this.signalingClient.sendSDPOffer(this.sessionId, offer.sdp!)

    console.log('Created and sent SDP offer')
  }

  sendMouseMove(x: number, y: number) {
    if (this.controlChannel && this.controlChannel.readyState === 'open') {
      const message = {
        type: 'mouse_move',
        x: x,
        y: y,
      }
      this.controlChannel.send(JSON.stringify(message))
    }
  }

  sendMouseButton(button: number, pressed: boolean) {
    if (this.controlChannel && this.controlChannel.readyState === 'open') {
      const buttonMessage = {
        type: 'mouse_button',
        button: button,
        pressed: pressed,
      }
      this.controlChannel.send(JSON.stringify(buttonMessage))
    }
  }

  sendKeyEvent(key: string, pressed: boolean) {
    if (this.controlChannel && this.controlChannel.readyState === 'open') {
      const message = {
        type: 'key',
        key_code: key,
        pressed: pressed,
      }
      this.controlChannel.send(JSON.stringify(message))
    }
  }

  sendClipboard(content: string) {
    if (this.controlChannel && this.controlChannel.readyState === 'open') {
      const message = {
        type: 'clipboard',
        content: content,
      }
      this.controlChannel.send(JSON.stringify(message))
    }
  }

  sendFileChunk(transferId: string, chunkIndex: number, data: Uint8Array) {
    if (this.fileTransferChannel && this.fileTransferChannel.readyState === 'open') {
      const header = new ArrayBuffer(64)
      const headerView = new Uint8Array(header)

      const transferIdBytes = new TextEncoder().encode(transferId)
      headerView.set(transferIdBytes.slice(0, 16), 0)

      const chunkIndexBytes = new Uint8Array(4)
      new DataView(chunkIndexBytes.buffer).setUint32(0, chunkIndex, false)
      headerView.set(chunkIndexBytes, 16)

      const chunkSizeBytes = new Uint8Array(4)
      new DataView(chunkSizeBytes.buffer).setUint32(0, data.length, false)
      headerView.set(chunkSizeBytes, 20)

      const chunk = new Uint8Array(64 + data.length)
      chunk.set(headerView, 0)
      chunk.set(data, 64)

      this.fileTransferChannel.send(chunk)
    }
  }

  private handleControlMessage(data: string) {
    try {
      const message = JSON.parse(data)

      if (message.type === 'clipboard') {
        // 更新本地剪贴板
        navigator.clipboard.writeText(message.content).catch(console.error)
        console.log('Clipboard updated from remote')
      }
    } catch (error) {
      console.error('Error handling control message:', error)
    }
  }

  close() {
    if (this.controlChannel) {
      this.controlChannel.close()
      this.controlChannel = null
    }

    if (this.fileTransferChannel) {
      this.fileTransferChannel.close()
      this.fileTransferChannel = null
    }

    if (this.peerConnection) {
      this.peerConnection.close()
      this.peerConnection = null
    }

    this.signalingClient.off(MessageType.SDP_ANSWER)
    this.signalingClient.off(MessageType.ICE_CANDIDATE)
  }

  getConnectionState(): RTCPeerConnectionState | null {
    return this.peerConnection?.connectionState || null
  }

  async getPerformanceSnapshot(): Promise<WebRTCPerformanceSnapshot | null> {
    if (!this.peerConnection) {
      return null
    }

    const report = await this.peerConnection.getStats()
    let inboundVideoStats: RTCInboundRtpStreamStats | null = null
    let outboundVideoStats: RTCOutboundRtpStreamStats | null = null
    let candidatePairStats: ExtendedIceCandidatePairStats | null = null

    for (const stat of report.values()) {
      if (isInboundVideoStats(stat)) {
        if (!inboundVideoStats || (stat.bytesReceived ?? 0) > (inboundVideoStats.bytesReceived ?? 0)) {
          inboundVideoStats = stat
        }
        continue
      }

      if (isOutboundVideoStats(stat)) {
        if (!outboundVideoStats || (stat.bytesSent ?? 0) > (outboundVideoStats.bytesSent ?? 0)) {
          outboundVideoStats = stat
        }
        continue
      }

      if (isSuccessfulCandidatePair(stat)) {
        if (!candidatePairStats || stat.nominated || stat.selected) {
          candidatePairStats = stat
        }
      }
    }

    const bytesReceived = candidatePairStats?.bytesReceived ?? inboundVideoStats?.bytesReceived ?? 0
    const bytesSent = candidatePairStats?.bytesSent ?? outboundVideoStats?.bytesSent ?? 0
    const packetsReceived = inboundVideoStats?.packetsReceived ?? 0
    const packetsLost = inboundVideoStats?.packetsLost ?? 0
    const roundTripTimeMs = candidatePairStats?.currentRoundTripTime != null
      ? candidatePairStats.currentRoundTripTime * 1000
      : null

    return {
      timestamp: performance.now(),
      bytesReceived,
      bytesSent,
      packetsReceived,
      packetsLost,
      roundTripTimeMs
    }
  }
}
