"""客户端配置管理"""
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class ClientConfig(BaseModel):
    """客户端配置"""

    server_url: str = Field(..., description="服务器 URL")
    device_name: str = Field(..., description="设备名称")
    device_id: Optional[str] = Field(None, description="设备 ID")
    device_token: Optional[str] = Field(None, description="设备令牌")

    heartbeat_interval: int = Field(30, description="心跳间隔（秒）")
    reconnect_delay: int = Field(5, description="重连延迟（秒）")
    max_reconnect_attempts: int = Field(6, description="最大重连次数")

    video_width: int = Field(1920, description="视频宽度")
    video_height: int = Field(1080, description="视频高度")
    video_fps: int = Field(60, description="视频帧率")
    video_bitrate: int = Field(2000000, description="视频比特率")

    enable_audio: bool = Field(True, description="启用音频")
    enable_clipboard: bool = Field(True, description="启用剪贴板同步")
    enable_file_transfer: bool = Field(True, description="启用文件传输")


def load_config(config_path: str) -> ClientConfig:
    """加载配置文件"""
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        data = json.load(f)

    return ClientConfig(**data)


def save_config(config: ClientConfig, config_path: str) -> None:
    """保存配置文件"""
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
