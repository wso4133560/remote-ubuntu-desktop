"""设备管理器"""
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
            exists = await self._device_exists_on_server(self.device_id)
            if exists is False:
                print(
                    f"Device {self.device_id} not found on server, re-registering..."
                )
                self.device_id = None
                self.device_token = None
                self.config.device_id = None
                self.config.device_token = None
                await self.register_device()

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

    async def _device_exists_on_server(self, device_id: str) -> Optional[bool]:
        """检查设备是否存在于服务端，None 表示无法判断（网络/服务异常）"""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.config.server_url}/api/v1/devices/{device_id}"
                ) as resp:
                    if resp.status == 200:
                        return True
                    if resp.status == 404:
                        return False
                    print(f"Warning: unexpected status when checking device: {resp.status}")
                    return None
        except Exception as e:
            print(f"Warning: failed to verify existing device on server: {e}")
            return None

    async def cleanup(self):
        """清理资源"""
        print("Cleaning up device manager...")
