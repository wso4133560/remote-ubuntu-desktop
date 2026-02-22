"""音频源检测"""
import asyncio
import subprocess
from typing import List, Optional, Dict


class AudioSourceDetector:
    """音频源检测器"""

    def __init__(self):
        self.sources: List[Dict] = []

    async def detect_sources(self) -> List[Dict]:
        """检测音频源"""
        if await self._check_pipewire():
            return await self._detect_pipewire_sources()
        elif await self._check_pulseaudio():
            return await self._detect_pulseaudio_sources()
        else:
            print("No audio system detected")
            return []

    async def _check_pipewire(self) -> bool:
        """检查 PipeWire"""
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

    async def _check_pulseaudio(self) -> bool:
        """检查 PulseAudio"""
        try:
            result = await asyncio.create_subprocess_exec(
                "pactl",
                "info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(result.wait(), timeout=2.0)
            return result.returncode == 0
        except Exception:
            return False

    async def _detect_pipewire_sources(self) -> List[Dict]:
        """检测 PipeWire 音频源"""
        try:
            result = await asyncio.create_subprocess_exec(
                "pw-cli",
                "list-objects",
                "Node",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await result.communicate()

            if result.returncode == 0:
                sources = []
                lines = stdout.decode().split('\n')
                current_source = {}

                for line in lines:
                    line = line.strip()
                    if line.startswith('id'):
                        if current_source and current_source.get('media_class') == 'Audio/Source':
                            sources.append(current_source)
                        current_source = {'id': line.split()[1].rstrip(','), 'type': 'pipewire'}

                    elif 'node.name' in line:
                        current_source['name'] = line.split('=')[1].strip().strip('"')
                    elif 'node.description' in line:
                        current_source['description'] = line.split('=')[1].strip().strip('"')
                    elif 'media.class' in line:
                        current_source['media_class'] = line.split('=')[1].strip().strip('"')

                if current_source and current_source.get('media_class') == 'Audio/Source':
                    sources.append(current_source)

                self.sources = sources
                print(f"Detected {len(sources)} PipeWire audio sources")
                return sources

        except Exception as e:
            print(f"Failed to detect PipeWire sources: {e}")

        return []

    async def _detect_pulseaudio_sources(self) -> List[Dict]:
        """检测 PulseAudio 音频源"""
        try:
            result = await asyncio.create_subprocess_exec(
                "pactl",
                "list",
                "sources",
                "short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await result.communicate()

            if result.returncode == 0:
                sources = []
                lines = stdout.decode().strip().split('\n')

                for line in lines:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        sources.append({
                            'id': parts[0],
                            'name': parts[1],
                            'type': 'pulseaudio'
                        })

                self.sources = sources
                print(f"Detected {len(sources)} PulseAudio sources")
                return sources

        except Exception as e:
            print(f"Failed to detect PulseAudio sources: {e}")

        return []

    def get_default_source(self) -> Optional[Dict]:
        """获取默认音频源"""
        if self.sources:
            return self.sources[0]
        return None

    def get_source_by_id(self, source_id: str) -> Optional[Dict]:
        """根据 ID 获取音频源"""
        for source in self.sources:
            if source['id'] == source_id:
                return source
        return None
