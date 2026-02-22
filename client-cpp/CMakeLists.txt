cmake_minimum_required(VERSION 3.16)
project(remote-desktop-client CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)

pkg_check_modules(GST REQUIRED gstreamer-1.0)
pkg_check_modules(GST_WEBRTC REQUIRED gstreamer-webrtc-1.0)
pkg_check_modules(GST_VIDEO REQUIRED gstreamer-video-1.0)
pkg_check_modules(GST_SDP REQUIRED gstreamer-sdp-1.0)
pkg_check_modules(SOUP REQUIRED libsoup-2.4)
pkg_check_modules(JSON REQUIRED json-glib-1.0)

find_package(Threads REQUIRED)

find_path(X11_INCLUDE_DIR X11/Xlib.h)
find_library(X11_LIB X11)
find_library(XTST_LIB Xtst)
find_library(XRANDR_LIB Xrandr)

add_executable(remote-desktop-client
    src/main.cpp
    src/config.cpp
    src/device_manager.cpp
    src/signaling_client.cpp
    src/webrtc_pipeline.cpp
    src/input_injector.cpp
)

target_include_directories(remote-desktop-client PRIVATE
    ${GST_INCLUDE_DIRS}
    ${GST_WEBRTC_INCLUDE_DIRS}
    ${GST_VIDEO_INCLUDE_DIRS}
    ${GST_SDP_INCLUDE_DIRS}
    ${SOUP_INCLUDE_DIRS}
    ${JSON_INCLUDE_DIRS}
    ${X11_INCLUDE_DIR}
    src/
)

target_link_libraries(remote-desktop-client
    ${GST_LIBRARIES}
    ${GST_WEBRTC_LIBRARIES}
    ${GST_VIDEO_LIBRARIES}
    ${GST_SDP_LIBRARIES}
    ${SOUP_LIBRARIES}
    ${JSON_LIBRARIES}
    ${X11_LIB}
    ${XTST_LIB}
    ${XRANDR_LIB}
    Threads::Threads
)

target_compile_options(remote-desktop-client PRIVATE
    ${GST_CFLAGS_OTHER}
    ${SOUP_CFLAGS_OTHER}
    ${JSON_CFLAGS_OTHER}
)
