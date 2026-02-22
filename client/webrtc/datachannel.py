"""DataChannel 管理"""
import asyncio
import json
from typing import Optional, Callable
from aiortc import RTCDataChannel


class DataChannelManager:
    """DataChannel 管理器"""

    def __init__(self):
        self.control_channel: Optional[RTCDataChannel] = None
        self.file_transfer_channel: Optional[RTCDataChannel] = None
        self.on_control_message: Optional[Callable] = None
        self.on_file_message: Optional[Callable] = None

    def setup_control_channel(self, channel: RTCDataChannel):
        """设置控制通道"""
        self.control_channel = channel

        @channel.on("open")
        def on_open():
            print("Control DataChannel opened")

        @channel.on("message")
        def on_message(message):
            if self.on_control_message:
                try:
                    data = json.loads(message)
                    asyncio.create_task(self.on_control_message(data))
                except Exception as e:
                    print(f"Error handling control message: {e}")

        @channel.on("close")
        def on_close():
            print("Control DataChannel closed")

    def setup_file_transfer_channel(self, channel: RTCDataChannel):
        """设置文件传输通道"""
        self.file_transfer_channel = channel

        @channel.on("open")
        def on_open():
            print("File transfer DataChannel opened")

        @channel.on("message")
        def on_message(message):
            if self.on_file_message:
                asyncio.create_task(self.on_file_message(message))

        @channel.on("close")
        def on_close():
            print("File transfer DataChannel closed")

    def send_control_message(self, message: dict):
        """发送控制消息"""
        if self.control_channel and self.control_channel.readyState == "open":
            self.control_channel.send(json.dumps(message))
        else:
            print("Control channel not ready")

    def send_file_chunk(self, data: bytes):
        """发送文件块"""
        if self.file_transfer_channel and self.file_transfer_channel.readyState == "open":
            self.file_transfer_channel.send(data)
        else:
            print("File transfer channel not ready")

    def set_control_message_handler(self, handler: Callable):
        """设置控制消息处理器"""
        self.on_control_message = handler

    def set_file_message_handler(self, handler: Callable):
        """设置文件消息处理器"""
        self.on_file_message = handler
