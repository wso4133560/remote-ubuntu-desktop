"""客户端主程序"""
import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

from .core.config import load_config
from .core.device_manager import DeviceManager
from .core.signaling_client import SignalingClient


class RemoteControlClient:
    """远程控制客户端"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.device_manager: Optional[DeviceManager] = None
        self.signaling_client: Optional[SignalingClient] = None
        self.running = False

    async def start(self):
        """启动客户端"""
        print("Starting Remote Control Client...")

        self.device_manager = DeviceManager(self.config, self.config_path)
        await self.device_manager.initialize()

        self.signaling_client = SignalingClient(
            self.config,
            self.device_manager,
        )

        await self.signaling_client.connect()

        self.running = True
        print("Client started successfully")

        while self.running:
            await asyncio.sleep(1)

    async def stop(self):
        """停止客户端"""
        print("Stopping Remote Control Client...")
        self.running = False

        if self.signaling_client:
            await self.signaling_client.disconnect()

        if self.device_manager:
            await self.device_manager.cleanup()

        print("Client stopped")

    def handle_signal(self, sig):
        """处理信号"""
        print(f"Received signal {sig}, shutting down...")
        asyncio.create_task(self.stop())


async def main():
    """主函数"""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "/etc/remote-control/client.conf"

    client = RemoteControlClient(config_path)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: client.handle_signal(s))

    try:
        await client.start()
    except KeyboardInterrupt:
        pass
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
