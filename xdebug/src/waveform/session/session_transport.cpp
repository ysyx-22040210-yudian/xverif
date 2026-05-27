#include "session_transport.h"
#include "../common/xdebug_waveform_paths.h"
#include "json.hpp"
#include "../protocol/protocol.h"

#include <arpa/inet.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fcntl.h>
#include <netdb.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

std::string current_host_name() {
    char buf[256] = {};
    if (gethostname(buf, sizeof(buf) - 1) == 0 && buf[0]) return std::string(buf);
    return "localhost";
}

std::string generate_auth_token() {
    unsigned char bytes[24] = {};
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd >= 0) {
        ssize_t n = read(fd, bytes, sizeof(bytes));
        close(fd);
        if (n != static_cast<ssize_t>(sizeof(bytes))) memset(bytes, 0, sizeof(bytes));
    }
    if (bytes[0] == 0 && bytes[1] == 0) {
        unsigned long long seed = static_cast<unsigned long long>(time(nullptr)) ^
                                  (static_cast<unsigned long long>(getpid()) << 32);
        for (size_t i = 0; i < sizeof(bytes); ++i) {
            seed = seed * 6364136223846793005ULL + 1;
            bytes[i] = static_cast<unsigned char>(seed >> 24);
        }
    }
    static const char hex[] = "0123456789abcdef";
    std::string out;
    out.reserve(sizeof(bytes) * 2);
    for (unsigned char b : bytes) {
        out.push_back(hex[b >> 4]);
        out.push_back(hex[b & 0xf]);
    }
    return out;
}

bool is_tcp_transport(const SessionInfo& session) {
    return session.transport == "tcp";
}

bool is_local_session_host(const SessionInfo& session) {
    return session.server_host.empty() || session.server_host == current_host_name() ||
           session.server_host == "localhost" || session.server_host == "127.0.0.1";
}

bool write_endpoint_file(const SessionInfo& session) {
    if (!xdebug_waveform_ensure_session_dir(session.session_id)) return false;
    Json root = {
        {"version", 1},
        {"endpoint", {
            {"transport", session.transport.empty() ? "uds" : session.transport},
            {"socket_path", session.socket_path},
            {"host", session.host},
            {"bind_host", session.bind_host},
            {"port", session.port},
            {"server_host", session.server_host},
            {"auth_token", session.auth_token}
        }}
    };
    std::string data = root.dump(2) + "\n";
    std::string path = xdebug_waveform_endpoint_path(session.session_id);
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return false;
    bool ok = write(fd, data.c_str(), data.size()) == static_cast<ssize_t>(data.size());
    close(fd);
    return ok;
}

bool read_endpoint_file(const std::string& session_id, SessionInfo& endpoint) {
    std::string path = xdebug_waveform_endpoint_path(session_id);
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
        endpoint.socket_path = e.value("socket_path", xdebug_waveform_socket_path(session_id));
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

static int connect_uds(const std::string& path) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
    if (connect(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static int connect_tcp(const std::string& host, int port) {
    if (host.empty() || port <= 0) return -1;
    struct addrinfo hints;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    std::string port_s = std::to_string(port);
    struct addrinfo* res = nullptr;
    if (getaddrinfo(host.c_str(), port_s.c_str(), &hints, &res) != 0) return -1;
    int fd = -1;
    for (struct addrinfo* p = res; p; p = p->ai_next) {
        fd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
        if (fd < 0) continue;
        if (connect(fd, p->ai_addr, p->ai_addrlen) == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

static bool read_line_timeout(int fd, std::string& line) {
    line.clear();
    struct timeval tv;
    tv.tv_sec = 2;
    tv.tv_usec = 0;
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    char c = 0;
    while (true) {
        ssize_t n = read(fd, &c, 1);
        if (n <= 0) return false;
        if (c == '\n') return true;
        line.push_back(c);
        if (line.size() > 4096) return false;
    }
}

static bool authenticate_tcp(int fd, const std::string& token) {
    std::string msg = std::string(CMD_AUTH) + " " + token + "\n";
    if (write(fd, msg.c_str(), msg.size()) != static_cast<ssize_t>(msg.size())) return false;
    std::string line;
    if (!read_line_timeout(fd, line)) return false;
    return line == "OK";
}

int connect_session_endpoint(const SessionInfo& session) {
    if (is_tcp_transport(session)) {
        int fd = connect_tcp(session.host, session.port);
        if (fd < 0) return -1;
        if (!authenticate_tcp(fd, session.auth_token)) {
            close(fd);
            return -1;
        }
        return fd;
    }
    return connect_uds(session.socket_path.empty() ? xdebug_waveform_socket_path(session.session_id) : session.socket_path);
}

bool ping_session_endpoint(const SessionInfo& session) {
    int fd = connect_session_endpoint(session);
    if (fd < 0) return false;
    const char* ping = CMD_PING "\n";
    bool ok = write(fd, ping, strlen(ping)) == static_cast<ssize_t>(strlen(ping));
    std::string line;
    if (ok) ok = read_line_timeout(fd, line) && line.find("PONG") != std::string::npos;
    close(fd);
    return ok;
}

bool send_quit_to_endpoint(const SessionInfo& session) {
    int fd = connect_session_endpoint(session);
    if (fd < 0) return false;
    const char* quit = CMD_QUIT "\n";
    bool ok = write(fd, quit, strlen(quit)) == static_cast<ssize_t>(strlen(quit));
    close(fd);
    return ok;
}

} // namespace xdebug_waveform
