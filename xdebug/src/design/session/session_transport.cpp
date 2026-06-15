#include "session_transport.h"
#include "../common/xdebug_design_paths.h"
#include "json.hpp"
#include "../protocol/protocol.h"
#include "transport/file_exchange.h"
#include "session/transport_timeout.h"
#include "session/transport_common.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <unistd.h>

namespace xdebug_design {

using Json = nlohmann::json;

// --- Re-exported shared utilities (called by session_manager, server, etc.) ---

std::string current_host_name() {
    return xdebug_core::current_host_name();
}

std::string generate_auth_token() {
    return xdebug_core::generate_auth_token();
}

// --- Transport type helpers (thin wrappers around shared utils) ---

bool is_tcp_transport(const SessionInfo& session) {
    return xdebug_core::is_tcp_transport(session.transport);
}

bool is_file_transport(const SessionInfo& session) {
    return xdebug_core::is_file_transport(session.transport);
}

bool is_local_session_host(const SessionInfo& session) {
    return xdebug_core::is_local_session_host(session.server_host);
}

// --- Endpoint file I/O (component-specific paths) ---

bool write_endpoint_file(const SessionInfo& session) {
    if (!xdebug_design_ensure_session_dir(session.session_id)) return false;
    Json root = {
        {"version", 1},
        {"endpoint", {
            {"transport", session.transport.empty() ? "uds" : session.transport},
            {"socket_path", session.socket_path},
            {"file_dir", session.file_dir},
            {"host", session.host},
            {"bind_host", session.bind_host},
            {"port", session.port},
            {"server_host", session.server_host},
            {"auth_token", session.auth_token}
        }}
    };
    return xdebug_core::atomic_write_json_file(xdebug_design_endpoint_path(session.session_id), root);
}

bool read_endpoint_file(const std::string& session_id, SessionInfo& endpoint) {
    FILE* fp = fopen(xdebug_design_endpoint_path(session_id).c_str(), "r");
    if (!fp) return false;
    std::string text;
    char buf[1024];
    while (fgets(buf, sizeof(buf), fp)) text += buf;
    fclose(fp);
    try {
        Json root = Json::parse(text);
        Json e = root.value("endpoint", Json::object());
        endpoint.session_id = session_id;
        endpoint.transport = e.value("transport", std::string("uds"));
        endpoint.socket_path = e.value("socket_path", xdebug_design_socket_path(session_id));
        endpoint.file_dir = e.value("file_dir", std::string());
        endpoint.host = e.value("host", std::string());
        endpoint.bind_host = e.value("bind_host", std::string());
        endpoint.port = e.value("port", 0);
        endpoint.server_host = e.value("server_host", std::string());
        endpoint.auth_token = e.value("auth_token", std::string());
        return true;
    } catch (...) {
        return false;
    }
}

// --- Connection management (uses shared socket helpers) ---

int connect_session_endpoint(const SessionInfo& session) {
    if (is_file_transport(session)) return -1;
    if (is_tcp_transport(session)) {
        return xdebug_core::connect_tcp(session.host, session.port);
    }
    return xdebug_core::connect_uds(
        session.socket_path.empty() ? xdebug_design_socket_path(session.session_id) : session.socket_path);
}

// --- File transport request ---

bool send_file_request_to_endpoint(const SessionInfo& session, const Json& request, Json& response, int timeout_ms) {
    if (!is_file_transport(session)) return false;
    std::string dir = session.file_dir.empty()
        ? xdebug_core::file_transport_dir(xdebug_design_session_dir(session.session_id))
        : session.file_dir;
    int effective_timeout_ms = timeout_ms > 0 ? timeout_ms : xdebug_core::file_transport_request_timeout_ms();
    xdebug_core::FileExchangeResult result = xdebug_core::file_exchange_send_request(dir, request, effective_timeout_ms);
    if (!(result.status == "ok" || result.status == "action_error" || result.status == "server_error")) return false;
    if (!result.response.is_object()) return false;
    response = result.response;
    return true;
}

// --- Simple request/response ---

static bool request_simple(const SessionInfo& session, const std::string& action, Json& data) {
    if (is_file_transport(session)) {
        Json request = {{"api_version", INTERNAL_API_VERSION}, {"action", action}, {"args", Json::object()}};
        Json response;
        if (!send_file_request_to_endpoint(session, request, response, xdebug_core::file_transport_ping_timeout_ms()))
            return false;
        bool ok = response.value("ok", false);
        data = response.value("data", Json::object());
        return ok;
    }
    int fd = connect_session_endpoint(session);
    if (fd < 0) return false;
    Json request = {{"api_version", INTERNAL_API_VERSION}, {"action", action}, {"args", Json::object()}};
    if (is_tcp_transport(session)) request["auth_token"] = session.auth_token;
    std::string msg = request.dump() + "\n";
    bool ok = write(fd, msg.c_str(), msg.size()) == static_cast<ssize_t>(msg.size());
    std::string line;
    if (ok) {
        ok = xdebug_core::read_line_timeout(fd, line);
        if (ok) {
            try {
                Json response = Json::parse(line);
                ok = response.value("ok", false);
                data = response.value("data", Json::object());
            } catch (...) {
                ok = false;
            }
        }
    }
    close(fd);
    return ok;
}

bool ping_session_endpoint(const SessionInfo& session) {
    Json data;
    return request_simple(session, "server.ping", data) && data.value("pong", false);
}

bool protocol_version_matches_endpoint(const SessionInfo& session) {
    Json data;
    return request_simple(session, "server.version", data) &&
           data.value("api_version", std::string()) == INTERNAL_API_VERSION;
}

bool send_quit_to_endpoint(const SessionInfo& session) {
    Json data;
    return request_simple(session, "server.quit", data);
}

} // namespace xdebug_design
