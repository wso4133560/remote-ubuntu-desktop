#pragma once
#include <string>
#include <functional>
#include <memory>
#include <thread>
#include <atomic>
#include <glib.h>
#include <libsoup/soup.h>

struct Config;
class WebRTCPipeline;
class InputInjector;

class SignalingClient {
public:
    explicit SignalingClient(Config& config);
    ~SignalingClient();

    bool connect();
    void disconnect();
    void run();  // blocks until stopped
    void stop();

private:
    Config& config_;
    SoupSession* session_ = nullptr;
    SoupWebsocketConnection* ws_ = nullptr;
    GMainLoop* loop_ = nullptr;
    std::unique_ptr<WebRTCPipeline> pipeline_;
    std::unique_ptr<InputInjector> inputInjector_;
    std::string currentSessionId_;
    int reconnectAttempts_ = 0;
    std::atomic<bool> running_{false};

    void sendMessage(const std::string& json);
    void onMessage(const std::string& json);
    void handleSessionRequest(const std::string& sessionId);
    void handleSdpOffer(const std::string& sessionId, const std::string& sdp);
    void handleIceCandidate(const std::string& sessionId, const std::string& candidate,
                            const std::string& sdpMid, int sdpMLineIndex);
    void handleControlMessage(const std::string& json);
    void handleSessionEnd();
    void scheduleReconnect();

    static void onWsMessage(SoupWebsocketConnection* ws, SoupWebsocketDataType type,
                            GBytes* message, gpointer user_data);
    static void onWsClosed(SoupWebsocketConnection* ws, gpointer user_data);
    static void onWsConnected(GObject* src, GAsyncResult* res, gpointer user_data);
};
