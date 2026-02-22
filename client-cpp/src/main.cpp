#include "config.h"
#include "device_manager.h"
#include "signaling_client.h"
#include <gst/gst.h>
#include <iostream>
#include <csignal>
#include <atomic>

static std::atomic<bool> g_running{true};
static SignalingClient* g_client = nullptr;

static void onSignal(int) {
    g_running = false;
    if (g_client) g_client->stop();
}

int main(int argc, char* argv[]) {
    gst_init(&argc, &argv);

    std::string configPath = "config.json";
    if (argc > 1) configPath = argv[1];

    Config config;
    try {
        config = Config::load(configPath);
    } catch (const std::exception& e) {
        std::cerr << "Failed to load config: " << e.what() << "\n";
        return 1;
    }

    std::signal(SIGINT,  onSignal);
    std::signal(SIGTERM, onSignal);

    DeviceManager dm(config);
    if (!dm.validateDevice()) {
        std::cout << "Device not registered, registering...\n";
        if (!dm.registerDevice()) {
            std::cerr << "Device registration failed\n";
            return 1;
        }
        config.save(configPath);
    }

    SignalingClient client(config);
    g_client = &client;
    client.run();  // blocks

    gst_deinit();
    return 0;
}
