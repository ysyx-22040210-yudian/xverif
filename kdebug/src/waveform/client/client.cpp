#include "client.h"
#include "../protocol/protocol.h"
#include "../session/session_manager.h"
#include "../session/session_transport.h"
#include "logging/action_log.h"

#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>

namespace kdebug_waveform {

int session_connect(const std::string& session_id) {
    SessionManager manager;
    SessionInfo session;
    if (!manager.get_session(session_id, session)) return -1;
    return connect_session_endpoint(session);
}

bool send_command_and_print(const std::string& session_id, const char* cmd) {
    SessionManager manager;
    if (!manager.ensure_session_current(session_id)) {
        SessionHealth health = manager.diagnose_session(session_id);
        fprintf(stderr, "Error: Session %s unavailable: %s (status=%s)\n",
                session_id.c_str(),
                health.message.c_str(),
                session_health_status_name(health.status));
        return false;
    }

    SessionInfo session;
    if (manager.get_session(session_id, session) && is_file_transport(session)) {
        std::string payload;
        bool server_error = false;
        if (!send_file_command_to_endpoint(session, std::string(cmd ? cmd : ""), payload, server_error)) return false;
        FILE* stream = server_error ? stderr : stdout;
        fwrite(payload.c_str(), 1, payload.size(), stream);
        fflush(stream);
        return !server_error;
    }

    int fd = session_connect(session_id);
    if (fd < 0) {
        SessionHealth health = manager.diagnose_session(session_id);
        fprintf(stderr, "Error: Session %s unavailable: %s (status=%s)\n",
                session_id.c_str(),
                health.message.c_str(),
                session_health_status_name(health.status));
        return false;
    }

    // Send command
    std::string msg = std::string(cmd) + "\n";
    if (write(fd, msg.c_str(), msg.length()) < 0) {
        close(fd);
        return false;
    }

    // Read response until END_MARKER
    std::string buf;
    const std::string end_marker(END_MARKER);
    char tmp[4096];

    bool server_error = false;
    while (true) {
        ssize_t n = read(fd, tmp, sizeof(tmp));
        if (n <= 0) break;
        buf.append(tmp, n);

        size_t pos = buf.find(end_marker);
        if (pos != std::string::npos) {
            std::string payload = buf.substr(0, pos);
            server_error = payload.compare(0, strlen(ERROR_PREFIX), ERROR_PREFIX) == 0;
            FILE* stream = server_error ? stderr : stdout;
            fwrite(payload.c_str(), 1, payload.size(), stream);
            break;
        }

        // Flush safe prefix if buffer grows large
        if (buf.size() > sizeof(tmp) + end_marker.size()) {
            size_t safe = buf.size() - end_marker.size();
            fwrite(buf.c_str(), 1, safe, stdout);
            buf.erase(0, safe);
        }
    }
    fflush(stdout);
    fflush(stderr);
    close(fd);
    return !server_error;
}

bool send_command_capture(const std::string& session_id, const char* cmd, std::string& payload) {
    payload.clear();
    SessionManager manager;
    if (!manager.ensure_session_current(session_id)) {
        kdebug_core::log_transport_event("waveform", session_id, "send_command.ensure_session_failed", false,
                                         {{"cmd", std::string(cmd ? cmd : "")}});
        return false;
    }

    SessionInfo session;
    if (manager.get_session(session_id, session) && is_file_transport(session)) {
        bool server_error = false;
        bool ok = send_file_command_to_endpoint(session, std::string(cmd ? cmd : ""), payload, server_error);
        kdebug_core::log_transport_event("waveform", session_id,
                                         ok && !server_error ? "send_command.ok" : "send_command.file_exchange_failed",
                                         ok && !server_error,
                                         {{"cmd", std::string(cmd ? cmd : "")},
                                          {"transport", session.transport}, {"file_dir", session.file_dir},
                                          {"payload_preview", payload.substr(0, 512)}});
        return ok && !server_error;
    }

    int fd = session_connect(session_id);
    if (fd < 0) {
        SessionHealth health = manager.diagnose_session(session_id);
        kdebug_core::log_transport_event("waveform", session_id, "send_command.connect_failed", false,
                                         {{"status", session_health_status_name(health.status)},
                                          {"message", health.message}, {"cmd", std::string(cmd ? cmd : "")}});
        return false;
    }

    std::string msg = std::string(cmd) + "\n";
    if (write(fd, msg.c_str(), msg.length()) < 0) {
        close(fd);
        kdebug_core::log_transport_event("waveform", session_id, "send_command.write_failed", false,
                                         {{"cmd", std::string(cmd ? cmd : "")}});
        return false;
    }

    std::string buf;
    const std::string end_marker(END_MARKER);
    char tmp[4096];
    bool server_error = false;
    while (true) {
        ssize_t n = read(fd, tmp, sizeof(tmp));
        if (n <= 0) break;
        buf.append(tmp, n);
        size_t pos = buf.find(end_marker);
        if (pos != std::string::npos) {
            payload = buf.substr(0, pos);
            server_error = payload.compare(0, strlen(ERROR_PREFIX), ERROR_PREFIX) == 0;
            break;
        }
    }
    close(fd);
    if (payload.empty() && !server_error) {
        kdebug_core::log_transport_event("waveform", session_id, "send_command.read_or_marker_failed", false,
                                         {{"cmd", std::string(cmd ? cmd : "")}});
        return false;
    }
    kdebug_core::log_transport_event("waveform", session_id,
                                     server_error ? "send_command.server_error" : "send_command.ok",
                                     !server_error,
                                     {{"cmd", std::string(cmd ? cmd : "")},
                                      {"payload_preview", payload.substr(0, 512)}});
    return !server_error;
}

bool session_ping(const std::string& session_id) {
    SessionManager manager;
    SessionInfo session;
    if (manager.get_session(session_id, session) && is_file_transport(session)) {
        return ping_session_endpoint(session);
    }
    int fd = session_connect(session_id);
    if (fd < 0) return false;

    const char* ping = CMD_PING "\n";
    if (write(fd, ping, strlen(ping)) < 0) {
        close(fd);
        kdebug_core::log_transport_event("waveform", session_id, "ping.write_failed", false);
        return false;
    }

    // Wait for PONG with timeout
    char buf[64];
    struct timeval tv;
    tv.tv_sec = 2;
    tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    bool got_pong = false;
    ssize_t n = read(fd, buf, sizeof(buf) - 1);
    if (n > 0) {
        buf[n] = '\0';
        if (strstr(buf, "PONG")) {
            got_pong = true;
        }
    }

    close(fd);
    kdebug_core::log_transport_event("waveform", session_id, got_pong ? "ping.ok" : "ping.timeout_or_invalid", got_pong);
    return got_pong;
}

} // namespace kdebug_waveform
