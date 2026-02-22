import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { SignalingClient } from '../services/signaling'
import { WebRTCManager } from '../services/webrtc'
import { MessageType } from '../protocol/messageTypes'
import { FileTransfer } from '../components/FileTransfer'

export default function SessionPage() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const [connectionState, setConnectionState] = useState('connecting')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showFileTransfer, setShowFileTransfer] = useState(false)

  const signalingClientRef = useRef<SignalingClient | null>(null)
  const webrtcManagerRef = useRef<WebRTCManager | null>(null)
  const sessionIdRef = useRef<string>('')
  const containerRef = useRef<HTMLDivElement>(null)
  const sessionTimeoutRef = useRef<number | null>(null)

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

      const signalingClient = new SignalingClient(token)
      signalingClientRef.current = signalingClient

      signalingClient.on(MessageType.SESSION_ACCEPT, async (message) => {
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

  const startWebRTC = async () => {
    try {
      const webrtcManager = new WebRTCManager(
        signalingClientRef.current!,
        sessionIdRef.current
      )
      webrtcManagerRef.current = webrtcManager

      await webrtcManager.initialize((stream) => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          setConnected(true)
          setConnectionState('connected')
        }
      })

      await webrtcManager.createOffer()
      setConnectionState('negotiating')
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
