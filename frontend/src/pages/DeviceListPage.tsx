import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { apiClient } from '../services/api'

interface Device {
  device_id: string
  device_name: string
  status: string
  last_seen: string | null
  os_info: string | null
}

export default function DeviceListPage() {
  const [devices, setDevices] = useState<Device[]>([])
  const [filteredDevices, setFilteredDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const { logout } = useAuth()
  const navigate = useNavigate()
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    loadDevices()
    connectWebSocket()

    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const connectWebSocket = () => {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws?token=${token}`)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected for device status updates')
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)

        if (message.type === 'device_status_update' || message.type === 'status_update') {
          const messageDeviceId = message.device_id
          const messageStatus = message.status
          if (!messageDeviceId || !messageStatus) return

          setDevices((prevDevices) => {
            const index = prevDevices.findIndex(d => d.device_id === messageDeviceId)
            if (index >= 0) {
              const next = [...prevDevices]
              next[index] = {
                ...next[index],
                status: messageStatus,
                last_seen: message.last_seen ?? next[index].last_seen,
                device_name: message.device_name ?? next[index].device_name,
                os_info: message.os_info ?? next[index].os_info,
              }
              return next
            }

            return [
              {
                device_id: messageDeviceId,
                device_name: message.device_name || messageDeviceId,
                status: messageStatus,
                last_seen: message.last_seen || null,
                os_info: message.os_info || null,
              },
              ...prevDevices,
            ]
          })
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting in 5s...')
      setTimeout(connectWebSocket, 5000)
    }
  }

  useEffect(() => {
    filterDevices()
  }, [devices, searchQuery, statusFilter])

  const filterDevices = () => {
    let filtered = devices

    if (statusFilter !== 'all') {
      filtered = filtered.filter(d => d.status === statusFilter)
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(d =>
        d.device_name.toLowerCase().includes(query) ||
        d.device_id.toLowerCase().includes(query) ||
        d.os_info?.toLowerCase().includes(query)
      )
    }

    setFilteredDevices(filtered)
  }

  const loadDevices = async () => {
    try {
      const data = await apiClient.getDevices()
      setDevices(data.devices)
    } catch (err) {
      console.error('Failed to load devices:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleConnect = (deviceId: string) => {
    navigate(`/session/${deviceId}`)
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  if (loading) {
    return <div style={{ padding: '2rem' }}>Loading...</div>
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <header style={{ background: 'white', padding: '1rem 2rem', boxShadow: '0 2px 4px rgba(0,0,0,0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Remote Control - Devices</h1>
        <button onClick={handleLogout} style={{ padding: '0.5rem 1rem', background: '#dc3545', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}>
          Logout
        </button>
      </header>

      <div style={{ padding: '2rem' }}>
        <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Search devices..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              padding: '0.5rem 1rem',
              border: '1px solid #ddd',
              borderRadius: '4px',
              fontSize: '1rem'
            }}
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: '0.5rem 1rem',
              border: '1px solid #ddd',
              borderRadius: '4px',
              fontSize: '1rem'
            }}
          >
            <option value="all">All Status</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
            <option value="busy">Busy</option>
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
          {filteredDevices.map((device) => (
            <div key={device.device_id} style={{ background: 'white', padding: '1.5rem', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
              <h3 style={{ marginBottom: '0.5rem' }}>{device.device_name}</h3>
              <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#666' }}>
                <div>Status: <span style={{ color: device.status === 'online' ? 'green' : 'gray' }}>{device.status}</span></div>
                {device.os_info && <div>OS: {device.os_info}</div>}
                {device.last_seen && <div>Last seen: {new Date(device.last_seen).toLocaleString()}</div>}
              </div>
              <button
                onClick={() => handleConnect(device.device_id)}
                disabled={device.status !== 'online'}
                style={{
                  width: '100%',
                  padding: '0.5rem',
                  background: device.status === 'online' ? '#007bff' : '#ccc',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: device.status === 'online' ? 'pointer' : 'not-allowed',
                }}
              >
                Connect
              </button>
            </div>
          ))}
        </div>

        {filteredDevices.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: '3rem', color: '#666' }}>
            {devices.length === 0 ? 'No devices registered yet' : 'No devices match your search'}
          </div>
        )}
      </div>
    </div>
  )
}
