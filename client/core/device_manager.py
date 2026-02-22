"""设备管理器"""
import secrets
import platform
from typing import Optional
import aiohttp

from .config import ClientConfig, save_config


class DeviceManager:
    """设备管理器"""

    def __init__(self, config: ClientConfig, config_path: str):
        self.config = config
        self.config_path = config_path
        self.device_id: Optional[str] = config.device_id
        self.device_token: Optional[str] = config.device_token

    async def initialize(self):
        """初始化设备"""
        if not self.device_id or not self.device_token:
            await self.register_device()
        else:
            print(f"Device already registered: {self.device_id}")

    async def register_device(self):
        """注册设备"""
        print("Registering device...")

        os_info = f"{platform.system()} {platform.release()}"
        capabilities = "screen_capture,audio_capture,input_injection,clipboard_sync,file_transfer"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.config.server_url}/api/v1/devices/register",
                json={
                    "device_name": self.config.device_name,
                    "os_info": os_info,
                    "capabilities": capabilities,
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.device_id = data["device_id"]
                    self.device_token = data["device_token"]

                    self.config.device_id = self.device_id
                    self.config.device_token = self.device_token
                    save_config(self.config, self.config_path)

                    print(f"Device registered: {self.device_id}")
                else:
                    raise Exception(f"Failed to register device: {resp.status}")

    async def cleanup(self):
        """清理资源"""
        print("Cleaning up device manager...")
