"""卡键恢复机制"""
import asyncio
import time
from typing import Dict, Set


class StuckKeyRecovery:
    """卡键恢复机制"""

    def __init__(self, injector):
        self.injector = injector
        self.pressed_keys: Dict[int, float] = {}
        self.max_key_duration = 10.0
        self.monitor_task: Optional[asyncio.Task] = None
        self.running = False

    async def start_monitoring(self):
        """开始监控"""
        if self.running:
            return

        self.running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        print("Stuck key recovery monitoring started")

    async def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None

        await self.release_all_keys()
        print("Stuck key recovery monitoring stopped")

    def record_key_press(self, keycode: int):
        """记录按键按下"""
        self.pressed_keys[keycode] = time.time()

    def record_key_release(self, keycode: int):
        """记录按键释放"""
        if keycode in self.pressed_keys:
            del self.pressed_keys[keycode]

    async def _monitor_loop(self):
        """监控循环"""
        try:
            while self.running:
                current_time = time.time()
                stuck_keys = []

                for keycode, press_time in self.pressed_keys.items():
                    if current_time - press_time > self.max_key_duration:
                        stuck_keys.append(keycode)

                for keycode in stuck_keys:
                    print(f"Releasing stuck key: {keycode}")
                    await self.injector.inject_key(keycode, False)
                    del self.pressed_keys[keycode]

                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in stuck key monitor: {e}")

    async def release_all_keys(self):
        """释放所有按键"""
        for keycode in list(self.pressed_keys.keys()):
            try:
                await self.injector.inject_key(keycode, False)
            except Exception as e:
                print(f"Failed to release key {keycode}: {e}")

        self.pressed_keys.clear()
        print("All keys released")

    def get_pressed_keys(self) -> Set[int]:
        """获取当前按下的按键"""
        return set(self.pressed_keys.keys())
