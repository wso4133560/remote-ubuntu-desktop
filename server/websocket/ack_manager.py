"""消息确认和重传机制"""
import asyncio
import time
from typing import Dict, Optional, Callable
from dataclasses import dataclass


@dataclass
class PendingMessage:
    """待确认消息"""
    message_id: str
    message: dict
    sent_at: float
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 5.0


class AckManager:
    """ACK 管理器"""

    def __init__(self, send_callback: Callable):
        self.send_callback = send_callback
        self.pending_messages: Dict[str, PendingMessage] = {}
        self.monitor_task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self):
        """启动监控"""
        if self.running:
            return

        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """停止监控"""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None

    async def send_with_ack(self, message: dict) -> bool:
        """发送需要确认的消息"""
        message_id = message.get("message_id")
        if not message_id:
            return False

        pending = PendingMessage(
            message_id=message_id,
            message=message,
            sent_at=time.time()
        )

        self.pending_messages[message_id] = pending

        await self.send_callback(message)
        return True

    def handle_ack(self, message_id: str):
        """处理 ACK 确认"""
        if message_id in self.pending_messages:
            del self.pending_messages[message_id]

    async def _monitor_loop(self):
        """监控超时和重传"""
        try:
            while self.running:
                current_time = time.time()
                to_retry = []
                to_remove = []

                for message_id, pending in self.pending_messages.items():
                    elapsed = current_time - pending.sent_at

                    if elapsed > pending.timeout:
                        if pending.retry_count < pending.max_retries:
                            to_retry.append(message_id)
                        else:
                            to_remove.append(message_id)
                            print(f"Message {message_id} failed after {pending.max_retries} retries")

                for message_id in to_retry:
                    pending = self.pending_messages[message_id]
                    pending.retry_count += 1
                    pending.sent_at = current_time
                    await self.send_callback(pending.message)
                    print(f"Retrying message {message_id} (attempt {pending.retry_count})")

                for message_id in to_remove:
                    del self.pending_messages[message_id]

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in ACK monitor: {e}")

    def get_pending_count(self) -> int:
        """获取待确认消息数量"""
        return len(self.pending_messages)
