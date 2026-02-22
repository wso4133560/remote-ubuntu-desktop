import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { SignalingClient } from '../services/signaling'
import { WebRTCManager } from '../services/webrtc'
import { MessageType } from '../protocol/messageTypes'
import { FileTransfer } from '../components/FileTransfer'

interface SessionStats {
  fps: number
  downloadMbps: number
  uploadMbps: number
  packetLossPercent: number | null
  roundTripTimeMs: number | null
}

interface SessionStatsSample {
  timestamp: number
  frameCount: number | null
  bytesReceived: number
  bytesSent: number
  packetsReceived: number
  packetsLost: number
}

const getRenderedFrameCount = (video: HTMLVideoElement): number | null => {
  if (typeof video.getVideoPlaybackQuality === 'function') {
    return video.getVideoPlaybackQuality().totalVideoFrames
  }

  const webkitVideo = video as HTMLVideoElement & { webkitDecodedFrameCount?: number }
  if (typeof webkitVideo.webkitDecodedFrameCount === 'number') {
    return webkitVideo.webkitDecodedFrameCount
  }

  return null
}

const formatStat = (value: number | null, digits = 1, unit = ''): string => {
  if (value == null || !Number.isFinite(value)) {
    return '--'
  }
  return `${value.toFixed(digits)}${unit}`
}

export default function SessionPage() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const [connectionState, setConnectionState] = useState('connecting')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showFileTransfer, setShowFileTransfer] = useState(false)
  const [showStats, setShowStats] = useState(true)
  const [sessionStats, setSessionStats] = useState<SessionStats>({
    fps: 0,
    downloadMbps: 0,
    uploadMbps: 0,
    packetLossPercent: null,
    roundTripTimeMs: null
  })

  const signalingClientRef = useRef<SignalingClient | null>(null)
  const webrtcManagerRef = useRef<WebRTCManager | null>(null)
  const sessionIdRef = useRef<string>('')
  const sessionAcceptedRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const sessionTimeoutRef = useRef<number | null>(null)
  const lastStatsSampleRef = useRef<SessionStatsSample | null>(null)
  const videoRecoveryTimerRef = useRef<number | null>(null)
  const videoRecoveryAttemptsRef = useRef(0)

  useEffect(() => {
    let mounted = true

    const init = async () => {
      if (mounted) {
        await initSession()
      }
    }

    init()

    return () => {
      mounted = false
      cleanup()
    }
  }, [deviceId])

  const initSession = async () => {
    try {
      setError('')
      setConnected(false)
      setConnectionState('connecting')
      const token = localStorage.getItem('access_token')
      if (!token) {
        throw new Error('No access token')
      }

      sessionIdRef.current = Math.random().toString(36).substring(2, 15)
      sessionAcceptedRef.current = false

      const signalingClient = new SignalingClient(token)
      signalingClientRef.current = signalingClient

      signalingClient.on(MessageType.SESSION_ACCEPT, async (message) => {
        if (sessionAcceptedRef.current) {
          console.warn('Ignoring duplicate session_accept:', message.session_id)
          return
        }
        sessionAcceptedRef.current = true
        console.log('Session accepted:', message)
        clearSessionTimeout()
        // 使用服务器返回的 session_id
        if (message.session_id) {
          sessionIdRef.current = message.session_id
          console.log('Updated session_id to:', message.session_id)
        }
        setError('')
        await startWebRTC()
      })

      signalingClient.on(MessageType.SESSION_REJECT, (message) => {
        console.log('Session rejected:', message.reason)
        clearSessionTimeout()
        setConnectionState('failed')
        setError(`Session rejected: ${message.reason}`)
      })

      signalingClient.on(MessageType.SESSION_END, () => {
        clearSessionTimeout()
        setConnectionState('ended')
        setError('Session ended by remote')
        setTimeout(() => navigate('/devices'), 2000)
      })

      signalingClient.on(MessageType.ERROR, (message: any) => {
        if (message.session_id && message.session_id !== sessionIdRef.current) {
          return
        }
        clearSessionTimeout()
        setConnectionState('failed')
        setError(message.error_message || 'Session setup failed')
      })

      console.log('Connecting to signaling server...')
      await signalingClient.connect()
      console.log('Sending session request for device:', deviceId)
      signalingClient.sendSessionRequest(deviceId!, sessionIdRef.current)

      setConnectionState('waiting for accept')
      sessionTimeoutRef.current = window.setTimeout(() => {
        setConnectionState('timeout')
        setError('Session request timed out. Please ensure the client is online.')
      }, 15000)
    } catch (err) {
      console.error('Failed to initialize session:', err)
      setConnectionState('failed')
      setError('Failed to connect to device')
    }
  }

  const clearVideoRecoveryTimer = () => {
    if (videoRecoveryTimerRef.current) {
      window.clearTimeout(videoRecoveryTimerRef.current)
      videoRecoveryTimerRef.current = null
    }
  }

  const startWebRTC = async (isRecovery = false) => {
    try {
      if (!isRecovery && webrtcManagerRef.current) {
        console.warn('WebRTC already initialized, skipping duplicate start')
        return
      }

      clearVideoRecoveryTimer()
      if (!isRecovery) {
        videoRecoveryAttemptsRef.current = 0
      }

      const webrtcManager = new WebRTCManager(
        signalingClientRef.current!,
        sessionIdRef.current
      )
      webrtcManagerRef.current = webrtcManager

      await webrtcManager.initialize((stream) => {
        if (videoRef.current) {
          const videoEl = videoRef.current
          videoEl.srcObject = stream
          // Ensure autoplay works reliably across browsers/policies.
          videoEl.muted = true
          void videoEl.play().catch((err) => {
            console.warn('Initial video.play() failed, retrying on metadata:', err)
          })
          videoEl.onloadedmetadata = () => {
            void videoEl.play().catch((err) => {
              console.warn('video.play() on loadedmetadata failed:', err)
            })
            if (videoEl.videoWidth > 0) {
              clearVideoRecoveryTimer()
              videoRecoveryAttemptsRef.current = 0
            }
          }
          videoEl.onplaying = () => {
            if (videoEl.videoWidth > 0) {
              clearVideoRecoveryTimer()
              videoRecoveryAttemptsRef.current = 0
            }
          }
          setConnected(true)
          setConnectionState('connected')
        }
      })

      await webrtcManager.createOffer()
      setConnectionState('negotiating')

      videoRecoveryTimerRef.current = window.setTimeout(() => {
        const videoEl = videoRef.current
        if (!videoEl || videoEl.videoWidth > 0) {
          clearVideoRecoveryTimer()
          videoRecoveryAttemptsRef.current = 0
          return
        }

        if (videoRecoveryAttemptsRef.current >= 2) {
          setConnectionState('failed')
          setError('Connected but no video frames received. Please reconnect.')
          return
        }

        videoRecoveryAttemptsRef.current += 1
        console.warn(
          `No playable video detected, renegotiating WebRTC (attempt ${videoRecoveryAttemptsRef.current})`
        )
        if (webrtcManagerRef.current) {
          webrtcManagerRef.current.close()
          webrtcManagerRef.current = null
        }
        setConnectionState('recovering')
        void startWebRTC(true)
      }, 9000)
    } catch (err) {
      setConnectionState('failed')
      setError('Failed to establish WebRTC connection')
      console.error(err)
    }
  }

  const clearSessionTimeout = () => {
    if (sessionTimeoutRef.current) {
      window.clearTimeout(sessionTimeoutRef.current)
      sessionTimeoutRef.current = null
    }
  }

  const cleanup = () => {
    clearSessionTimeout()
    clearVideoRecoveryTimer()
    sessionAcceptedRef.current = false
    if (webrtcManagerRef.current) {
      webrtcManagerRef.current.close()
    }
    if (signalingClientRef.current) {
      signalingClientRef.current.sendSessionEnd(sessionIdRef.current)
      signalingClientRef.current.disconnect()
    }
  }

  const handleDisconnect = () => {
    cleanup()
    navigate('/devices')
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLVideoElement>) => {
    if (!connected || !videoRef.current || !webrtcManagerRef.current) return

    const rect = videoRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height

    webrtcManagerRef.current.sendMouseMove(x, y)
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLVideoElement>) => {
    if (!connected || !videoRef.current || !webrtcManagerRef.current) return
    containerRef.current?.focus()
    const rect = videoRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    webrtcManagerRef.current.sendMouseMove(x, y)
    webrtcManagerRef.current.sendMouseButton(e.button, true)
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLVideoElement>) => {
    if (!connected || !videoRef.current || !webrtcManagerRef.current) return
    const rect = videoRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width
    const y = (e.clientY - rect.top) / rect.height
    webrtcManagerRef.current.sendMouseMove(x, y)
    webrtcManagerRef.current.sendMouseButton(e.button, false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!connected || !webrtcManagerRef.current) return
    e.preventDefault()
    webrtcManagerRef.current.sendKeyEvent(e.code, true)
  }

  const handleKeyUp = (e: React.KeyboardEvent) => {
    if (!connected || !webrtcManagerRef.current) return
    e.preventDefault()
    webrtcManagerRef.current.sendKeyEvent(e.code, false)
  }

  const toggleFullscreen = async () => {
    if (!containerRef.current) return

    if (!document.fullscreenElement) {
      await containerRef.current.requestFullscreen()
      setIsFullscreen(true)
    } else {
      await document.exitFullscreen()
      setIsFullscreen(false)
    }
  }

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
    }
  }, [])

  useEffect(() => {
    if (connected) {
      containerRef.current?.focus()
    }
  }, [connected])

  useEffect(() => {
    if (!connected) {
      lastStatsSampleRef.current = null
      setSessionStats({
        fps: 0,
        downloadMbps: 0,
        uploadMbps: 0,
        packetLossPercent: null,
        roundTripTimeMs: null
      })
      return
    }

    const interval = window.setInterval(() => {
      void (async () => {
        try {
          const webrtcManager = webrtcManagerRef.current
          const video = videoRef.current
          if (!webrtcManager || !video) {
            return
          }

          const snapshot = await webrtcManager.getPerformanceSnapshot()
          if (!snapshot) {
            return
          }

          const now = performance.now()
          const frameCount = getRenderedFrameCount(video)
          const previousSample = lastStatsSampleRef.current

          if (!previousSample) {
            lastStatsSampleRef.current = {
              timestamp: now,
              frameCount,
              bytesReceived: snapshot.bytesReceived,
              bytesSent: snapshot.bytesSent,
              packetsReceived: snapshot.packetsReceived,
              packetsLost: snapshot.packetsLost
            }
            setSessionStats((current) => ({
              ...current,
              roundTripTimeMs: snapshot.roundTripTimeMs ?? current.roundTripTimeMs
            }))
            return
          }

          const elapsedSeconds = (now - previousSample.timestamp) / 1000
          if (elapsedSeconds <= 0) {
            return
          }

          const receivedBytesDelta = Math.max(0, snapshot.bytesReceived - previousSample.bytesReceived)
          const sentBytesDelta = Math.max(0, snapshot.bytesSent - previousSample.bytesSent)
          const packetsReceivedDelta = Math.max(0, snapshot.packetsReceived - previousSample.packetsReceived)
          const packetsLostDelta = Math.max(0, snapshot.packetsLost - previousSample.packetsLost)

          const calculatedFps = frameCount != null && previousSample.frameCount != null
            ? Math.max(0, (frameCount - previousSample.frameCount) / elapsedSeconds)
            : null

          let packetLossPercent: number | null = null
          const totalPacketsDelta = packetsReceivedDelta + packetsLostDelta
          if (totalPacketsDelta > 0) {
            packetLossPercent = (packetsLostDelta / totalPacketsDelta) * 100
          }

          setSessionStats((current) => ({
            fps: calculatedFps ?? current.fps,
            downloadMbps: (receivedBytesDelta * 8) / (elapsedSeconds * 1_000_000),
            uploadMbps: (sentBytesDelta * 8) / (elapsedSeconds * 1_000_000),
            packetLossPercent: packetLossPercent ?? current.packetLossPercent,
            roundTripTimeMs: snapshot.roundTripTimeMs ?? current.roundTripTimeMs
          }))

          lastStatsSampleRef.current = {
            timestamp: now,
            frameCount,
            bytesReceived: snapshot.bytesReceived,
            bytesSent: snapshot.bytesSent,
            packetsReceived: snapshot.packetsReceived,
            packetsLost: snapshot.packetsLost
          }
        } catch (statsError) {
          console.error('Failed to collect WebRTC stats:', statsError)
        }
      })()
    }, 1000)

    return () => {
      window.clearInterval(interval)
    }
  }, [connected])

  return (
    <div
      ref={containerRef}
      style={{ minHeight: '100vh', background: '#000', display: 'flex', flexDirection: 'column' }}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      tabIndex={0}
    >
      <header style={{ background: '#1a1a1a', padding: '1rem 2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ color: 'white', margin: 0 }}>Remote Session - {deviceId}</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => setShowStats(!showStats)}
            style={{ padding: '0.5rem 1rem', background: '#1f6feb', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
            disabled={!connected}
          >
            {showStats ? 'Hide Stats' : 'Show Stats'}
          </button>
          <button
            onClick={() => setShowFileTransfer(!showFileTransfer)}
            style={{ padding: '0.5rem 1rem', background: '#17a2b8', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
            disabled={!connected}
          >
            {showFileTransfer ? 'Hide Files' : 'File Transfer'}
          </button>
          <button
            onClick={toggleFullscreen}
            style={{ padding: '0.5rem 1rem', background: '#28a745', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          </button>
          <button
            onClick={handleDisconnect}
            style={{ padding: '0.5rem 1rem', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Disconnect
          </button>
        </div>
      </header>

      <div style={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '1rem' }}>
        {error ? (
          <div style={{ color: 'red', fontSize: '1.2rem' }}>{error}</div>
        ) : (
          <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              onClick={() => containerRef.current?.focus()}
              onContextMenu={(e) => e.preventDefault()}
              onMouseMove={handleMouseMove}
              onMouseDown={handleMouseDown}
              onMouseUp={handleMouseUp}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                background: '#000',
                cursor: connected ? 'crosshair' : 'default'
              }}
            />
            {!connected && (
              <div style={{ position: 'absolute', color: '#ddd', fontSize: '1.05rem' }}>
                Connecting... ({connectionState})
              </div>
            )}
            {connected && showStats && (
              <div
                style={{
                  position: 'absolute',
                  top: '1rem',
                  right: '1rem',
                  minWidth: '260px',
                  background: 'rgba(15, 23, 42, 0.86)',
                  border: '1px solid rgba(148, 163, 184, 0.4)',
                  borderRadius: '10px',
                  padding: '0.85rem',
                  color: '#e2e8f0',
                  backdropFilter: 'blur(4px)'
                }}
              >
                <div style={{ fontSize: '0.78rem', letterSpacing: '0.06em', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '0.6rem' }}>
                  实时传输统计
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem 1rem' }}>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>帧率</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{formatStat(sessionStats.fps, 1, ' FPS')}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>延迟</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{formatStat(sessionStats.roundTripTimeMs, 0, ' ms')}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>下载速度</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{formatStat(sessionStats.downloadMbps, 2, ' Mbps')}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>上传速度</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{formatStat(sessionStats.uploadMbps, 2, ' Mbps')}</div>
                  </div>
                  <div style={{ gridColumn: '1 / span 2' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>丢包率</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{formatStat(sessionStats.packetLossPercent, 2, '%')}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showFileTransfer && connected && webrtcManagerRef.current && (
        <FileTransfer
          webrtcManager={webrtcManagerRef.current}
          onClose={() => setShowFileTransfer(false)}
        />
      )}

      <div style={{ background: '#1a1a1a', padding: '0.5rem 2rem', color: '#888', fontSize: '0.9rem' }}>
        Status: {connectionState}
      </div>
    </div>
  )
}
