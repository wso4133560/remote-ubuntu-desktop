#pragma once
#include <string>
#include <functional>
#include <memory>
#include <glib.h>

struct Config;

class DeviceManager {
public:
    explicit DeviceManager(Config& config);
    ~DeviceManager();

    bool registerDevice();
    bool validateDevice();

private:
    Config& config_;
    bool httpPost(const std::string& url, const std::string& body, std::string& response);
    bool httpGet(const std::string& url, std::string& response);
};
