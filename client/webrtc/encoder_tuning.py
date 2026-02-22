"""aiortc video encoder tuning for high-FPS and hardware acceleration."""
from __future__ import annotations

import fractions
import os
import subprocess
import time
from typing import Optional

import av
import av._core
import numpy as np
from aiortc.codecs import h264, vpx
from aiortc.codecs.h264 import H264Encoder

_TUNING_APPLIED = False
_TARGET_FPS = 60
_TARGET_BITRATE = 8_000_000
_SELECTED_ENCODER: Optional[str] = None
_LOG_ENCODER_STATS = os.environ.get("RC_LOG_ENCODER_STATS", "1") == "1"
_STATS_WINDOW_START = time.perf_counter()
_STATS_FRAMES = 0
_STATS_TOTAL_ENCODE_MS = 0.0
_STATS_MAX_ENCODE_MS = 0.0
_STATS_CODEC_NAME = "unknown"


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _pick_encoder() -> str:
    preferred = os.environ.get("RC_VIDEO_ENCODER", "auto").strip().lower()
    candidates: list[str]
    if preferred and preferred != "auto":
        candidates = [preferred, "h264_nvenc", "h264_qsv", "libx264"]
    else:
        candidates = ["h264_nvenc", "h264_qsv", "libx264"]

    for codec_name in candidates:
        if _probe_encoder(codec_name):
            return codec_name
    return "libx264"


def _create_codec_context(
    codec_name: str,
    width: int,
    height: int,
    bitrate: int,
    fps: int,
) -> av.CodecContext:
    codec = av.CodecContext.create(codec_name, "w")
    codec.width = width
    codec.height = height
    codec.bit_rate = bitrate
    codec.pix_fmt = "yuv420p"
    codec.framerate = fractions.Fraction(fps, 1)
    codec.time_base = fractions.Fraction(1, fps)
    codec.gop_size = fps
    codec.max_b_frames = 0

    if codec_name == "h264_nvenc":
        codec.options = {
            "preset": "p1",
            "tune": "ull",
            "rc": "cbr",
            "zerolatency": "1",
            "rc-lookahead": "0",
            "delay": "0",
        }
    elif codec_name == "h264_qsv":
        codec.options = {
            "preset": "veryfast",
            "look_ahead": "0",
        }
    else:
        codec.options = {
            "profile": "baseline",
            "level": "4.2",
            "tune": "zerolatency",
            "preset": "ultrafast",
            "rc-lookahead": "0",
        }
        codec.profile = "Baseline"
        codec.thread_count = 0

    return codec


def _probe_encoder(codec_name: str) -> bool:
    try:
        probe = _create_codec_context(
            codec_name=codec_name,
            width=320,
            height=180,
            bitrate=2_000_000,
            fps=30,
        )
        frame = av.VideoFrame.from_ndarray(
            np.zeros((180, 320, 3), dtype=np.uint8),
            format="rgb24",
        ).reformat(format="yuv420p")
        frame.pts = 0
        frame.time_base = fractions.Fraction(1, 30)
        probe.encode(frame)
        return True
    except Exception:
        return False


def _uses_bundled_av_libs() -> bool:
    try:
        output = subprocess.check_output(["ldd", av._core.__file__], text=True)
        return "av.libs" in output
    except Exception:
        return False


def apply_webrtc_encoder_tuning(target_fps: int, target_bitrate: int) -> None:
    global _TUNING_APPLIED, _TARGET_FPS, _TARGET_BITRATE, _SELECTED_ENCODER
    global _STATS_WINDOW_START, _STATS_FRAMES, _STATS_TOTAL_ENCODE_MS, _STATS_MAX_ENCODE_MS, _STATS_CODEC_NAME

    _TARGET_FPS = _clamp(target_fps, 30, 60)
    _TARGET_BITRATE = _clamp(target_bitrate, 2_000_000, 50_000_000)

    h264.MAX_FRAME_RATE = _TARGET_FPS
    h264.DEFAULT_BITRATE = _TARGET_BITRATE
    h264.MAX_BITRATE = max(_TARGET_BITRATE, 20_000_000)
    h264.MIN_BITRATE = min(h264.MIN_BITRATE, _TARGET_BITRATE)
    vpx.DEFAULT_BITRATE = max(vpx.DEFAULT_BITRATE, _TARGET_BITRATE // 2)
    vpx.MAX_BITRATE = max(vpx.MAX_BITRATE, _TARGET_BITRATE)

    if _SELECTED_ENCODER is None:
        _SELECTED_ENCODER = _pick_encoder()
        if _uses_bundled_av_libs():
            print(
                "PyAV is linked to bundled av.libs (wheel FFmpeg), "
                "hardware encoders may be unavailable despite system ffmpeg support"
            )
        print(
            f"Applied aiortc encoder tuning: fps={_TARGET_FPS}, "
            f"bitrate={_TARGET_BITRATE}, encoder={_SELECTED_ENCODER}"
        )
        if _SELECTED_ENCODER in {"libx264"}:
            print(
                "Hardware H264 encoder not usable in current runtime, "
                "falling back to CPU libx264"
            )

    _STATS_WINDOW_START = time.perf_counter()
    _STATS_FRAMES = 0
    _STATS_TOTAL_ENCODE_MS = 0.0
    _STATS_MAX_ENCODE_MS = 0.0
    _STATS_CODEC_NAME = _SELECTED_ENCODER or "unknown"

    if _TUNING_APPLIED:
        return

    def _encode_frame_patched(self, frame: av.VideoFrame, force_keyframe: bool):
        global _STATS_WINDOW_START, _STATS_FRAMES, _STATS_TOTAL_ENCODE_MS, _STATS_MAX_ENCODE_MS, _STATS_CODEC_NAME

        if self.codec and (
            frame.width != self.codec.width
            or frame.height != self.codec.height
            or abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.1
        ):
            self.buffer_data = b""
            self.buffer_pts = None
            self.codec = None

        if force_keyframe:
            frame.pict_type = av.video.frame.PictureType.I
        else:
            frame.pict_type = av.video.frame.PictureType.NONE

        if self.codec is None:
            target_bitrate = _clamp(self.target_bitrate, 2_000_000, h264.MAX_BITRATE)
            try:
                self.codec = _create_codec_context(
                    _SELECTED_ENCODER or "libx264",
                    frame.width,
                    frame.height,
                    target_bitrate,
                    _TARGET_FPS,
                )
            except Exception as primary_error:
                print(f"Primary H264 encoder init failed: {primary_error}; fallback to libx264")
                self.codec = _create_codec_context(
                    "libx264",
                    frame.width,
                    frame.height,
                    target_bitrate,
                    _TARGET_FPS,
                )

        data_to_send = b""
        encode_started = time.perf_counter()
        try:
            for packet in self.codec.encode(frame):
                data_to_send += bytes(packet)
        except Exception as encode_error:
            print(f"H264 encode failed on {self.codec.name}: {encode_error}; retry with libx264")
            target_bitrate = _clamp(self.target_bitrate, 2_000_000, h264.MAX_BITRATE)
            self.codec = _create_codec_context(
                "libx264",
                frame.width,
                frame.height,
                target_bitrate,
                _TARGET_FPS,
            )
            encode_started = time.perf_counter()
            for packet in self.codec.encode(frame):
                data_to_send += bytes(packet)

        encode_ms = (time.perf_counter() - encode_started) * 1000
        _STATS_FRAMES += 1
        _STATS_TOTAL_ENCODE_MS += encode_ms
        _STATS_MAX_ENCODE_MS = max(_STATS_MAX_ENCODE_MS, encode_ms)
        if self.codec:
            _STATS_CODEC_NAME = self.codec.name

        if _LOG_ENCODER_STATS:
            window_elapsed = time.perf_counter() - _STATS_WINDOW_START
            if window_elapsed >= 1.0:
                window_fps = _STATS_FRAMES / window_elapsed
                avg_encode_ms = _STATS_TOTAL_ENCODE_MS / max(_STATS_FRAMES, 1)
                print(
                    "[ENC] "
                    f"codec={_STATS_CODEC_NAME} "
                    f"fps={window_fps:.1f} "
                    f"encode_avg={avg_encode_ms:.2f}ms "
                    f"encode_max={_STATS_MAX_ENCODE_MS:.2f}ms "
                    f"target={_TARGET_FPS}fps "
                    f"bitrate={self.target_bitrate}",
                    flush=True,
                )
                _STATS_WINDOW_START = time.perf_counter()
                _STATS_FRAMES = 0
                _STATS_TOTAL_ENCODE_MS = 0.0
                _STATS_MAX_ENCODE_MS = 0.0

        if data_to_send:
            yield from self._split_bitstream(data_to_send)

    H264Encoder._encode_frame = _encode_frame_patched
    _TUNING_APPLIED = True
