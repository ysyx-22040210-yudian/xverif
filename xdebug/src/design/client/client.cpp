#include "client.h"

#include "../protocol/protocol.h"
#include "../session/session_manager.h"
#include "../session/session_transport.h"

#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

namespace xdebug_design {

int session_connect(const std::string& session_id) {
    SessionManager manager;
    SessionInfo session;
    if (!manager.get_session(session_id, session)) return -1;
    return connect_session_endpoint(session);
}

static bool write_json_line(int fd, const Json& request) {
    std::string wire = request.dump() + "\n";
    return write(fd, wire.c_str(), wire.size()) == static_cast<ssize_t>(wire.size());
}

static bool read_json_line(int fd, Json& response) {
    struct timeval tv = {2, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    std::string line;
    char c = 0;
    while (line.size() <= 1024 * 1024) {
        ssize_t n = read(fd, &c, 1);
        if (n <= 0) return false;
        if (c == '\n') {
            try {
                response = Json::parse(line);
                return true;
            } catch (...) {
                return false;
            }
        }
        line.push_back(c);
    }
    return false;
}

bool send_request_capture(const std::string& session_id,
                          const Json& request,
                          Json& data,
                          std::string& status,
                          std::string& message) {
    SessionManager manager;
    SessionInfo session;
    if (!manager.get_session(session_id, session)) {
        status = "session_not_found";
        message = "session not found";
        return false;
    }
    int fd = connect_session_endpoint(session);
    if (fd < 0) {
        SessionHealth health = manager.diagnose_session(session_id);
        status = session_health_status_name(health.status);
        message = health.message;
        return false;
    }

    Json rpc = request;
    rpc["api_version"] = INTERNAL_API_VERSION;
    if (is_tcp_transport(session)) rpc["auth_token"] = session.auth_token;
    Json response;
    bool received = write_json_line(fd, rpc) && read_json_line(fd, response);
    close(fd);
    if (!received) {
        status = "transport_failed";
        message = "failed to exchange JSON request with session";
        return false;
    }
    if (!response.value("ok", false)) {
        status = response.value("status", std::string("server_error"));
        message = response.value("error", Json::object()).value("message", std::string("server request failed"));
        return false;
    }
    data = response.value("data", Json::object());
    manager.touch_session(session_id);
    status = "ok";
    message.clear();
    return true;
}

bool session_ping(const std::string& session_id) {
    Json data;
    std::string status;
    std::string message;
    return send_request_capture(session_id,
                                {{"api_version", INTERNAL_API_VERSION},
                                 {"action", "server.ping"},
                                 {"args", Json::object()}},
                                data, status, message) &&
           data.value("pong", false);
}

}  // namespace xdebug_design
