"""WebSocket 连接管理"""
import asyncio
from typing import Dict, Optional
from fastapi import WebSocket
from datetime import datetime

from .ack_manager import AckManager


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.device_connections: Dict[str, str] = {}
        self.user_connections: Dict[str, str] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.ack_managers: Dict[str, AckManager] = {}

    async def connect(self, websocket: WebSocket, connection_id: str, client_type: str, client_id: str):
        """建立连接"""
        import logging
        logger = logging.getLogger(__name__)

        await websocket.accept()
        self.active_connections[connection_id] = websocket

        if client_type == "device":
            self.device_connections[client_id] = connection_id
            print(f"[DEBUG] Device registered: {client_id} -> {connection_id}", flush=True)
            print(f"[DEBUG] device_connections now: {dict(self.device_connections)}", flush=True)
            logger.info(f"Device connected: {client_id} -> {connection_id}")
            logger.info(f"Active device connections: {list(self.device_connections.keys())}")
        elif client_type == "user":
            self.user_connections[client_id] = connection_id
            logger.info(f"User connected: {client_id} -> {connection_id}")

        async def send_callback(message: dict):
            await self.send_message(connection_id, message)

        ack_manager = AckManager(send_callback)
        self.ack_managers[connection_id] = ack_manager
        await ack_manager.start()

    def disconnect(self, connection_id: str):
        """断开连接"""
        print(f"[DEBUG] Disconnecting connection_id: {connection_id}", flush=True)

        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        for device_id, conn_id in list(self.device_connections.items()):
            if conn_id == connection_id:
                print(f"[DEBUG] Removing device: {device_id}", flush=True)
                del self.device_connections[device_id]
                print(f"[DEBUG] device_connections now: {dict(self.device_connections)}", flush=True)

        for user_id, conn_id in list(self.user_connections.items()):
            if conn_id == connection_id:
                del self.user_connections[user_id]

        if connection_id in self.heartbeat_tasks:
            self.heartbeat_tasks[connection_id].cancel()
            del self.heartbeat_tasks[connection_id]

        if connection_id in self.ack_managers:
            asyncio.create_task(self.ack_managers[connection_id].stop())
            del self.ack_managers[connection_id]

    async def send_message(self, connection_id: str, message: dict) -> bool:
        """发送消息到指定连接"""
        websocket = self.active_connections.get(connection_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                print(f"[DEBUG] send_message failed: connection_id={connection_id}, error={e}", flush=True)
                self.disconnect(connection_id)
                return False
        return False

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        """发送消息到设备"""
        connection_id = self.device_connections.get(device_id)
        print(f"[DEBUG] send_to_device: device_id={device_id}, found={connection_id is not None}", flush=True)
        print(f"[DEBUG] Available devices: {list(self.device_connections.keys())}", flush=True)
        if connection_id:
            return await self.send_message(connection_id, message)
        return False

    async def send_to_user(self, user_id: str, message: dict) -> bool:
        """发送消息到用户"""
        connection_id = self.user_connections.get(user_id)
        if connection_id:
            return await self.send_message(connection_id, message)
        return False

    async def broadcast_to_users(self, message: dict) -> None:
        """广播消息给所有在线用户"""
        for user_id in list(self.user_connections.keys()):
            await self.send_to_user(user_id, message)

    async def broadcast_device_status_update(
        self,
        device_id: str,
        status: str,
        last_seen: Optional[str] = None,
        device_name: Optional[str] = None,
        os_info: Optional[str] = None,
    ) -> None:
        """广播设备状态变更"""
        message = {
            "type": "device_status_update",
            "device_id": device_id,
            "status": status,
            "last_seen": last_seen,
            "device_name": device_name,
            "os_info": os_info,
        }
        await self.broadcast_to_users(message)

    def get_device_connection_id(self, device_id: str) -> Optional[str]:
        """获取设备的连接 ID"""
        return self.device_connections.get(device_id)

    def get_user_connection_id(self, user_id: str) -> Optional[str]:
        """获取用户的连接 ID"""
        return self.user_connections.get(user_id)

    def is_device_online(self, device_id: str) -> bool:
        """检查设备是否在线"""
        return device_id in self.device_connections

    def get_connection_count(self) -> int:
        """获取活动连接数"""
        return len(self.active_connections)

    async def send_with_ack(self, connection_id: str, message: dict) -> bool:
        """发送需要确认的消息"""
        ack_manager = self.ack_managers.get(connection_id)
        if ack_manager:
            return await ack_manager.send_with_ack(message)
        return False

    def handle_ack(self, connection_id: str, message_id: str):
        """处理 ACK 确认"""
        ack_manager = self.ack_managers.get(connection_id)
        if ack_manager:
            ack_manager.handle_ack(message_id)

    def get_pending_ack_count(self, connection_id: str) -> int:
        """获取待确认消息数量"""
        ack_manager = self.ack_managers.get(connection_id)
        if ack_manager:
            return ack_manager.get_pending_count()
        return 0


# 全局连接管理器实例
connection_manager = ConnectionManager()
