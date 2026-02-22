# Remote Desktop Client (C++)

C++ rewrite of the Python client using GStreamer + webrtcbin for native hardware encoding.

## Features

- Hardware encoding: NVENC (NVIDIA) → VAAPI (Intel/AMD) → x264 (software), auto-detected at runtime
- Native resolution capture via `ximagesrc`, no downscaling
- Full WebRTC pipeline via GStreamer `webrtcbin`
- X11 input injection via XTest extension
- WebSocket signaling via libsoup-3.0

## Dependencies

### Runtime (apt)

```
gstreamer1.0-plugins-base
gstreamer1.0-plugins-good
gstreamer1.0-plugins-bad      # webrtcbin, nvh264enc
gstreamer1.0-plugins-ugly     # x264enc
gstreamer1.0-libav
gstreamer1.0-x                # ximagesrc
```

For NVIDIA hardware encoding:
```
gstreamer1.0-plugins-bad      # nvh264enc (requires CUDA)
```

For Intel/AMD VAAPI encoding:
```
gstreamer1.0-vaapi            # vaapih264enc
```

### Build (apt)

```bash
sudo apt install \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev \
  libgstreamer-plugins-bad1.0-dev \
  libsoup-3.0-dev \
  libjson-glib-dev \
  libx11-dev \
  libxtst-dev \
  cmake \
  ninja-build
```

### Missing on this system (already installed by setup)

The following were not present by default and were installed:

| Package | Purpose |
|---|---|
| `libgstreamer1.0-dev` | GStreamer core headers |
| `libgstreamer-plugins-base1.0-dev` | Base plugin headers |
| `libgstreamer-plugins-bad1.0-dev` | webrtcbin, nvh264enc headers |
| `gstreamer1.0-plugins-bad` | webrtcbin, nvh264enc runtime |
| `gstreamer1.0-plugins-ugly` | x264enc runtime |
| `libnice-dev` | ICE library (used by webrtcbin) |
| `libopus-dev` | Opus audio codec |
| `libvpx-dev` | VP8/VP9 codec |
| `libsrtp2-dev` | SRTP for WebRTC |
| `libx11-dev` | X11 headers |
| `libxtst-dev` | XTest extension (input injection) |

## Build

```bash
cd client-cpp
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

## Run

```bash
./build/remote-desktop-client ../client/config.json
```

The binary reads the same `config.json` as the Python client.

## Encoder selection

At startup the binary probes encoders in order:

1. `nvh264enc` — NVIDIA NVENC (requires NVIDIA GPU + driver)
2. `vaapih264enc` — VAAPI (Intel/AMD GPU)
3. `x264enc` — software fallback (always available)

Set `RC_VIDEO_ENCODER` env var to force a specific encoder:

```bash
RC_VIDEO_ENCODER=x264enc ./remote-desktop-client config.json
```
