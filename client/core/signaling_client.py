"""信令客户端"""
import asyncio
import secrets
from datetime import datetime
from typing import Optional
import websockets
import json

from .config import ClientConfig
from .device_manager import DeviceManager
from ..protocol.message_types import MessageType
from ..protocol.states import SessionState
from ..monitoring.performance import PerformanceMonitor


class SignalingClient:
    """信令客户端"""

    def __init__(self, config: ClientConfig, device_manager: DeviceManager):
        self.config = config
        self.device_manager = device_manager
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.session_state = SessionState.IDLE
        self.current_session_id: Optional[str] = None
        self.reconnect_attempts = 0
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.webrtc_manager = None
        self.input_injector = None
        self.clipboard_manager = None
        self.file_transfer_manager = None

    async def connect(self):
        """连接到服务器"""
        ws_url = self.config.server_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws?token={self.device_manager.device_token}"

        print(f"Connecting to: {ws_url}")
        try:
            self.websocket = await websockets.connect(ws_url)
            print("Connected to signaling server")
            self.reconnect_attempts = 0

            asyncio.create_task(self.receive_messages())

        except Exception as e:
            print(f"Failed to connect: {e}")
            import traceback
            traceback.print_exc()
            await self.handle_reconnect()

    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

    async def handle_reconnect(self):
        """处理重连"""
        if self.reconnect_attempts >= self.config.max_reconnect_attempts:
            print("Max reconnect attempts reached")
            return

        self.reconnect_attempts += 1
        delay = min(2 ** self.reconnect_attempts, 32)
        print(f"Reconnecting in {delay} seconds... (attempt {self.reconnect_attempts})")

        await asyncio.sleep(delay)
        await self.connect()

    async def receive_messages(self):
        """接收消息"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self.handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
            await self.handle_reconnect()
        except Exception as e:
            print(f"Error receiving message: {e}")

    async def handle_message(self, message: dict):
        """处理消息"""
        try:
            msg_type = message.get("type")
            print(f"[CLIENT] Received message type: {msg_type}, full message: {message}", flush=True)

            if msg_type == MessageType.HEARTBEAT:
                await self.send_heartbeat_ack()

            elif msg_type == MessageType.SESSION_REQUEST:
                await self.handle_session_request(message)

            elif msg_type == MessageType.SESSION_END:
                await self.handle_session_end(message)

            elif msg_type == MessageType.SDP_OFFER:
                await self.handle_sdp_offer(message)

            elif msg_type == MessageType.ICE_CANDIDATE:
                await self.handle_ice_candidate(message)

            elif msg_type == "error":
                print(f"[CLIENT] ERROR message from server: {message}", flush=True)
        except Exception as e:
            print(f"[CLIENT] ERROR in handle_message: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def send_message(self, message: dict):
        """发送消息"""
        if self.websocket:
            await self.websocket.send(json.dumps(message))

    async def send_heartbeat_ack(self):
        """发送心跳确认"""
        message = {
            "type": MessageType.HEARTBEAT_ACK,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
        }
        await self.send_message(message)

    async def handle_session_request(self, message: dict):
        """处理会话请求"""
        session_id = message.get("session_id")

        # 如果当前有活动会话，先清理
        if self.session_state != SessionState.IDLE:
            print(f"Warning: Received new session request while in state {self.session_state}, cleaning up...")
            # 清理旧会话
            if hasattr(self, 'webrtc_manager') and self.webrtc_manager:
                await self.webrtc_manager.close()
                self.webrtc_manager = None
            self.session_state = SessionState.IDLE
            self.current_session_id = None

        self.current_session_id = session_id
        self.session_state = SessionState.PENDING

        await self.accept_session(session_id)

    async def accept_session(self, session_id: str):
        """接受会话"""
        message = {
            "type": MessageType.SESSION_ACCEPT,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
        }
        await self.send_message(message)
        self.session_state = SessionState.NEGOTIATING

    async def reject_session(self, session_id: str, reason: str):
        """拒绝会话"""
        message = {
            "type": MessageType.SESSION_REJECT,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "reason": reason,
        }
        await self.send_message(message)

    async def handle_session_end(self, message: dict):
        """处理会话结束"""
        # 停止性能监控
        if self.performance_monitor:
            await self.performance_monitor.stop_monitoring()
            self.performance_monitor = None

        # 停止剪贴板监控
        if hasattr(self, 'clipboard_manager') and self.clipboard_manager:
            await self.clipboard_manager.stop_monitoring()
            self.clipboard_manager = None

        # 清理输入注入器
        if hasattr(self, 'input_injector'):
            self.input_injector = None

        # 清理文件传输
        if hasattr(self, 'file_transfer_manager'):
            self.file_transfer_manager = None

        # 关闭 WebRTC
        if hasattr(self, 'webrtc_manager') and self.webrtc_manager:
            await self.webrtc_manager.close()
            self.webrtc_manager = None

        self.session_state = SessionState.IDLE
        self.current_session_id = None
        print("Session ended")

    async def handle_sdp_offer(self, message: dict):
        """处理 SDP Offer"""
        print("Received SDP offer", flush=True)
        session_id = message.get("session_id")
        sdp = message.get("sdp")

        if session_id != self.current_session_id:
            print(f"Session ID mismatch: {session_id} != {self.current_session_id}", flush=True)
            return

        try:
            from ..webrtc.manager import WebRTCManager
            from ..capture.wayland_capture import WaylandVideoTrack

            print("Initializing WebRTC manager...", flush=True)
            self.webrtc_manager = WebRTCManager(session_id)
            await self.webrtc_manager.initialize()
            self.webrtc_manager.set_ice_candidate_handler(
                lambda candidate: self.send_ice_candidate_from_client(session_id, candidate)
            )

            print("Initializing video capture...", flush=True)
            video_track = WaylandVideoTrack(width=1280, height=720, fps=30)
            await video_track.initialize()
            self.webrtc_manager.add_video_track(video_track)

            print("Creating SDP answer...", flush=True)
            answer_sdp = await self.webrtc_manager.handle_offer(sdp)

            print("Sending SDP answer...", flush=True)
            await self.send_sdp_answer(session_id, answer_sdp)
            self.session_state = SessionState.ACTIVE
            print("SDP answer sent successfully", flush=True)

            # 以下模块是可选增强能力，不应阻塞 SDP answer
            try:
                from ..input.injector import InputInjector
                print("Initializing input injector...", flush=True)
                self.input_injector = InputInjector()
                input_ready = await self.input_injector.initialize()
                if not input_ready:
                    print("Input injector disabled: no supported backend available", flush=True)
                    self.input_injector = None
            except Exception as e:
                print(f"Warning: input injector unavailable: {e}", flush=True)
                self.input_injector = None

            try:
                from ..clipboard.manager import ClipboardManager
                print("Initializing clipboard manager...", flush=True)
                self.clipboard_manager = ClipboardManager()
                clipboard_ready = await self.clipboard_manager.initialize()
                if clipboard_ready:
                    self.clipboard_manager.set_change_handler(self._handle_clipboard_change)
                    await self.clipboard_manager.start_monitoring()
                else:
                    print("Clipboard manager disabled: no clipboard backend available", flush=True)
                    self.clipboard_manager = None
            except Exception as e:
                print(f"Warning: clipboard manager unavailable: {e}", flush=True)
                self.clipboard_manager = None

            try:
                from ..file_transfer.manager import FileTransferManager
                print("Initializing file transfer...", flush=True)
                self.file_transfer_manager = FileTransferManager(
                    self.webrtc_manager.datachannel_manager
                )
                await self.file_transfer_manager.initialize()
            except Exception as e:
                print(f"Warning: file transfer unavailable: {e}", flush=True)
                self.file_transfer_manager = None

            try:
                print("Initializing performance monitor...", flush=True)
                self.performance_monitor = PerformanceMonitor(sample_interval=5)
                self.performance_monitor.set_metrics_handler(self._handle_metrics_update)
                await self.performance_monitor.start_monitoring()
            except Exception as e:
                print(f"Warning: performance monitor unavailable: {e}", flush=True)
                self.performance_monitor = None

            self.webrtc_manager.datachannel_manager.set_control_message_handler(
                self._handle_control_message
            )
        except Exception as e:
            print(f"ERROR in handle_sdp_offer: {e}", flush=True)
            import traceback
            traceback.print_exc()
            raise

    async def _handle_control_message(self, message: dict):
        """处理控制消息"""
        msg_type = message.get("type")

        if msg_type == "mouse_move":
            x = message.get("x")
            y = message.get("y")
            if self.input_injector:
                await self.input_injector.inject_mouse_move(x, y)

        elif msg_type == "mouse_button":
            button = message.get("button")
            pressed = message.get("pressed")
            if self.input_injector:
                await self.input_injector.inject_mouse_button(button, pressed)

        elif msg_type == "key":
            key_code = message.get("key_code")
            pressed = message.get("pressed")
            if self.input_injector:
                await self.input_injector.inject_key(key_code, pressed)

        elif msg_type == "clipboard":
            content = message.get("content")
            if self.clipboard_manager:
                await self.clipboard_manager.set_clipboard(content)

    async def _handle_clipboard_change(self, content: str):
        """处理剪贴板变化"""
        # 通过 DataChannel 发送剪贴板内容
        if self.webrtc_manager:
            message = {
                "type": "clipboard",
                "content": content,
            }
            self.webrtc_manager.datachannel_manager.send_control_message(message)

    async def _handle_metrics_update(self, metrics: dict):
        """处理性能指标更新"""
        if not self.current_session_id:
            return

        if self.performance_monitor:
            degradation = self.performance_monitor.check_degradation()
            if degradation:
                print(f"Performance degradation detected: {degradation}")

        process_metrics = metrics.get("process", {})
        message = {
            "type": MessageType.METRICS_UPDATE,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": self.current_session_id,
            "fps": 0.0,
            "bitrate": 0,
            "rtt": 0.0,
            "packet_loss": 0.0,
            "cpu_usage": max(0.0, min(1.0, process_metrics.get("cpu_percent", 0) / 100.0)),
        }
        await self.send_message(message)

    async def send_sdp_answer(self, session_id: str, sdp: str):
        """发送 SDP Answer"""
        message = {
            "type": MessageType.SDP_ANSWER,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "sdp": sdp,
        }
        await self.send_message(message)

    async def send_ice_candidate_from_client(self, session_id: str, candidate):
        """从客户端发送 ICE 候选"""
        message = {
            "type": MessageType.ICE_CANDIDATE,
            "message_id": secrets.token_urlsafe(16),
            "timestamp": datetime.utcnow().timestamp(),
            "session_id": session_id,
            "candidate": candidate.candidate,
            "sdp_mid": candidate.sdpMid,
            "sdp_m_line_index": candidate.sdpMLineIndex,
        }
        await self.send_message(message)

    async def handle_ice_candidate(self, message: dict):
        """处理 ICE 候选"""
        print("Received ICE candidate")
        session_id = message.get("session_id")

        if session_id != self.current_session_id or not hasattr(self, 'webrtc_manager'):
            return

        candidate = message.get("candidate")
        sdp_mid = message.get("sdp_mid")
        sdp_m_line_index = message.get("sdp_m_line_index")

        await self.webrtc_manager.add_ice_candidate(candidate, sdp_mid, sdp_m_line_index)
