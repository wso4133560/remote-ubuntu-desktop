"""PipeWire 流处理"""
import asyncio
from typing import Optional, Callable
import subprocess


class PipeWireStream:
    """PipeWire 流处理器"""

    def __init__(self, node_id: int):
        self.node_id = node_id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.frame_callback: Optional[Callable] = None
        self.running = False

    async def start(self, width: int = 1920, height: int = 1080, fps: int = 30) -> bool:
        """启动流处理"""
        try:
            cmd = [
                "pw-record",
                "--target", str(self.node_id),
                "--rate", str(fps),
                "-"
            ]

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            self.running = True
            asyncio.create_task(self._read_stream())

            print(f"PipeWire stream started for node {self.node_id}")
            return True

        except Exception as e:
            print(f"Failed to start PipeWire stream: {e}")
            return False

    async def _read_stream(self):
        """读取流数据"""
        try:
            while self.running and self.process:
                chunk = await self.process.stdout.read(65536)
                if not chunk:
                    break

                if self.frame_callback:
                    await self.frame_callback(chunk)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error reading stream: {e}")

    async def stop(self):
        """停止流处理"""
        self.running = False

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                print(f"Error stopping stream: {e}")

            self.process = None

        print("PipeWire stream stopped")

    def set_frame_callback(self, callback: Callable):
        """设置帧回调"""
        self.frame_callback = callback

    @staticmethod
    async def check_pipewire() -> bool:
        """检查 PipeWire 是否可用"""
        try:
            result = await asyncio.create_subprocess_exec(
                "pw-cli",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            await asyncio.wait_for(result.wait(), timeout=2.0)
            return result.returncode == 0

        except Exception:
            return False

    @staticmethod
    async def list_nodes() -> list:
        """列出 PipeWire 节点"""
        try:
            result = await asyncio.create_subprocess_exec(
                "pw-cli",
                "list-objects",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await result.communicate()

            if result.returncode == 0:
                nodes = []
                lines = stdout.decode().split('\n')
                current_node = {}

                for line in lines:
                    line = line.strip()
                    if line.startswith('id'):
                        if current_node:
                            nodes.append(current_node)
                        current_node = {'id': line.split()[1].rstrip(',')}
                    elif 'node.name' in line:
                        current_node['name'] = line.split('=')[1].strip().strip('"')

                if current_node:
                    nodes.append(current_node)

                return nodes

        except Exception as e:
            print(f"Failed to list nodes: {e}")

        return []
