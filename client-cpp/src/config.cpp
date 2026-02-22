#include "config.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <json-glib/json-glib.h>

static std::string jsonStr(JsonObject* obj, const char* key, const std::string& def = "") {
    if (!json_object_has_member(obj, key)) return def;
    return json_object_get_string_member(obj, key) ?: def;
}

static int jsonInt(JsonObject* obj, const char* key, int def = 0) {
    if (!json_object_has_member(obj, key)) return def;
    return (int)json_object_get_int_member(obj, key);
}

static bool jsonBool(JsonObject* obj, const char* key, bool def = false) {
    if (!json_object_has_member(obj, key)) return def;
    return json_object_get_boolean_member(obj, key);
}

static std::string normalizeServerUrl(const std::string& url) {
    auto rewrite = [&url](const std::string& from, const std::string& to) -> std::string {
        if (url.rfind(from, 0) != 0) return "";
        if (url.size() > from.size()) {
            char next = url[from.size()];
            if (next != ':' && next != '/') return "";
        }
        return to + url.substr(from.size());
    };

    std::string rewritten = rewrite("http://localhost", "http://127.0.0.1");
    if (rewritten.empty()) rewritten = rewrite("https://localhost", "https://127.0.0.1");
    if (!rewritten.empty()) {
        std::cerr << "[CFG] Rewrote server_url from localhost to 127.0.0.1: "
                  << rewritten << "\n";
        return rewritten;
    }
    return url;
}

Config Config::load(const std::string& path) {
    GError* err = nullptr;
    JsonParser* parser = json_parser_new();

    if (!json_parser_load_from_file(parser, path.c_str(), &err)) {
        std::string msg = err ? err->message : "unknown error";
        g_clear_error(&err);
        g_object_unref(parser);
        throw std::runtime_error("Failed to load config: " + msg);
    }

    JsonObject* root = json_node_get_object(json_parser_get_root(parser));
    Config c;
    c.server_url            = normalizeServerUrl(jsonStr(root, "server_url"));
    c.device_name           = jsonStr(root, "device_name");
    c.device_id             = jsonStr(root, "device_id");
    c.device_token          = jsonStr(root, "device_token");
    c.heartbeat_interval    = jsonInt(root, "heartbeat_interval", 30);
    c.reconnect_delay       = jsonInt(root, "reconnect_delay", 5);
    c.max_reconnect_attempts= jsonInt(root, "max_reconnect_attempts", 6);
    c.video_width           = jsonInt(root, "video_width", 1920);
    c.video_height          = jsonInt(root, "video_height", 1080);
    c.video_fps             = jsonInt(root, "video_fps", 60);
    c.video_bitrate         = jsonInt(root, "video_bitrate", 8000000);
    c.enable_audio          = jsonBool(root, "enable_audio", true);
    c.enable_clipboard      = jsonBool(root, "enable_clipboard", true);
    c.enable_file_transfer  = jsonBool(root, "enable_file_transfer", true);

    g_object_unref(parser);
    return c;
}

void Config::save(const std::string& path) const {
    JsonBuilder* b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "server_url");    json_builder_add_string_value(b, server_url.c_str());
    json_builder_set_member_name(b, "device_name");   json_builder_add_string_value(b, device_name.c_str());
    json_builder_set_member_name(b, "device_id");     json_builder_add_string_value(b, device_id.c_str());
    json_builder_set_member_name(b, "device_token");  json_builder_add_string_value(b, device_token.c_str());
    json_builder_set_member_name(b, "heartbeat_interval");     json_builder_add_int_value(b, heartbeat_interval);
    json_builder_set_member_name(b, "reconnect_delay");        json_builder_add_int_value(b, reconnect_delay);
    json_builder_set_member_name(b, "max_reconnect_attempts"); json_builder_add_int_value(b, max_reconnect_attempts);
    json_builder_set_member_name(b, "video_width");   json_builder_add_int_value(b, video_width);
    json_builder_set_member_name(b, "video_height");  json_builder_add_int_value(b, video_height);
    json_builder_set_member_name(b, "video_fps");     json_builder_add_int_value(b, video_fps);
    json_builder_set_member_name(b, "video_bitrate"); json_builder_add_int_value(b, video_bitrate);
    json_builder_set_member_name(b, "enable_audio");          json_builder_add_boolean_value(b, enable_audio);
    json_builder_set_member_name(b, "enable_clipboard");      json_builder_add_boolean_value(b, enable_clipboard);
    json_builder_set_member_name(b, "enable_file_transfer");  json_builder_add_boolean_value(b, enable_file_transfer);
    json_builder_end_object(b);

    JsonGenerator* gen = json_generator_new();
    json_generator_set_pretty(gen, TRUE);
    json_generator_set_root(gen, json_builder_get_root(b));

    GError* err = nullptr;
    json_generator_to_file(gen, path.c_str(), &err);
    g_clear_error(&err);
    g_object_unref(gen);
    g_object_unref(b);
}
