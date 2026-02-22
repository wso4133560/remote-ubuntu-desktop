#include "webrtc_pipeline.h"
#include "config.h"
#include <gst/webrtc/webrtc.h>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <sstream>

static int findVideoMLineIndex(const std::string& sdp) {
    std::istringstream iss(sdp);
    std::string line;
    int mline = 0;
    while (std::getline(iss, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.rfind("m=", 0) != 0) continue;
        if (line.rfind("m=video", 0) == 0) return mline;
        mline++;
    }
    return 0;
}

static std::string getDataChannelLabel(GstWebRTCDataChannel* channel) {
    gchar* label = nullptr;
    g_object_get(channel, "label", &label, nullptr);
    std::string labelStr = label ? label : "";
    g_free(label);
    return labelStr;
}

WebRTCPipeline::WebRTCPipeline(const Config& config) : config_(config) {}

WebRTCPipeline::~WebRTCPipeline() {
    stop();
}

bool WebRTCPipeline::probeEncoder(const std::string& name) {
    GstElement* el = gst_element_factory_make(name.c_str(), nullptr);
    if (!el) return false;
    gst_object_unref(el);
    return true;
}

std::string WebRTCPipeline::selectEncoder() {
    const char* forcedCodec = getenv("RC_VIDEO_CODEC");
    if (forcedCodec && std::string(forcedCodec) == "h264") {
        std::cout << "[ENC] RC_VIDEO_CODEC=h264, forcing H264 path\n";
    } else {
        if (probeEncoder("vp8enc")) {
            std::cout << "[ENC] Selected: vp8enc (compatibility default)\n";
            return "vp8enc";
        }
    }

    // Compatibility-first: software encoder is more reliable across browsers.
    // Set RC_PREFER_HW_ENCODER=1 to prefer hardware encoders.
    const char* preferHw = getenv("RC_PREFER_HW_ENCODER");
    bool useHwFirst = preferHw && std::string(preferHw) == "1";

    if (useHwFirst) {
        if (probeEncoder("nvh264enc")) {
            std::cout << "[ENC] Selected: nvh264enc (NVIDIA hardware)\n";
            return "nvh264enc";
        }
        if (probeEncoder("vaapih264enc")) {
            std::cout << "[ENC] Selected: vaapih264enc (VAAPI hardware)\n";
            return "vaapih264enc";
        }
    }

    if (probeEncoder("x264enc")) {
        std::cout << "[ENC] Selected: x264enc (software)\n";
        return "x264enc";
    }

    // If software encoder is unavailable, fall back to hardware candidates.
    if (probeEncoder("nvh264enc")) {
        std::cout << "[ENC] Selected: nvh264enc (NVIDIA hardware fallback)\n";
        return "nvh264enc";
    }
    if (probeEncoder("vaapih264enc")) {
        std::cout << "[ENC] Selected: vaapih264enc (VAAPI hardware fallback)\n";
        return "vaapih264enc";
    }

    std::cout << "[ENC] No preferred encoder found, using x264enc\n";
    return "x264enc";
}

std::string WebRTCPipeline::buildPipelineStr(const std::string& encoder) {
    std::ostringstream ss;
    int fps = std::max(1, config_.video_fps);
    int bitrate = std::max(300000, config_.video_bitrate);
    int width = std::max(640, config_.video_width);
    int height = std::max(360, config_.video_height);

    if (encoder == "vp8enc") {
        // Software VP8 at 1080p60 can collapse over time on some hosts.
        // Keep defaults in a stable envelope for long-running sessions.
        fps = std::min(fps, 30);
        const int maxPixels = 1280 * 720;
        if (width * height > maxPixels) {
            const double scale = std::sqrt((double)maxPixels / (double)(width * height));
            width = std::max(640, (int)(width * scale));
            height = std::max(360, (int)(height * scale));
            if (width % 2) width--;
            if (height % 2) height--;
        }
        bitrate = std::min(bitrate, 4000000);
    }

    std::cout << "[ENC] Effective stream profile: "
              << width << "x" << height
              << " @" << fps << "fps"
              << " bitrate=" << bitrate << "\n";

    ss << "ximagesrc display-name=" << (getenv("DISPLAY") ? getenv("DISPLAY") : ":0")
       << " use-damage=0 ! ";
    ss << "video/x-raw,framerate=" << fps << "/1 ! ";
    ss << "videoconvert ! videoscale ! ";
    ss << "video/x-raw,width=" << width << ",height=" << height
       << ",framerate=" << fps << "/1 ! ";
    // Drop stale frames under encoder pressure to keep interaction responsive.
    ss << "queue leaky=downstream max-size-buffers=2 max-size-time=0 max-size-bytes=0 ! ";

    if (encoder == "vp8enc") {
        unsigned int hwThreads = std::max(1u, std::thread::hardware_concurrency());
        unsigned int encThreads = std::min(8u, hwThreads);
        ss << "vp8enc deadline=1 cpu-used=8 target-bitrate=" << bitrate
           << " keyframe-max-dist=" << fps
           << " error-resilient=partitions threads=" << encThreads << " ! ";
        ss << "rtpvp8pay name=rtppay0 pt=96 picture-id-mode=15-bit";
        return ss.str();
    } else if (encoder == "nvh264enc") {
        // bitrate in kbps for nvh264enc
        int kbps = bitrate / 1000;
        ss << "nvh264enc bitrate=" << kbps
           << " preset=low-latency-hq rc-mode=cbr zerolatency=true ! ";
        ss << "video/x-h264,profile=baseline,stream-format=byte-stream ! ";
    } else if (encoder == "vaapih264enc") {
        ss << "vaapipostproc ! ";
        ss << "vaapih264enc bitrate=" << (bitrate / 1000)
           << " keyframe-period=" << fps << " ! ";
        ss << "video/x-h264,profile=baseline,stream-format=byte-stream ! ";
    } else {
        // x264enc bitrate in kbps
        ss << "x264enc bitrate=" << (bitrate / 1000)
           << " speed-preset=ultrafast tune=zerolatency key-int-max=" << fps
           << " ! ";
        ss << "video/x-h264,profile=baseline,stream-format=byte-stream ! ";
    }

    ss << "h264parse ! ";
    ss << "rtph264pay name=rtppay0 pt=96 config-interval=1";

    return ss.str();
}

bool WebRTCPipeline::initialize() {
    std::string encoder = selectEncoder();
    std::string pipelineStr = buildPipelineStr(encoder);
    std::cout << "[GST] Pipeline: " << pipelineStr << "\n";

    GError* err = nullptr;
    pipeline_ = gst_parse_launch(pipelineStr.c_str(), &err);
    if (!pipeline_ || err) {
        std::cerr << "[GST] Failed to create pipeline: "
                  << (err ? err->message : "unknown") << "\n";
        g_clear_error(&err);
        return false;
    }

    webrtcbin_ = gst_element_factory_make("webrtcbin", "webrtcbin");
    if (!webrtcbin_) {
        std::cerr << "[GST] Failed to create webrtcbin element\n";
        return false;
    }
    if (!gst_bin_add(GST_BIN(pipeline_), webrtcbin_)) {
        std::cerr << "[GST] Failed to add webrtcbin into pipeline\n";
        gst_object_unref(webrtcbin_);
        webrtcbin_ = nullptr;
        return false;
    }

    g_signal_connect(webrtcbin_, "on-ice-candidate", G_CALLBACK(onIceCandidate), this);
    g_signal_connect(webrtcbin_, "on-data-channel", G_CALLBACK(onDataChannel), this);
    g_object_set(
        webrtcbin_,
        "stun-server", "stun://stun.l.google.com:19302",
        "bundle-policy", GST_WEBRTC_BUNDLE_POLICY_MAX_BUNDLE,
        nullptr);

    loop_ = g_main_loop_new(nullptr, FALSE);
    loopThread_ = std::thread([this]() { g_main_loop_run(loop_); });

    gst_element_set_state(pipeline_, GST_STATE_READY);
    return true;
}

bool WebRTCPipeline::linkPayloaderToWebrtc() {
    if (payloaderLinked_) return true;
    if (!pipeline_ || !webrtcbin_) return false;

    GstElement* payloader = gst_bin_get_by_name(GST_BIN(pipeline_), "rtppay0");
    if (!payloader) {
        std::cerr << "[GST] Failed to find rtppay0 element\n";
        return false;
    }

    GstPad* paySrcPad = gst_element_get_static_pad(payloader, "src");
    std::string sinkPadNameTarget = "sink_" + std::to_string(videoMLineIndex_);
    GstPad* webrtcSinkPad = gst_element_get_static_pad(webrtcbin_, sinkPadNameTarget.c_str());
    if (!webrtcSinkPad) {
        // Fallback for legacy behavior when specific sink pad is not yet materialized.
        std::cerr << "[GST] " << sinkPadNameTarget << " not found, requesting generic sink_%u\n";
        webrtcSinkPad = gst_element_request_pad_simple(webrtcbin_, "sink_%u");
    }
    if (!paySrcPad || !webrtcSinkPad) {
        std::cerr << "[GST] Failed to request/link webrtc sink pad"
                  << " paySrcPad=" << (paySrcPad ? "ok" : "null")
                  << " webrtcSinkPad=" << (webrtcSinkPad ? "ok" : "null") << "\n";
        if (paySrcPad) gst_object_unref(paySrcPad);
        if (webrtcSinkPad) gst_object_unref(webrtcSinkPad);
        gst_object_unref(payloader);
        return false;
    }

    gchar* sinkPadName = gst_pad_get_name(webrtcSinkPad);
    bool ok = (gst_pad_link(paySrcPad, webrtcSinkPad) == GST_PAD_LINK_OK);
    if (!ok) {
        std::cerr << "[GST] Failed to link payloader to webrtcbin sink pad: "
                  << (sinkPadName ? sinkPadName : "<unknown>") << "\n";
    } else {
        std::cout << "[GST] Linked payloader to webrtcbin pad: "
                  << (sinkPadName ? sinkPadName : "<unknown>") << "\n";
        payloaderLinked_ = true;
    }
    g_free(sinkPadName);

    gst_object_unref(paySrcPad);
    gst_object_unref(webrtcSinkPad);
    gst_object_unref(payloader);
    return ok;
}

void WebRTCPipeline::handleOffer(const std::string& sdp) {
    answerRetryCount_ = 0;
    videoMLineIndex_ = findVideoMLineIndex(sdp);
    std::cout << "[SDP] Video m-line index from offer: " << videoMLineIndex_ << "\n";

    GstSDPMessage* sdpMsg = nullptr;
    gst_sdp_message_new(&sdpMsg);
    gst_sdp_message_parse_buffer((const guint8*)sdp.c_str(), sdp.size(), sdpMsg);

    GstWebRTCSessionDescription* offer =
        gst_webrtc_session_description_new(GST_WEBRTC_SDP_TYPE_OFFER, sdpMsg);

    gst_element_set_state(pipeline_, GST_STATE_PLAYING);

    GstPromise* promise = gst_promise_new_with_change_func(
        [](GstPromise* p, gpointer ud) {
            auto* self = static_cast<WebRTCPipeline*>(ud);
            if (!self->linkPayloaderToWebrtc()) {
                std::cerr << "[GST] Cannot create answer: failed to link payloader\n";
                gst_promise_unref(p);
                return;
            }
            retryCreateAnswer(self);
            gst_promise_unref(p);
        },
        this, nullptr);

    g_signal_emit_by_name(webrtcbin_, "set-remote-description", offer, promise);
    gst_webrtc_session_description_free(offer);
}

void WebRTCPipeline::onAnswerCreated(GstPromise* promise, gpointer user_data) {
    auto* self = static_cast<WebRTCPipeline*>(user_data);

    const GstStructure* reply = gst_promise_get_reply(promise);
    if (!reply) {
        std::cerr << "[SDP] create-answer returned empty reply\n";
        gst_promise_unref(promise);
        return;
    }
    GstWebRTCSessionDescription* answer = nullptr;
    gst_structure_get(reply, "answer", GST_TYPE_WEBRTC_SESSION_DESCRIPTION, &answer, nullptr);
    gst_promise_unref(promise);
    if (!answer || !answer->sdp) {
        if (self->answerRetryCount_ < 3) {
            self->answerRetryCount_++;
            std::cerr << "[SDP] create-answer returned invalid answer, retry "
                      << self->answerRetryCount_ << "/3\n";
            g_timeout_add(150, retryCreateAnswer, self);
        } else {
            std::cerr << "[SDP] create-answer failed after retries\n";
        }
        if (answer) gst_webrtc_session_description_free(answer);
        return;
    }
    self->answerRetryCount_ = 0;

    GstPromise* localPromise = gst_promise_new();
    g_signal_emit_by_name(self->webrtcbin_, "set-local-description", answer, localPromise);
    gst_promise_interrupt(localPromise);
    gst_promise_unref(localPromise);

    gchar* sdpStr = gst_sdp_message_as_text(answer->sdp);
    if (self->sdpCb_) self->sdpCb_(sdpStr);
    g_free(sdpStr);

    gst_webrtc_session_description_free(answer);
}

gboolean WebRTCPipeline::retryCreateAnswer(gpointer user_data) {
    auto* self = static_cast<WebRTCPipeline*>(user_data);
    if (!self || !self->webrtcbin_) return G_SOURCE_REMOVE;
    GstPromise* answerPromise = gst_promise_new_with_change_func(
        onAnswerCreated, self, nullptr);
    g_signal_emit_by_name(self->webrtcbin_, "create-answer", nullptr, answerPromise);
    return G_SOURCE_REMOVE;
}

void WebRTCPipeline::onIceCandidate(GstElement*, guint mline, gchar* candidate, gpointer user_data) {
    auto* self = static_cast<WebRTCPipeline*>(user_data);
    if (self->iceCb_) self->iceCb_(candidate, std::to_string(mline), (int)mline);
}

void WebRTCPipeline::onDataChannel(GstElement*, GstWebRTCDataChannel* channel, gpointer user_data) {
    auto* self = static_cast<WebRTCPipeline*>(user_data);
    std::string label = getDataChannelLabel(channel);
    std::cout << "[DC] DataChannel received: " << label << "\n";

    g_signal_connect(channel, "on-open", G_CALLBACK(onDataChannelOpen), self);
    g_signal_connect(channel, "on-message-string", G_CALLBACK(onDataChannelMessageString), self);
}

void WebRTCPipeline::onDataChannelOpen(GstWebRTCDataChannel* channel, gpointer) {
    std::cout << "[DC] Opened: " << getDataChannelLabel(channel) << "\n";
}

void WebRTCPipeline::onDataChannelMessageString(GstWebRTCDataChannel* channel, gchar* str, gpointer user_data) {
    auto* self = static_cast<WebRTCPipeline*>(user_data);
    if (!self->dataChannelCb_ || !str) return;
    self->dataChannelCb_(getDataChannelLabel(channel), str);
}

void WebRTCPipeline::onNegotiationNeeded(GstElement*, gpointer) {}

void WebRTCPipeline::addIceCandidate(const std::string& candidate,
                                      const std::string& sdpMid, int sdpMLineIndex) {
    (void)sdpMid;
    if (!webrtcbin_) return;
    g_signal_emit_by_name(webrtcbin_, "add-ice-candidate", (guint)sdpMLineIndex, candidate.c_str());
}

void WebRTCPipeline::stop() {
    if (pipeline_) {
        gst_element_set_state(pipeline_, GST_STATE_NULL);
        gst_object_unref(pipeline_);
        pipeline_ = nullptr;
        webrtcbin_ = nullptr;
    }
    if (loop_) {
        g_main_loop_quit(loop_);
        if (loopThread_.joinable()) loopThread_.join();
        g_main_loop_unref(loop_);
        loop_ = nullptr;
    }
}
