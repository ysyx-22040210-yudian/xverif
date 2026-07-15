#include "session_transport.h"
#include "../common/kdebug_waveform_paths.h"
#include "json.hpp"
#include "../protocol/protocol.h"
#include "transport/file_exchange.h"
#include "session/transport_timeout.h"
#include "session/transport_common.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <unistd.h>

namespace kdebug_waveform {

using Json = nlohmann::ordered_json;

// --- Re-exported shared utilities (called by session_manager, server, etc.) ---

std::string current_host_name() {
    return kdebug_core::current_host_name();
}

std::string generate_auth_token() {
    return kdebug_core::generate_auth_token();
}

// --- Transport type helpers ---

bool is_tcp_transport(const SessionInfo& session) {
    return kdebug_core::is_tcp_transport(session.transport);
}

bool is_file_transport(const SessionInfo& session) {
    return kdebug_core::is_file_transport(session.transport);
}

bool is_local_session_host(const SessionInfo& session) {
    return kdebug_core::is_local_session_host(session.server_host);
}

// --- Endpoint file I/O ---

bool write_endpoint_file(const SessionInfo& session) {
    if (!kdebug_waveform_ensure_session_dir(session.session_id)) return false;
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
    return kdebug_core::atomic_write_json_file(kdebug_waveform_endpoint_path(session.session_id), root);
}

bool read_endpoint_file(const std::string& session_id, SessionInfo& endpoint) {
    std::string path = kdebug_waveform_endpoint_path(session_id);
    FILE* fp = fopen(path.c_str(), "r");
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
        endpoint.socket_path = e.value("socket_path", kdebug_waveform_socket_path(session_id));
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

// --- TCP authentication (waveform-specific: uses CMD_AUTH text protocol) ---

static bool authenticate_tcp(int fd, const std::string& token) {
    std::string msg = std::string(CMD_AUTH) + " " + token + "\n";
    if (write(fd, msg.c_str(), msg.size()) != static_cast<ssize_t>(msg.size())) return false;
    std::string line;
    if (!kdebug_core::read_line_timeout(fd, line)) return false;
    return line == "OK";
}

// --- Connection management ---

int connect_session_endpoint(const SessionInfo& session) {
    if (is_file_transport(session)) return -1;
    if (is_tcp_transport(session)) {
        int fd = kdebug_core::connect_tcp(session.host, session.port);
        if (fd < 0) return -1;
        if (!authenticate_tcp(fd, session.auth_token)) {
            close(fd);
            return -1;
        }
        return fd;
    }
    return kdebug_core::connect_uds(
        session.socket_path.empty() ? kdebug_waveform_socket_path(session.session_id) : session.socket_path);
}

// --- File transport command ---

bool send_file_command_to_endpoint(const SessionInfo& session,
                                   const std::string& command,
                                   std::string& payload,
                                   bool& server_error,
                                   int timeout_ms) {
    payload.clear();
    server_error = false;
    if (!is_file_transport(session)) return false;
    std::string dir = session.file_dir.empty()
        ? kdebug_core::file_transport_dir(kdebug_waveform_session_dir(session.session_id))
        : session.file_dir;
    Json request = {{"command", command}};
    int effective_timeout_ms = timeout_ms > 0 ? timeout_ms : kdebug_core::file_transport_request_timeout_ms();
    kdebug_core::FileExchangeResult result = kdebug_core::file_exchange_send_request(dir, request, effective_timeout_ms);
    if (!(result.status == "ok" || result.status == "action_error" || result.status == "server_error")) return false;
    if (!result.response.is_object()) return false;
    payload = result.response.value("payload", std::string());
    server_error = result.response.value("server_error", false);
    return true;
}

// --- Ping / Quit ---

bool ping_session_endpoint(const SessionInfo& session) {
    if (is_file_transport(session)) {
        std::string payload;
        bool server_error = false;
        return send_file_command_to_endpoint(session, CMD_PING, payload, server_error,
                                             kdebug_core::file_transport_ping_timeout_ms()) &&
               !server_error && payload.find("PONG") != std::string::npos;
    }
    int fd = connect_session_endpoint(session);
    if (fd < 0) return false;
    const char* ping = CMD_PING "\n";
    bool ok = write(fd, ping, strlen(ping)) == static_cast<ssize_t>(strlen(ping));
    std::string line;
    if (ok) ok = kdebug_core::read_line_timeout(fd, line) && line.find("PONG") != std::string::npos;
    close(fd);
    return ok;
}

bool send_quit_to_endpoint(const SessionInfo& session) {
    if (is_file_transport(session)) {
        std::string payload;
        bool server_error = false;
        return send_file_command_to_endpoint(session, CMD_QUIT, payload, server_error,
                                             kdebug_core::file_transport_ping_timeout_ms()) && !server_error;
    }
    int fd = connect_session_endpoint(session);
    if (fd < 0) return false;
    const char* quit = CMD_QUIT "\n";
    bool ok = write(fd, quit, strlen(quit)) == static_cast<ssize_t>(strlen(quit));
    close(fd);
    return ok;
}

} // namespace kdebug_waveform
