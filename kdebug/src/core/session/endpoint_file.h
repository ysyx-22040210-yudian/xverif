#pragma once

#include "json.hpp"

#include <string>

namespace kdebug_core {

// Shared endpoint file I/O for design and waveform sessions.
// The endpoint file is a JSON file that stores transport metadata
// (socket path, host, port, auth token, etc.) for a session.
//
// Component-specific paths (session dir, endpoint path) are injected
// via the policy parameter.

struct EndpointFilePolicy {
    // Returns the filesystem path to the endpoint JSON file for a session.
    std::string (*endpoint_path)(const std::string& session_id);

    // Returns the default socket path for a session (used as fallback).
    std::string (*default_socket_path)(const std::string& session_id);

    // Creates the session directory if it doesn't exist.
    bool (*ensure_session_dir)(const std::string& session_id);
};

// Read endpoint metadata from a session's endpoint JSON file.
// Returns true and populates `fields` on success.
// `fields` should be a JSON object; keys are filled from the file.
inline bool read_endpoint_json(const EndpointFilePolicy& policy,
                               const std::string& session_id,
                               nlohmann::json& fields) {
    std::string path = policy.endpoint_path(session_id);
    FILE* fp = fopen(path.c_str(), "r");
    if (!fp) return false;

    std::string text;
    char buf[1024];
    while (fgets(buf, sizeof(buf), fp)) text += buf;
    fclose(fp);

    try {
        auto root = nlohmann::json::parse(text);
        auto ep = root.value("endpoint", nlohmann::json::object());
        fields["session_id"] = session_id;
        fields["transport"] = ep.value("transport", std::string("uds"));
        fields["socket_path"] = ep.value("socket_path", policy.default_socket_path(session_id));
        fields["file_dir"] = ep.value("file_dir", std::string());
        fields["host"] = ep.value("host", std::string());
        fields["bind_host"] = ep.value("bind_host", std::string());
        fields["port"] = ep.value("port", 0);
        fields["server_host"] = ep.value("server_host", std::string());
        fields["auth_token"] = ep.value("auth_token", std::string());
        return true;
    } catch (...) {
        return false;
    }
}

} // namespace kdebug_core
