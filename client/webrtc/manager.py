"""WebRTC 管理器"""
import asyncio
from typing import Optional, Callable
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.sdp import candidate_from_sdp
from aiortc.contrib.media import MediaRelay

from ..protocol.message_types import MessageType
from ..protocol.states import SessionState
from .datachannel import DataChannelManager


class WebRTCManager:
    """WebRTC 连接管理器"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.relay = MediaRelay()
        self.video_track: Optional[MediaStreamTrack] = None
        self.audio_track: Optional[MediaStreamTrack] = None
        self.datachannel_manager = DataChannelManager()
        self.on_ice_candidate: Optional[Callable] = None

    async def initialize(self):
        """初始化 PeerConnection"""
        self.peer_connection = RTCPeerConnection()

        @self.peer_connection.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate and self.on_ice_candidate:
                await self.on_ice_candidate(candidate)

        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {self.peer_connection.connectionState}")

        @self.peer_connection.on("datachannel")
        def on_datachannel(channel):
            print(f"DataChannel received: {channel.label}")
            if channel.label == "control":
                self.datachannel_manager.setup_control_channel(channel)
            elif channel.label == "file-transfer":
                self.datachannel_manager.setup_file_transfer_channel(channel)

        print("WebRTC PeerConnection initialized")

    def set_ice_candidate_handler(self, handler: Callable):
        """设置 ICE 候选处理器"""
        self.on_ice_candidate = handler

    def add_video_track(self, track: MediaStreamTrack):
        """添加视频轨道"""
        self.video_track = track
        if self.peer_connection:
            self.peer_connection.addTrack(track)
            print("Added video track")

    def add_audio_track(self, track: MediaStreamTrack):
        """添加音频轨道"""
        self.audio_track = track
        if self.peer_connection:
            self.peer_connection.addTrack(track)
            print("Added audio track")

    async def handle_offer(self, sdp: str) -> str:
        """处理 SDP Offer 并生成 Answer"""
        if not self.peer_connection:
            raise Exception("PeerConnection not initialized")

        offer = RTCSessionDescription(sdp=sdp, type="offer")
        await self.peer_connection.setRemoteDescription(offer)

        answer = await self.peer_connection.createAnswer()
        await self.peer_connection.setLocalDescription(answer)

        print("Created SDP answer")
        return self.peer_connection.localDescription.sdp

    async def add_ice_candidate(self, candidate: str, sdp_mid: Optional[str], sdp_m_line_index: Optional[int]):
        """添加 ICE 候选"""
        if not self.peer_connection:
            return

        ice_candidate = candidate_from_sdp(candidate)
        ice_candidate.sdpMid = sdp_mid
        ice_candidate.sdpMLineIndex = sdp_m_line_index
        await self.peer_connection.addIceCandidate(ice_candidate)
        print("Added ICE candidate")

    async def close(self):
        """关闭连接"""
        if self.peer_connection:
            await self.peer_connection.close()
            self.peer_connection = None
        print("WebRTC connection closed")

    def get_connection_state(self) -> Optional[str]:
        """获取连接状态"""
        if self.peer_connection:
            return self.peer_connection.connectionState
        return None
