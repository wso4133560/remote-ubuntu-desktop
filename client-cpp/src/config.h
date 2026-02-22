#pragma once
#include <string>

struct Config {
    std::string server_url;
    std::string device_name;
    std::string device_id;
    std::string device_token;

    int heartbeat_interval = 30;
    int reconnect_delay = 5;
    int max_reconnect_attempts = 6;

    int video_width = 1920;
    int video_height = 1080;
    int video_fps = 60;
    int video_bitrate = 8000000;

    bool enable_audio = true;
    bool enable_clipboard = true;
    bool enable_file_transfer = true;

    static Config load(const std::string& path);
    void save(const std::string& path) const;
};
