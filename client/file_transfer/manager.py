"""文件传输管理器"""
import asyncio
import os
import hashlib
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class FileTransfer:
    """文件传输信息"""
    transfer_id: str
    filename: str
    file_size: int
    chunk_size: int = 256 * 1024  # 256KB
    chunks_total: int = 0
    chunks_received: int = 0
    file_hash: Optional[str] = None
    status: str = "pending"  # pending, transferring, completed, failed


class FileTransferManager:
    """文件传输管理器"""

    def __init__(self, datachannel_manager):
        self.datachannel_manager = datachannel_manager
        self.active_transfers = {}
        self.download_dir = Path.home() / "Downloads" / "RemoteControl"
        self.upload_dir = Path.home()

    async def initialize(self):
        """初始化文件传输"""
        # 创建下载目录
        self.download_dir.mkdir(parents=True, exist_ok=True)
        print(f"File transfer initialized. Download dir: {self.download_dir}")

        # 设置 DataChannel 消息处理器
        self.datachannel_manager.set_file_message_handler(
            self._handle_file_message
        )

    async def send_file(self, file_path: str) -> str:
        """发送文件"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 创建传输信息
        transfer_id = hashlib.md5(
            f"{path.name}{path.stat().st_size}".encode()
        ).hexdigest()[:16]

        file_size = path.stat().st_size
        chunk_size = 256 * 1024
        chunks_total = (file_size + chunk_size - 1) // chunk_size

        transfer = FileTransfer(
            transfer_id=transfer_id,
            filename=path.name,
            file_size=file_size,
            chunk_size=chunk_size,
            chunks_total=chunks_total,
        )

        self.active_transfers[transfer_id] = transfer

        # 发送文件元数据
        await self._send_file_metadata(transfer)

        # 发送文件块
        transfer.status = "transferring"
        with open(path, "rb") as f:
            for chunk_index in range(chunks_total):
                chunk_data = f.read(chunk_size)
                await self._send_file_chunk(
                    transfer_id, chunk_index, chunk_data
                )
                transfer.chunks_received = chunk_index + 1

                # 显示进度
                progress = (chunk_index + 1) / chunks_total * 100
                print(f"Sending {path.name}: {progress:.1f}%")

                # 流控：等待一小段时间
                await asyncio.sleep(0.01)

        transfer.status = "completed"
        print(f"File sent: {path.name}")
        return transfer_id

    async def _send_file_metadata(self, transfer: FileTransfer):
        """发送文件元数据"""
        metadata = {
            "type": "file_metadata",
            "transfer_id": transfer.transfer_id,
            "filename": transfer.filename,
            "file_size": transfer.file_size,
            "chunk_size": transfer.chunk_size,
            "chunks_total": transfer.chunks_total,
        }

        # 通过 DataChannel 发送
        import json
        self.datachannel_manager.send_file_chunk(
            json.dumps(metadata).encode()
        )

    async def _send_file_chunk(self, transfer_id: str, chunk_index: int, data: bytes):
        """发送文件块"""
        # 构建二进制头部（64 字节）
        header = bytearray(64)

        # transfer_id (16 bytes)
        header[0:16] = transfer_id.encode()[:16]

        # chunk_index (4 bytes, big-endian)
        header[16:20] = chunk_index.to_bytes(4, byteorder="big")

        # chunk_size (4 bytes, big-endian)
        header[20:24] = len(data).to_bytes(4, byteorder="big")

        # 组合头部和数据
        chunk = bytes(header) + data

        # 通过 DataChannel 发送
        self.datachannel_manager.send_file_chunk(chunk)

    async def _handle_file_message(self, message):
        """处理文件消息"""
        if isinstance(message, str):
            # JSON 元数据
            import json
            data = json.loads(message)

            if data["type"] == "file_metadata":
                await self._handle_file_metadata(data)

        elif isinstance(message, bytes):
            # 二进制文件块
            await self._handle_file_chunk(message)

    async def _handle_file_metadata(self, metadata: dict):
        """处理文件元数据"""
        transfer_id = metadata["transfer_id"]
        filename = metadata["filename"]
        file_size = metadata["file_size"]
        chunks_total = metadata["chunks_total"]

        # 创建传输信息
        transfer = FileTransfer(
            transfer_id=transfer_id,
            filename=filename,
            file_size=file_size,
            chunks_total=chunks_total,
        )

        self.active_transfers[transfer_id] = transfer
        transfer.status = "transferring"

        # 创建文件
        file_path = self.download_dir / filename
        transfer.file_path = file_path

        print(f"Receiving file: {filename} ({file_size} bytes)")

    async def _handle_file_chunk(self, chunk: bytes):
        """处理文件块"""
        # 解析头部
        transfer_id = chunk[0:16].decode().rstrip("\x00")
        chunk_index = int.from_bytes(chunk[16:20], byteorder="big")
        chunk_size = int.from_bytes(chunk[20:24], byteorder="big")
        data = chunk[64:64+chunk_size]

        # 获取传输信息
        transfer = self.active_transfers.get(transfer_id)
        if not transfer:
            print(f"Unknown transfer: {transfer_id}")
            return

        # 写入文件
        file_path = transfer.file_path
        mode = "ab" if chunk_index > 0 else "wb"
        with open(file_path, mode) as f:
            f.write(data)

        transfer.chunks_received += 1

        # 显示进度
        progress = transfer.chunks_received / transfer.chunks_total * 100
        print(f"Receiving {transfer.filename}: {progress:.1f}%")

        # 检查是否完成
        if transfer.chunks_received >= transfer.chunks_total:
            transfer.status = "completed"
            print(f"File received: {transfer.filename}")
            print(f"Saved to: {file_path}")

    def get_transfer_progress(self, transfer_id: str) -> Optional[float]:
        """获取传输进度"""
        transfer = self.active_transfers.get(transfer_id)
        if not transfer:
            return None

        if transfer.chunks_total == 0:
            return 0.0

        return transfer.chunks_received / transfer.chunks_total
