#pragma once
#include <string>
#include <functional>
#include <memory>
#include <thread>
#include <atomic>
#include <gst/gst.h>
#include <gst/webrtc/webrtc.h>

struct Config;

using IceCandidateCallback = std::function<void(const std::string& candidate, const std::string& sdpMid, int sdpMLineIndex)>;
using SdpAnswerCallback = std::function<void(const std::string& sdp)>;
using DataChannelMessageCallback = std::function<void(const std::string& label, const std::string& message)>;

class WebRTCPipeline {
public:
    explicit WebRTCPipeline(const Config& config);
    ~WebRTCPipeline();

    bool initialize();
    void handleOffer(const std::string& sdp);
    void addIceCandidate(const std::string& candidate, const std::string& sdpMid, int sdpMLineIndex);
    void stop();

    void setIceCandidateCallback(IceCandidateCallback cb) { iceCb_ = std::move(cb); }
    void setSdpAnswerCallback(SdpAnswerCallback cb) { sdpCb_ = std::move(cb); }
    void setDataChannelMessageCallback(DataChannelMessageCallback cb) { dataChannelCb_ = std::move(cb); }

private:
    const Config& config_;
    GstElement* pipeline_ = nullptr;
    GstElement* webrtcbin_ = nullptr;
    GMainLoop* loop_ = nullptr;
    std::thread loopThread_;
    IceCandidateCallback iceCb_;
    SdpAnswerCallback sdpCb_;
    DataChannelMessageCallback dataChannelCb_;
    bool payloaderLinked_ = false;
    int videoMLineIndex_ = 0;
    int answerRetryCount_ = 0;

    std::string selectEncoder();
    bool probeEncoder(const std::string& name);
    std::string buildPipelineStr(const std::string& encoder);
    bool linkPayloaderToWebrtc();

    static void onNegotiationNeeded(GstElement* webrtc, gpointer user_data);
    static void onIceCandidate(GstElement* webrtc, guint mline, gchar* candidate, gpointer user_data);
    static void onAnswerCreated(GstPromise* promise, gpointer user_data);
    static void onDataChannel(GstElement* webrtc, GstWebRTCDataChannel* channel, gpointer user_data);
    static void onDataChannelOpen(GstWebRTCDataChannel* channel, gpointer user_data);
    static void onDataChannelMessageString(GstWebRTCDataChannel* channel, gchar* str, gpointer user_data);
    static gboolean retryCreateAnswer(gpointer user_data);
};
