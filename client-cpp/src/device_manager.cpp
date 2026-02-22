#include "device_manager.h"
#include "config.h"
#include <libsoup/soup.h>
#include <json-glib/json-glib.h>
#include <iostream>

DeviceManager::DeviceManager(Config& config) : config_(config) {}
DeviceManager::~DeviceManager() {}

bool DeviceManager::httpPost(const std::string& url, const std::string& body, std::string& response) {
    SoupSession* session = soup_session_new();
    SoupMessage* msg = soup_message_new("POST", url.c_str());
    soup_message_set_request(msg, "application/json", SOUP_MEMORY_COPY, body.c_str(), body.size());

    guint status = soup_session_send_message(session, msg);
    bool ok = false;
    if (msg->response_body && msg->response_body->data) {
        response.assign(msg->response_body->data, msg->response_body->length);
    }
    ok = (status == SOUP_STATUS_OK);
    if (!ok && status > 0) {
        std::cerr << "HTTP POST error status: " << status << "\n";
    }

    g_object_unref(msg);
    g_object_unref(session);
    return ok;
}

bool DeviceManager::httpGet(const std::string& url, std::string& response) {
    SoupSession* session = soup_session_new();
    SoupMessage* msg = soup_message_new("GET", url.c_str());

    guint status = soup_session_send_message(session, msg);
    bool ok = false;
    if (msg->response_body && msg->response_body->data) {
        response.assign(msg->response_body->data, msg->response_body->length);
    }
    ok = (status == SOUP_STATUS_OK);
    if (!ok && status > 0) {
        std::cerr << "HTTP GET error status: " << status << "\n";
    }

    g_object_unref(msg);
    g_object_unref(session);
    return ok;
}

bool DeviceManager::registerDevice() {
    JsonBuilder* b = json_builder_new();
    json_builder_begin_object(b);
    json_builder_set_member_name(b, "device_name");
    json_builder_add_string_value(b, config_.device_name.c_str());
    json_builder_end_object(b);

    JsonGenerator* gen = json_generator_new();
    json_generator_set_root(gen, json_builder_get_root(b));
    gchar* body = json_generator_to_data(gen, nullptr);
    g_object_unref(gen);
    g_object_unref(b);

    std::string response;
    std::string url = config_.server_url + "/api/v1/devices/register";
    bool ok = httpPost(url, body, response);
    g_free(body);

    if (!ok) { std::cerr << "Device registration failed\n"; return false; }

    JsonParser* parser = json_parser_new();
    GError* err = nullptr;
    if (!json_parser_load_from_data(parser, response.c_str(), -1, &err)) {
        std::cerr << "Failed to parse registration response\n";
        g_clear_error(&err);
        g_object_unref(parser);
        return false;
    }

    JsonObject* root = json_node_get_object(json_parser_get_root(parser));
    if (json_object_has_member(root, "device_id"))
        config_.device_id = json_object_get_string_member(root, "device_id");
    if (json_object_has_member(root, "device_token"))
        config_.device_token = json_object_get_string_member(root, "device_token");
    g_object_unref(parser);

    std::cout << "Device registered: " << config_.device_id << "\n";
    return true;
}

bool DeviceManager::validateDevice() {
    if (config_.device_id.empty() || config_.device_token.empty()) return false;
    std::string url = config_.server_url + "/api/v1/devices/" + config_.device_id;
    std::string response;
    return httpGet(url, response);
}
