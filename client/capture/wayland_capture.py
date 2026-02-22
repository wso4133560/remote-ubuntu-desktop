"""桌面视频捕获（Wayland 检测 + X11 回退）"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import fractions
import os
import shutil
import subprocess
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

import numpy as np
from aiortc import VideoStreamTrack
from aiortc.mediastreams import MediaStreamError, VIDEO_CLOCK_RATE
from av import VideoFrame

try:
    from PIL import Image, ImageGrab, UnidentifiedImageError
except Exception:
    Image = None
    ImageGrab = None
    UnidentifiedImageError = Exception

try:
    from Xlib import display as XDisplay
except Exception:
    XDisplay = None

try:
    from mss import mss as MSS
except Exception:
    MSS = None


class WaylandCapture:
    """Wayland 屏幕捕获管理器"""

    def __init__(self):
        self.compositor_type: Optional[str] = None
        self.capture_method: Optional[str] = None

    async def detect_compositor(self) -> str:
        """检测 Wayland compositor 类型"""
        try:
            session_type = os.getenv("XDG_SESSION_TYPE", "").lower()
            if "wayland" not in session_type:
                raise Exception("Not running on Wayland")

            # 检测 compositor 类型
            # 检查 GNOME
            result = subprocess.run(
                ["pgrep", "-x", "gnome-shell"],
                capture_output=True
            )
            if result.returncode == 0:
                self.compositor_type = "gnome"
                self.capture_method = "xdg-desktop-portal"
                return "GNOME (Mutter)"

            # 检查 wlroots-based (Sway, etc.)
            result = subprocess.run(
                ["pgrep", "-x", "sway"],
                capture_output=True
            )
            if result.returncode == 0:
                self.compositor_type = "wlroots"
                self.capture_method = "wlr-screencopy"
                return "Sway (wlroots)"

            # 未知 compositor
            self.compositor_type = "unknown"
            self.capture_method = None
            return "Unknown"

        except Exception as e:
            print(f"Error detecting compositor: {e}")
            return "Error"

    def check_dependencies(self) -> dict:
        """检查依赖项"""
        dependencies = {
            "xdg-desktop-portal": False,
            "xdg-desktop-portal-gnome": False,
            "xdg-desktop-portal-wlr": False,
            "pipewire": False,
            "grim": False,
        }

        dependencies["xdg-desktop-portal"] = shutil.which("xdg-desktop-portal") is not None
        dependencies["xdg-desktop-portal-gnome"] = shutil.which("xdg-desktop-portal-gnome") is not None
        dependencies["xdg-desktop-portal-wlr"] = shutil.which("xdg-desktop-portal-wlr") is not None
        dependencies["pipewire"] = shutil.which("pipewire") is not None
        dependencies["grim"] = shutil.which("grim") is not None

        return dependencies

    async def initialize(self) -> bool:
        """初始化屏幕捕获"""
        compositor = await self.detect_compositor()
        print(f"Detected compositor: {compositor}")

        dependencies = self.check_dependencies()
        print("Dependencies:")
        for dep, available in dependencies.items():
            status = "✓" if available else "✗"
            print(f"  {status} {dep}")

        if self.capture_method == "xdg-desktop-portal":
            return await self._init_portal_capture()
        elif self.capture_method == "wlr-screencopy":
            return await self._init_wlr_capture()
        else:
            print("No supported capture method available")
            return False

    async def _init_portal_capture(self) -> bool:
        """初始化 XDG Desktop Portal 捕获"""
        print("Initializing XDG Desktop Portal capture...")
        # TODO: 后续可接入 xdg-desktop-portal + PipeWire
        return False

    async def _init_wlr_capture(self) -> bool:
        """初始化 wlr-screencopy 捕获"""
        print("Initializing wlr-screencopy capture...")
        # TODO: 实现 wlr-screencopy 捕获
        # 需要使用 Wayland 协议
        return False


class WaylandVideoTrack(VideoStreamTrack):
    """桌面视频轨道（优先真实屏幕，失败后测试图案）"""

    def __init__(self, width=1920, height=1080, fps=30):
        super().__init__()
        self.width = width
        self.height = height
        self.fps = max(5, int(fps))
        self.capture = WaylandCapture()
        self.initialized = False
        self.backend = "test-pattern"
        self.display: Optional[str] = None
        self.xauthority: Optional[str] = None
        self._last_capture_error_at = 0.0
        self._frame_count = 0
        self._x11_pointer_display = None
        self._x11_screen_width = 1
        self._x11_screen_height = 1
        self._latest_frame: Optional[np.ndarray] = None
        self._capture_task: Optional[asyncio.Task] = None
        self._capture_executor: Optional[ThreadPoolExecutor] = None
        self._frame_interval = 1.0 / self.fps
        self._timestamp: Optional[int] = None
        self._start_time: Optional[float] = None
        self._mss_instance = None
        self._mss_monitor = None
        self._mss_owner_thread_id: Optional[int] = None

    async def initialize(self):
        """初始化捕获"""
        wayland_ready = await self.capture.initialize()
        if wayland_ready:
            print("Wayland backend detected but not fully implemented, trying X11 capture fallback")

        self.backend = self._select_capture_backend()
        self.initialized = self.backend != "test-pattern"
        if self.backend.startswith("x11-"):
            self._init_x11_pointer_overlay()
        print(f"Video capture backend: {self.backend}")
        if not self.initialized:
            print("Warning: desktop capture not available, using test pattern")
            return

        self._capture_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screen-capture")
        self._capture_task = asyncio.create_task(self._capture_loop())

    async def recv(self):
        """接收视频帧"""
        pts, time_base = await self._next_frame_timestamp()

        frame_data = self._latest_frame
        if frame_data is None:
            frame_data = self._generate_test_pattern_frame()

        frame = VideoFrame.from_ndarray(frame_data, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    async def _capture_loop(self):
        loop = asyncio.get_running_loop()
        try:
            while self.readyState == "live":
                loop_started = time.perf_counter()
                frame_data = None

                try:
                    if self.backend == "x11-mss":
                        frame_data = await loop.run_in_executor(
                            self._capture_executor,
                            self._capture_with_mss,
                        )
                    elif self.backend == "x11-imagegrab":
                        frame_data = await loop.run_in_executor(
                            self._capture_executor,
                            self._capture_with_imagegrab,
                        )
                    elif self.backend == "x11-import":
                        frame_data = await loop.run_in_executor(
                            self._capture_executor,
                            self._capture_with_import,
                        )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    now = time.time()
                    if now - self._last_capture_error_at > 5:
                        print(f"Screen capture failed on backend={self.backend}: {e}")
                        self._last_capture_error_at = now

                if frame_data is not None:
                    if self.backend.startswith("x11-"):
                        self._overlay_x11_cursor(frame_data)
                    self._latest_frame = frame_data

                elapsed = time.perf_counter() - loop_started
                sleep_time = self._frame_interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
        finally:
            if self._capture_executor is not None:
                try:
                    await loop.run_in_executor(self._capture_executor, self._close_mss_instance)
                except Exception:
                    pass

    async def _next_frame_timestamp(self):
        if self.readyState != "live":
            raise MediaStreamError

        frame_step = int((1 / self.fps) * VIDEO_CLOCK_RATE)
        if self._timestamp is None:
            self._start_time = time.time()
            self._timestamp = 0
        else:
            self._timestamp += frame_step
            wait = self._start_time + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
            if wait > 0:
                await asyncio.sleep(wait)

        return self._timestamp, fractions.Fraction(1, VIDEO_CLOCK_RATE)

    def _select_capture_backend(self) -> str:
        context = self._find_x11_context()
        if context:
            self.display, self.xauthority = context
            self._apply_x11_env()

            if MSS is not None:
                try:
                    self._probe_mss_backend()
                    return "x11-mss"
                except Exception as e:
                    print(f"MSS backend unavailable: {e}")

            if ImageGrab is not None:
                try:
                    self._capture_with_imagegrab()
                    return "x11-imagegrab"
                except Exception as e:
                    print(f"ImageGrab backend unavailable: {e}")

            if shutil.which("import") is not None:
                try:
                    self._capture_with_import()
                    return "x11-import"
                except Exception as e:
                    print(f"ImageMagick import backend unavailable: {e}")

        return "test-pattern"

    def _find_x11_context(self) -> Optional[tuple[str, Optional[str]]]:
        display_candidates = []

        x11_dir = Path("/tmp/.X11-unix")
        if x11_dir.exists():
            sockets = sorted(x11_dir.glob("X*"))
            for socket in sockets:
                suffix = socket.name[1:]
                if suffix.isdigit():
                    display = f":{suffix}"
                    if display not in display_candidates:
                        display_candidates.append(display)

        env_display = os.getenv("DISPLAY")
        if env_display and env_display not in display_candidates:
            display_candidates.append(env_display)

        if not display_candidates:
            return None

        xauth_candidates = []
        env_xauth = os.getenv("XAUTHORITY")
        if env_xauth:
            xauth_candidates.append(env_xauth)

        gdm_xauth = f"/run/user/{os.getuid()}/gdm/Xauthority"
        if gdm_xauth not in xauth_candidates:
            xauth_candidates.append(gdm_xauth)

        home_xauth = str(Path.home() / ".Xauthority")
        if home_xauth not in xauth_candidates:
            xauth_candidates.append(home_xauth)

        existing_xauth = [p for p in xauth_candidates if Path(p).exists()]
        if not existing_xauth:
            existing_xauth = [None]

        for display in display_candidates:
            for xauth in existing_xauth:
                if self._can_open_display(display, xauth):
                    return display, xauth

        # 如果检测命令不可用，至少返回环境里给的 DISPLAY 让运行时再尝试
        return display_candidates[0], existing_xauth[0]

    def _can_open_display(self, display: str, xauth: Optional[str]) -> bool:
        if shutil.which("xdpyinfo") is None:
            return True
        env = os.environ.copy()
        env["DISPLAY"] = display
        if xauth:
            env["XAUTHORITY"] = xauth
        else:
            env.pop("XAUTHORITY", None)
        result = subprocess.run(
            ["xdpyinfo"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        return result.returncode == 0

    def _apply_x11_env(self):
        if self.display:
            os.environ["DISPLAY"] = self.display
        if self.xauthority:
            os.environ["XAUTHORITY"] = self.xauthority

    def _init_x11_pointer_overlay(self):
        if XDisplay is None:
            return

        try:
            self._apply_x11_env()
            self._x11_pointer_display = XDisplay.Display(self.display or os.environ.get("DISPLAY"))
            screen = self._x11_pointer_display.screen()
            self._x11_screen_width = max(1, int(screen.width_in_pixels))
            self._x11_screen_height = max(1, int(screen.height_in_pixels))
            print(
                "Enabled X11 cursor overlay "
                f"({self._x11_screen_width}x{self._x11_screen_height})"
            )
        except Exception as e:
            print(f"X11 cursor overlay disabled: {e}")
            self._x11_pointer_display = None

    def _overlay_x11_cursor(self, frame_data: np.ndarray):
        if self._x11_pointer_display is None:
            return

        try:
            pointer = self._x11_pointer_display.screen().root.query_pointer()
            src_x = int(pointer.root_x)
            src_y = int(pointer.root_y)
        except Exception:
            return

        x = int(src_x * self.width / max(1, self._x11_screen_width))
        y = int(src_y * self.height / max(1, self._x11_screen_height))
        x = max(0, min(self.width - 1, x))
        y = max(0, min(self.height - 1, y))
        size = max(8, min(self.width, self.height) // 80)

        self._draw_cross(frame_data, x, y, size + 1, (0, 0, 0), thickness=3)
        self._draw_cross(frame_data, x, y, size, (255, 255, 255), thickness=1)

    def _draw_cross(
        self,
        frame_data: np.ndarray,
        x: int,
        y: int,
        radius: int,
        color: tuple[int, int, int],
        thickness: int = 1,
    ):
        h, w, _ = frame_data.shape
        half = max(0, thickness // 2)

        y0 = max(0, y - half)
        y1 = min(h, y + half + 1)
        x0 = max(0, x - radius)
        x1 = min(w, x + radius + 1)
        frame_data[y0:y1, x0:x1] = color

        x0 = max(0, x - half)
        x1 = min(w, x + half + 1)
        y0 = max(0, y - radius)
        y1 = min(h, y + radius + 1)
        frame_data[y0:y1, x0:x1] = color

    def _resize_rgb(self, image):
        image = image.convert("RGB")
        if image.size != (self.width, self.height):
            if hasattr(Image, "Resampling"):
                image = image.resize((self.width, self.height), Image.Resampling.BILINEAR)
            else:
                image = image.resize((self.width, self.height), Image.BILINEAR)
        # Ensure frame is writable for cursor overlay drawing.
        return np.array(image, dtype=np.uint8, copy=True)

    def _capture_with_imagegrab(self) -> np.ndarray:
        if ImageGrab is None:
            raise RuntimeError("Pillow ImageGrab is not available")
        self._apply_x11_env()
        image = ImageGrab.grab()
        return self._resize_rgb(image)

    def _capture_with_mss(self) -> np.ndarray:
        if MSS is None:
            raise RuntimeError("mss is not available")
        self._apply_x11_env()
        thread_id = threading.get_ident()
        if self._mss_instance is None or self._mss_owner_thread_id != thread_id:
            self._close_mss_instance()
            self._mss_instance = MSS()
            if not self._mss_instance.monitors:
                raise RuntimeError("No monitor found for mss capture")
            self._mss_monitor = self._mss_instance.monitors[0]
            self._mss_owner_thread_id = thread_id

        raw = self._mss_instance.grab(self._mss_monitor)
        frame_bgra = np.asarray(raw, dtype=np.uint8)
        frame_rgb = np.ascontiguousarray(frame_bgra[:, :, :3][:, :, ::-1])

        if frame_rgb.shape[1] == self.width and frame_rgb.shape[0] == self.height:
            return frame_rgb

        if Image is None:
            return frame_rgb

        image = Image.fromarray(frame_rgb, mode="RGB")
        return self._resize_rgb(image)

    def _probe_mss_backend(self):
        if MSS is None:
            raise RuntimeError("mss is not available")
        self._apply_x11_env()
        with MSS() as mss:
            if not mss.monitors:
                raise RuntimeError("No monitor found for mss capture")
            mss.grab(mss.monitors[0])

    def _close_mss_instance(self):
        if self._mss_instance is not None:
            try:
                self._mss_instance.close()
            except Exception:
                pass
            self._mss_instance = None
            self._mss_monitor = None
            self._mss_owner_thread_id = None

    def _capture_with_import(self) -> np.ndarray:
        self._apply_x11_env()
        cmd = [
            "import",
            "-window",
            "root",
            "-resize",
            f"{self.width}x{self.height}!",
            "-depth",
            "8",
            "rgb:-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=2,
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(stderr_text.strip() or f"import exited with code {result.returncode}")

        expected_size = self.width * self.height * 3
        if len(result.stdout) != expected_size:
            if Image is None:
                raise RuntimeError(
                    f"unexpected raw frame size {len(result.stdout)}, expected {expected_size}"
                )
            try:
                image = Image.open(BytesIO(result.stdout))
            except (UnidentifiedImageError, OSError) as e:
                raise RuntimeError(f"cannot decode screenshot: {e}") from e
            return self._resize_rgb(image)

        frame_data = np.frombuffer(result.stdout, dtype=np.uint8).reshape(
            (self.height, self.width, 3)
        )
        return np.ascontiguousarray(frame_data)

    def _generate_test_pattern_frame(self) -> np.ndarray:
        """生成测试帧（仅在无法访问真实桌面时使用）"""
        frame_data = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame_data[:, :] = [40, 40, 40]
        bar_width = max(80, self.width // 10)
        offset = (self._frame_count * 8) % max(1, self.width - bar_width)
        frame_data[:, offset:offset + bar_width] = [65, 110, 185]
        self._frame_count += 1
        return frame_data

    def stop(self):
        if self._capture_task:
            self._capture_task.cancel()
            self._capture_task = None

        if self._x11_pointer_display is not None:
            try:
                self._x11_pointer_display.close()
            except Exception:
                pass
            self._x11_pointer_display = None

        if self._mss_instance is not None:
            self._close_mss_instance()

        if self._capture_executor is not None:
            self._capture_executor.shutdown(wait=False, cancel_futures=True)
            self._capture_executor = None

        super().stop()
