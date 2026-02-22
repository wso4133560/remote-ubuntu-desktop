import React, { useState, useCallback, useRef } from 'react'
import './FileTransfer.css'

interface FileTransferItem {
  id: string
  name: string
  size: number
  progress: number
  status: 'pending' | 'transferring' | 'completed' | 'failed' | 'cancelled'
  direction: 'upload' | 'download'
}

interface FileTransferProps {
  webrtcManager: any
  onClose: () => void
}

export const FileTransfer: React.FC<FileTransferProps> = ({ webrtcManager, onClose }) => {
  const [transfers, setTransfers] = useState<FileTransferItem[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = Array.from(e.dataTransfer.files)
    files.forEach(file => addFileTransfer(file))
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach(file => addFileTransfer(file))
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [])

  const addFileTransfer = (file: File) => {
    const transferId = Math.random().toString(36).substring(7)
    const newTransfer: FileTransferItem = {
      id: transferId,
      name: file.name,
      size: file.size,
      progress: 0,
      status: 'pending',
      direction: 'upload'
    }

    setTransfers(prev => [...prev, newTransfer])
    startFileTransfer(transferId, file)
  }

  const startFileTransfer = async (transferId: string, file: File) => {
    setTransfers(prev => prev.map(t =>
      t.id === transferId ? { ...t, status: 'transferring' as const } : t
    ))

    try {
      const chunkSize = 256 * 1024
      const totalChunks = Math.ceil(file.size / chunkSize)

      for (let i = 0; i < totalChunks; i++) {
        const start = i * chunkSize
        const end = Math.min(start + chunkSize, file.size)
        const chunk = file.slice(start, end)
        const arrayBuffer = await chunk.arrayBuffer()

        webrtcManager.sendFileChunk(transferId, i, new Uint8Array(arrayBuffer))

        const progress = ((i + 1) / totalChunks) * 100
        setTransfers(prev => prev.map(t =>
          t.id === transferId ? { ...t, progress } : t
        ))

        await new Promise(resolve => setTimeout(resolve, 10))
      }

      setTransfers(prev => prev.map(t =>
        t.id === transferId ? { ...t, status: 'completed' as const, progress: 100 } : t
      ))
    } catch (error) {
      console.error('File transfer failed:', error)
      setTransfers(prev => prev.map(t =>
        t.id === transferId ? { ...t, status: 'failed' as const } : t
      ))
    }
  }

  const cancelTransfer = (transferId: string) => {
    setTransfers(prev => prev.map(t =>
      t.id === transferId ? { ...t, status: 'cancelled' as const } : t
    ))
  }

  const removeTransfer = (transferId: string) => {
    setTransfers(prev => prev.filter(t => t.id !== transferId))
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
  }

  const getStatusIcon = (status: FileTransferItem['status']) => {
    switch (status) {
      case 'pending': return '⏳'
      case 'transferring': return '📤'
      case 'completed': return '✓'
      case 'failed': return '✗'
      case 'cancelled': return '⊘'
    }
  }

  return (
    <div className="file-transfer-panel">
      <div className="file-transfer-header">
        <h3>文件传输</h3>
        <button onClick={onClose} className="close-button">×</button>
      </div>

      <div
        className={`drop-zone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <div className="drop-zone-content">
          <span className="upload-icon">📁</span>
          <p>拖放文件到此处或点击选择</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />
      </div>

      <div className="transfer-list">
        {transfers.length === 0 ? (
          <div className="empty-state">暂无传输任务</div>
        ) : (
          transfers.map(transfer => (
            <div key={transfer.id} className={`transfer-item ${transfer.status}`}>
              <div className="transfer-info">
                <span className="status-icon">{getStatusIcon(transfer.status)}</span>
                <div className="file-details">
                  <div className="file-name">{transfer.name}</div>
                  <div className="file-size">{formatFileSize(transfer.size)}</div>
                </div>
              </div>

              <div className="transfer-progress">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${transfer.progress}%` }}
                  />
                </div>
                <span className="progress-text">{transfer.progress.toFixed(0)}%</span>
              </div>

              <div className="transfer-actions">
                {transfer.status === 'transferring' && (
                  <button
                    onClick={() => cancelTransfer(transfer.id)}
                    className="action-button cancel"
                  >
                    取消
                  </button>
                )}
                {(transfer.status === 'completed' || transfer.status === 'failed' || transfer.status === 'cancelled') && (
                  <button
                    onClick={() => removeTransfer(transfer.id)}
                    className="action-button remove"
                  >
                    移除
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
