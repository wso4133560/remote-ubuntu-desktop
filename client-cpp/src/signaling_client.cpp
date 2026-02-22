#include "signaling_client.h"
#include "config.h"
#include "webrtc_pipeline.h"
#include "input_injector.h"
#include <json-glib/json-glib.h>
#include <algorithm>
#include <chrono>
#include <cctype>
#include <iostream>
#include <ctime>
#include <vector>
#include <sstream>

static std::string makeId() {
    static uint64_t counter = 0;
    return std::to_string(++counter) + "_" + std::to_string(time(nullptr));
}

static double nowTimestamp() {
    using namespace std::chrono;
    return duration<double>(system_clock::now().time_since_epoch()).count();
}

static std::string toLower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return (char)std::tolower(c); });
    return value;
}

static void logSdpSummary(const std::string& sdp, const std::string& prefix) {
    std::istringstream iss(sdp);
    std::string line;
    while (std::getline(iss, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.rfind("m=", 0) == 0 ||
            line.rfind("a=mid:", 0) == 0 ||
            line.rfind("a=sendonly", 0) == 0 ||
            line.rfind("a=recvonly", 0) == 0 ||
            line.rfind("a=inactive", 0) == 0 ||
            line.rfind("a=sendrecv", 0) == 0) {
            std::cout << prefix << " " << line << "\n";
        }
    }
}

static std::string buildBaseJson(
    const std::string& type,
    const std::vector<std::pair<std::string, std::string>>& stringFields = {},
    const std::vector<std::pair<std::string, int>>& intFields = {}) {
    JsonBuilder* b = json_builder_new();
    json_builder_begin_object(b);

    json_builder_set_member_name(b, "type");
    json_builder_add_string_value(b, type.c_str());
    json_builder_set_member_name(b, "message_id");
    json_builder_add_string_value(b, makeId().c_str());
    json_builder_set_member_name(b, "timestamp");
    json_builder_add_double_value(b, nowTimestamp());

    for (const auto& [k, v] : stringFields) {
        json_builder_set_member_name(b, k.c_str());
        json_builder_add_string_value(b, v.c_str());
    }
    for (const auto& [k, v] : intFields) {
        json_builder_set_member_name(b, k.c_str());
        json_builder_add_int_value(b, v);
    }

    json_builder_end_object(b);
    JsonGenerator* gen = json_generator_new();
    json_generator_set_root(gen, json_builder_get_root(b));
    gchar* s = json_generator_to_data(gen, nullptr);
    std::string result(s);
    g_free(s);
    g_object_unref(gen);
    g_object_unref(b);
    return result;
}

SignalingClient::SignalingClient(Config& config) : config_(config) {}

SignalingClient::~SignalingClient() {
    stop();
}

void SignalingClient::stop() {
    running_ = false;
    handleSessionEnd();
    if (pipeline_) { pipeline_->stop(); pipeline_.reset(); }
    if (ws_) { soup_websocket_connection_close(ws_, 1000, ""); g_object_unref(ws_); ws_ = nullptr; }
    if (session_) { g_object_unref(session_); session_ = nullptr; }
    if (loop_) {
        g_main_loop_quit(loop_);
        g_main_loop_unref(loop_);
        loop_ = nullptr;
    }
}

void SignalingClient::run() {
    loop_ = g_main_loop_new(nullptr, FALSE);
    running_ = true;
    connect();
    g_main_loop_run(loop_);
}

void SignalingClient::disconnect() {
    stop();
}

bool SignalingClient::connect() {
    if (session_) { g_object_unref(session_); session_ = nullptr; }
    session_ = soup_session_new();

    std::string wsUrl = config_.server_url;
    // http -> ws, https -> wss
    if (wsUrl.substr(0, 7) == "http://")  wsUrl = "ws://"  + wsUrl.substr(7);
    if (wsUrl.substr(0, 8) == "https://") wsUrl = "wss://" + wsUrl.substr(8);
    wsUrl += "/ws?token=" + config_.device_token;

    std::cout << "[WS] Connecting to: " << wsUrl << "\n";

    SoupMessage* msg = soup_message_new("GET", wsUrl.c_str());
    soup_session_websocket_connect_async(
        session_, msg, nullptr, nullptr, nullptr, onWsConnected, this);
    g_object_unref(msg);
    return true;
}

void SignalingClient::onWsConnected(GObject* src, GAsyncResult* res, gpointer user_data) {
    auto* self = static_cast<SignalingClient*>(user_data);
    GError* err = nullptr;
    self->ws_ = soup_session_websocket_connect_finish(SOUP_SESSION(src), res, &err);
    if (!self->ws_ || err) {
        std::cerr << "[WS] Connection failed: " << (err ? err->message : "unknown") << "\n";
        g_clear_error(&err);
        self->scheduleReconnect();
        return;
    }
    std::cout << "[WS] Connected\n";
    self->reconnectAttempts_ = 0;
    g_signal_connect(self->ws_, "message", G_CALLBACK(onWsMessage), self);
    g_signal_connect(self->ws_, "closed",  G_CALLBACK(onWsClosed),  self);
}

void SignalingClient::onWsClosed(SoupWebsocketConnection*, gpointer user_data) {
    auto* self = static_cast<SignalingClient*>(user_data);
    std::cout << "[WS] Connection closed\n";
    if (self->ws_) { g_object_unref(self->ws_); self->ws_ = nullptr; }
    if (self->running_) self->scheduleReconnect();
}

void SignalingClient::scheduleReconnect() {
    if (reconnectAttempts_ >= config_.max_reconnect_attempts) {
        std::cerr << "[WS] Max reconnect attempts reached\n";
        if (loop_) g_main_loop_quit(loop_);
        return;
    }
    int delay = std::min(1 << reconnectAttempts_, 32);
    reconnectAttempts_++;
    std::cout << "[WS] Reconnecting in " << delay << "s (attempt " << reconnectAttempts_ << ")\n";
    g_timeout_add_seconds(delay, [](gpointer ud) -> gboolean {
        static_cast<SignalingClient*>(ud)->connect();
        return G_SOURCE_REMOVE;
    }, this);
}

void SignalingClient::onWsMessage(SoupWebsocketConnection*, SoupWebsocketDataType type,
                                   GBytes* message, gpointer user_data) {
    if (type != SOUP_WEBSOCKET_DATA_TEXT) return;
    auto* self = static_cast<SignalingClient*>(user_data);
    gsize sz;
    const char* data = (const char*)g_bytes_get_data(message, &sz);
    self->onMessage(std::string(data, sz));
}

void SignalingClient::sendMessage(const std::string& json) {
    if (!ws_) return;
    soup_websocket_connection_send_text(ws_, json.c_str());
}

void SignalingClient::onMessage(const std::string& json) {
    JsonParser* parser = json_parser_new();
    GError* err = nullptr;
    if (!json_parser_load_from_data(parser, json.c_str(), -1, &err)) {
        g_clear_error(&err); g_object_unref(parser); return;
    }
    JsonNode* rootNode = json_parser_get_root(parser);
    if (!JSON_NODE_HOLDS_OBJECT(rootNode)) {
        g_object_unref(parser);
        return;
    }
    JsonObject* root = json_node_get_object(rootNode);
    std::string type = json_object_has_member(root, "type")
        ? json_object_get_string_member(root, "type") : "";

    std::cout << "[WS] Received: " << type << "\n";

    std::string normalizedType = toLower(type);

    if (normalizedType == "heartbeat") {
        sendMessage(buildBaseJson("heartbeat_ack"));
    } else if (normalizedType == "session_request") {
        std::string sid = json_object_has_member(root, "session_id")
            ? json_object_get_string_member(root, "session_id") : "";
        handleSessionRequest(sid);
    } else if (normalizedType == "sdp_offer") {
        std::string sid = json_object_has_member(root, "session_id")
            ? json_object_get_string_member(root, "session_id") : "";
        std::string sdp = json_object_has_member(root, "sdp")
            ? json_object_get_string_member(root, "sdp") : "";
        handleSdpOffer(sid, sdp);
    } else if (normalizedType == "ice_candidate") {
        std::string sid  = json_object_has_member(root, "session_id")  ? json_object_get_string_member(root, "session_id")  : "";
        std::string cand = json_object_has_member(root, "candidate")   ? json_object_get_string_member(root, "candidate")   : "";
        std::string mid  = json_object_has_member(root, "sdp_mid")     ? json_object_get_string_member(root, "sdp_mid")     : "0";
        int mline = json_object_has_member(root, "sdp_m_line_index")
            ? (int)json_object_get_int_member(root, "sdp_m_line_index") : 0;
        handleIceCandidate(sid, cand, mid, mline);
    } else if (normalizedType == "session_end") {
        handleSessionEnd();
    }
    g_object_unref(parser);
}

void SignalingClient::handleSessionRequest(const std::string& sessionId) {
    if (!currentSessionId_.empty()) handleSessionEnd();
    currentSessionId_ = sessionId;
    sendMessage(buildBaseJson("session_accept", {{"session_id", sessionId}}));
    std::cout << "[SESSION] Accepted: " << sessionId << "\n";
}

void SignalingClient::handleSdpOffer(const std::string& sessionId, const std::string& sdp) {
    if (sessionId != currentSessionId_) return;
    std::cout << "[SDP] Handling offer\n";

    if (pipeline_) {
        pipeline_->stop();
        pipeline_.reset();
    }
    pipeline_ = std::make_unique<WebRTCPipeline>(config_);
    if (!inputInjector_) {
        inputInjector_ = std::make_unique<InputInjector>();
        if (!inputInjector_->initialize()) {
            std::cerr << "[INPUT] Input injector unavailable, control events disabled\n";
            inputInjector_.reset();
        }
    }

    pipeline_->setIceCandidateCallback([this, sessionId](const std::string& cand,
                                                          const std::string& mid, int mline) {
        sendMessage(buildBaseJson(
            "ice_candidate",
            {{"session_id", sessionId}, {"candidate", cand}, {"sdp_mid", mid}},
            {{"sdp_m_line_index", mline}}));
    });

    pipeline_->setSdpAnswerCallback([this, sessionId](const std::string& answerSdp) {
        logSdpSummary(answerSdp, "[SDP-ANSWER]");
        sendMessage(buildBaseJson("sdp_answer", {{"session_id", sessionId}, {"sdp", answerSdp}}));
        std::cout << "[SDP] Answer sent\n";
    });

    pipeline_->setDataChannelMessageCallback([this](const std::string& label, const std::string& message) {
        if (label == "control") {
            handleControlMessage(message);
        }
    });

    if (!pipeline_->initialize()) {
        std::cerr << "[PIPELINE] Failed to initialize\n";
        pipeline_.reset();
        return;
    }
    pipeline_->handleOffer(sdp);
}

void SignalingClient::handleIceCandidate(const std::string& sessionId, const std::string& candidate,
                                          const std::string& sdpMid, int sdpMLineIndex) {
    if (sessionId != currentSessionId_ || !pipeline_) return;
    pipeline_->addIceCandidate(candidate, sdpMid, sdpMLineIndex);
}

void SignalingClient::handleControlMessage(const std::string& json) {
    if (!inputInjector_) return;

    JsonParser* parser = json_parser_new();
    GError* err = nullptr;
    if (!json_parser_load_from_data(parser, json.c_str(), -1, &err)) {
        g_clear_error(&err);
        g_object_unref(parser);
        return;
    }

    JsonNode* rootNode = json_parser_get_root(parser);
    if (!JSON_NODE_HOLDS_OBJECT(rootNode)) {
        g_object_unref(parser);
        return;
    }

    JsonObject* root = json_node_get_object(rootNode);
    std::string type = json_object_has_member(root, "type")
        ? json_object_get_string_member(root, "type")
        : "";

    if (type == "mouse_move") {
        if (json_object_has_member(root, "x") && json_object_has_member(root, "y")) {
            double x = json_object_get_double_member(root, "x");
            double y = json_object_get_double_member(root, "y");
            inputInjector_->injectMouseMove(x, y);
        }
    } else if (type == "mouse_button") {
        if (json_object_has_member(root, "button") && json_object_has_member(root, "pressed")) {
            int button = (int)json_object_get_int_member(root, "button");
            bool pressed = json_object_get_boolean_member(root, "pressed");
            inputInjector_->injectMouseButton(button, pressed);
        }
    } else if (type == "key") {
        if (json_object_has_member(root, "key_code") && json_object_has_member(root, "pressed")) {
            std::string keyCode = json_object_get_string_member(root, "key_code");
            bool pressed = json_object_get_boolean_member(root, "pressed");
            inputInjector_->injectKey(keyCode, pressed);
        }
    }

    g_object_unref(parser);
}

void SignalingClient::handleSessionEnd() {
    if (currentSessionId_.empty() && !pipeline_ && !inputInjector_) {
        return;
    }
    std::cout << "[SESSION] Ended\n";
    if (pipeline_) { pipeline_->stop(); pipeline_.reset(); }
    inputInjector_.reset();
    currentSessionId_.clear();
}
