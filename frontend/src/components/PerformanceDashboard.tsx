import React, { useEffect, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import './PerformanceDashboard.css'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

interface PerformanceMetrics {
  timestamp: number
  fps: number
  bitrate: number
  rtt: number
  packet_loss: number
  cpu_usage: number
}

interface PerformanceDashboardProps {
  deviceId: string
}

export const PerformanceDashboard: React.FC<PerformanceDashboardProps> = ({ deviceId }) => {
  const [metrics, setMetrics] = useState<PerformanceMetrics[]>([])
  const [currentMetrics, setCurrentMetrics] = useState<PerformanceMetrics | null>(null)
  const [healthStatus, setHealthStatus] = useState<'good' | 'warning' | 'critical'>('good')

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const token = localStorage.getItem('access_token')
        const response = await fetch(
          `http://localhost:8000/api/v1/metrics/devices/${deviceId}?limit=60`,
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        )

        if (response.ok) {
          const data = await response.json()
          setMetrics(data)
          if (data.length > 0) {
            setCurrentMetrics(data[data.length - 1])
            updateHealthStatus(data[data.length - 1])
          }
        }
      } catch (error) {
        console.error('Failed to fetch metrics:', error)
      }
    }

    fetchMetrics()
    const interval = setInterval(fetchMetrics, 5000)

    return () => clearInterval(interval)
  }, [deviceId])

  const updateHealthStatus = (metric: PerformanceMetrics) => {
    if (metric.packet_loss > 5 || metric.rtt > 200 || metric.fps < 15) {
      setHealthStatus('critical')
    } else if (metric.packet_loss > 2 || metric.rtt > 100 || metric.fps < 25) {
      setHealthStatus('warning')
    } else {
      setHealthStatus('good')
    }
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      }
    },
    scales: {
      x: {
        display: false
      },
      y: {
        beginAtZero: true
      }
    }
  }

  const fpsData = {
    labels: metrics.map((_, i) => i),
    datasets: [
      {
        label: 'FPS',
        data: metrics.map(m => m.fps),
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        fill: true,
        tension: 0.4
      }
    ]
  }

  const bitrateData = {
    labels: metrics.map((_, i) => i),
    datasets: [
      {
        label: 'Bitrate (Mbps)',
        data: metrics.map(m => m.bitrate / 1000000),
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        fill: true,
        tension: 0.4
      }
    ]
  }

  const rttData = {
    labels: metrics.map((_, i) => i),
    datasets: [
      {
        label: 'RTT (ms)',
        data: metrics.map(m => m.rtt),
        borderColor: 'rgb(255, 159, 64)',
        backgroundColor: 'rgba(255, 159, 64, 0.2)',
        fill: true,
        tension: 0.4
      }
    ]
  }

  const packetLossData = {
    labels: metrics.map((_, i) => i),
    datasets: [
      {
        label: 'Packet Loss (%)',
        data: metrics.map(m => m.packet_loss),
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.2)',
        fill: true,
        tension: 0.4
      }
    ]
  }

  const getHealthStatusColor = () => {
    switch (healthStatus) {
      case 'good': return '#28a745'
      case 'warning': return '#ffc107'
      case 'critical': return '#dc3545'
    }
  }

  const getHealthStatusText = () => {
    switch (healthStatus) {
      case 'good': return '良好'
      case 'warning': return '警告'
      case 'critical': return '严重'
    }
  }

  return (
    <div className="performance-dashboard">
      <div className="dashboard-header">
        <h3>性能监控</h3>
        <div className="health-indicator" style={{ backgroundColor: getHealthStatusColor() }}>
          {getHealthStatusText()}
        </div>
      </div>

      {currentMetrics && (
        <div className="current-metrics">
          <div className="metric-card">
            <div className="metric-label">FPS</div>
            <div className="metric-value">{currentMetrics.fps.toFixed(1)}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">码率</div>
            <div className="metric-value">{(currentMetrics.bitrate / 1000000).toFixed(1)} Mbps</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">延迟</div>
            <div className="metric-value">{currentMetrics.rtt.toFixed(0)} ms</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">丢包率</div>
            <div className="metric-value">{currentMetrics.packet_loss.toFixed(2)}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">CPU</div>
            <div className="metric-value">{currentMetrics.cpu_usage.toFixed(1)}%</div>
          </div>
        </div>
      )}

      <div className="charts-grid">
        <div className="chart-container">
          <h4>帧率 (FPS)</h4>
          <div className="chart">
            <Line data={fpsData} options={chartOptions} />
          </div>
        </div>

        <div className="chart-container">
          <h4>码率 (Mbps)</h4>
          <div className="chart">
            <Line data={bitrateData} options={chartOptions} />
          </div>
        </div>

        <div className="chart-container">
          <h4>往返延迟 (ms)</h4>
          <div className="chart">
            <Line data={rttData} options={chartOptions} />
          </div>
        </div>

        <div className="chart-container">
          <h4>丢包率 (%)</h4>
          <div className="chart">
            <Line data={packetLossData} options={chartOptions} />
          </div>
        </div>
      </div>
    </div>
  )
}
