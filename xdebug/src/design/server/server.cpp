#include "server.h"
#include "../common/xdebug_design_paths.h"
#include "../protocol/protocol.h"
#include "../trace/trace_engine.h"
#include "../signal/signal_finder.h"
#include "../port/port_analyzer.h"
#include "../session/session_registry.h"
#include "../session/session_transport.h"
#include "json.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <sstream>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/stat.h>
#include <signal.h>
#include <cstdarg>
#include <strings.h>

#include "npi.h"

namespace xdebug_design {

using Json = nlohmann::ordered_json;

// Global for cleanup
static std::string g_session_id;
static int g_srv_fd = -1;
static char g_sock_path[SOCK_PATH_LEN];
static std::string g_transport = "uds";
static std::string g_bind_host;
static std::string g_host;
static int g_port = 0;
static std::string g_auth_token;
static FILE* g_debug_log = nullptr;

static bool server_debug_enabled() {
    const char* env = getenv("XDEBUG_DESIGN_DEBUG");
    return env && env[0] != '\0' && strcmp(env, "0") != 0 &&
           strcasecmp(env, "false") != 0 && strcasecmp(env, "off") != 0;
}

static void server_debug_open_log() {
    if (!server_debug_enabled() || g_session_id.empty()) return;
    xdebug_design_ensure_session_dir(g_session_id);
    char log_path[SOCK_PATH_LEN];
    get_debug_log_path(log_path, g_session_id);
    g_debug_log = fopen(log_path, "a");
    if (g_debug_log) {
        chmod(log_path, 0600);
        fprintf(g_debug_log, "=== xdebug_design server debug session=%s ===\n", g_session_id.c_str());
        fflush(g_debug_log);
    }
}

static void server_debug_log(const char* fmt, ...) {
    if (!g_debug_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_debug_log, fmt, ap);
    va_end(ap);
    fprintf(g_debug_log, "\n");
    fflush(g_debug_log);
}

static void cleanup_and_exit(int sig) {
    server_debug_log("signal_exit sig=%d", sig);
    if (g_srv_fd >= 0) {
        close(g_srv_fd);
    }
    if (strlen(g_sock_path) > 0) {
        unlink(g_sock_path);
    }
    if (g_debug_log) {
        fclose(g_debug_log);
        g_debug_log = nullptr;
    }
    // Note: npi_end not called here because signal handler context
    exit(0);
}

static void daemonize_io() {
    int devnull = open("/dev/null", O_RDWR);
    if (devnull >= 0) {
        dup2(devnull, STDIN_FILENO);
        dup2(devnull, STDOUT_FILENO);
        dup2(devnull, STDERR_FILENO);
        close(devnull);
    }
}

static bool send_all(int fd, const char* buf, size_t len) {
    size_t sent = 0;
    while (sent < len) {
        ssize_t n = write(fd, buf + sent, len - sent);
        if (n <= 0) return false;
        sent += n;
    }
    return true;
}

static bool read_command_line(int fd, char* line, size_t line_size) {
    size_t total = 0;
    while (total < line_size - 1) {
        ssize_t n = read(fd, line + total, 1);
        if (n <= 0) return false;
        if (line[total] == '\n') break;
        total++;
    }
    line[total] = '\0';
    return true;
}

static TraceOptions parse_trace_options(const Json& args) {
    TraceOptions options;
    options.limit = args.value("limit", 0);
    options.role = args.value("role", std::string());
    options.no_statement_only = args.value("no_statement_only", false);
    if (args.contains("include_statement_only") && args["include_statement_only"].is_boolean()) {
        options.no_statement_only = !args["include_statement_only"].get<bool>();
    }
    return options;
}

static Json ok_response(const Json& data = Json::object()) {
    return {{"api_version", INTERNAL_API_VERSION}, {"ok", true}, {"data", data}, {"error", nullptr}};
}

static Json error_response(const std::string& code, const std::string& message) {
    return {{"api_version", INTERNAL_API_VERSION}, {"ok", false}, {"status", "server_error"},
            {"data", nullptr}, {"error", {{"code", code}, {"message", message}}}};
}

static bool send_response(int fd, const Json& response) {
    std::string wire = response.dump() + "\n";
    return send_all(fd, wire.c_str(), wire.size());
}

static Json trace_request(const Json& args, TraceMode mode) {
    std::string signal = args.value("signal", std::string());
    if (signal.empty()) return error_response("MISSING_FIELD", "args.signal is required");
    TraceEngine engine;
    TraceResult result = engine.trace(signal, mode, parse_trace_options(args));
    return ok_response(Json::parse(engine.render_ai_json(result)));
}

static Json signal_resolve_request(const Json& args) {
    std::string signal = args.value("signal", std::string());
    if (signal.empty()) return error_response("MISSING_FIELD", "args.signal is required");
    SignalFinder finder;
    SignalResolveResult result = finder.resolve(signal);
    return ok_response(Json::parse(finder.render_json(result)));
}

static Json port_request(const Json& args, const std::string& action) {
    std::string path = args.value("path", std::string());
    if (path.empty()) return error_response("MISSING_FIELD", "args.path is required");
    int limit = args.value("limit", 0);
    PortAnalyzer analyzer;
    std::string payload;
    if (action == "port.trace") {
        payload = analyzer.render_port_trace(path, limit);
    } else if (action == "instance.map") {
        payload = analyzer.render_instance_map(path);
    } else {
        payload = analyzer.render_interface_resolve(path);
    }
    return ok_response(Json::parse(payload));
}

static bool handle_client(int client_fd, bool& should_quit) {
    should_quit = false;
    char line[1024 * 1024] = {};
    if (!read_command_line(client_fd, line, sizeof(line))) return false;
    Json request;
    try {
        request = Json::parse(line);
    } catch (...) {
        return send_response(client_fd, error_response("INVALID_JSON", "request must be a JSON object"));
    }
    if (request.value("api_version", std::string()) != INTERNAL_API_VERSION) {
        return send_response(client_fd, error_response("UNSUPPORTED_API_VERSION", "expected xdebug.internal.v1"));
    }
    if (g_transport == "tcp" && request.value("auth_token", std::string()) != g_auth_token) {
        return send_response(client_fd, error_response("AUTH_FAILED", "authentication failed"));
    }
    const std::string action = request.value("action", std::string());
    const Json args = request.value("args", Json::object());
    if (action == "server.quit") {
        send_response(client_fd, ok_response());
        should_quit = true;
        return true;
    }
    if (action == "server.ping") return send_response(client_fd, ok_response({{"pong", true}}));
    if (action == "server.version") {
        return send_response(client_fd, ok_response({{"api_version", INTERNAL_API_VERSION}}));
    }
    if (action == "trace.driver") return send_response(client_fd, trace_request(args, TraceMode::Driver));
    if (action == "trace.load") return send_response(client_fd, trace_request(args, TraceMode::Load));
    if (action == "signal.resolve") return send_response(client_fd, signal_resolve_request(args));
    if (action == "port.trace" || action == "instance.map" || action == "interface.resolve") {
        return send_response(client_fd, port_request(args, action));
    }
    return send_response(client_fd, error_response("UNKNOWN_ACTION", "unknown internal action: " + action));
}

int server_main(int argc, char** argv) {
    // argv: [exe, session_id, ...design_args...]
    if (argc < 2) {
        fprintf(stderr, "Server mode requires session_id argument\n");
        return 1;
    }

    int arg_idx = 1;

    // Parse session ID
    g_session_id = argv[arg_idx];
    if (g_session_id.empty()) {
        fprintf(stderr, "Invalid session ID: %s\n", argv[arg_idx]);
        return 1;
    }
    arg_idx++;
    server_debug_open_log();
    server_debug_log("server_main: parsed session_id=%s argc=%d", g_session_id.c_str(), argc);

    std::vector<std::string> design_args;
    while (arg_idx < argc) {
        std::string opt = argv[arg_idx++];
        if (opt == "--transport" && arg_idx < argc) g_transport = argv[arg_idx++];
        else if (opt == "--bind" && arg_idx < argc) g_bind_host = argv[arg_idx++];
        else if (opt == "--host" && arg_idx < argc) g_host = argv[arg_idx++];
        else if (opt == "--port" && arg_idx < argc) g_port = atoi(argv[arg_idx++]);
        else if (opt == "--auth" && arg_idx < argc) g_auth_token = argv[arg_idx++];
        else design_args.push_back(opt);
    }
    if (g_transport == "tcp") {
        if (g_bind_host.empty()) g_bind_host = "127.0.0.1";
        if (g_host.empty()) {
            g_host = (g_bind_host == "0.0.0.0" || g_bind_host == "::") ? current_host_name() : g_bind_host;
        }
    }
    server_debug_log("server_main: transport=%s bind=%s host=%s port=%d",
                     g_transport.c_str(), g_bind_host.c_str(), g_host.c_str(), g_port);

    // Build design args for NPI: [exe, ...design_args...]
    int npi_argc = static_cast<int>(design_args.size()) + 1;
    char** npi_argv = new char*[npi_argc];
    npi_argv[0] = argv[0];  // exe name
    for (int i = 1; i < npi_argc; i++) {
        npi_argv[i] = const_cast<char*>(design_args[i - 1].c_str());
    }

    // Keep session startup quiet so CLI JSON output remains machine-parseable.
    daemonize_io();

    // Initialize NPI
    server_debug_log("npi_init: begin argc=%d", npi_argc);
    int result = npi_init(npi_argc, npi_argv);
    if (result == 0) {
        server_debug_log("npi_init: failed");
        delete[] npi_argv;
        return 1;
    }
    server_debug_log("npi_init: ok");

    server_debug_log("npi_load_design: begin");
    result = npi_load_design(npi_argc, npi_argv);
    if (result == 0) {
        server_debug_log("npi_load_design: failed");
        npi_end();
        delete[] npi_argv;
        return 1;
    }
    server_debug_log("npi_load_design: ok");

    delete[] npi_argv;

    // Set up signal handlers
    signal(SIGTERM, cleanup_and_exit);
    signal(SIGINT, cleanup_and_exit);

    get_sock_path(g_sock_path, g_session_id);
    if (g_transport == "tcp") {
        struct addrinfo hints;
        memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_flags = AI_PASSIVE;
        struct addrinfo* res = nullptr;
        std::string port_s = std::to_string(g_port);
        int gai = getaddrinfo(g_bind_host.c_str(), port_s.c_str(), &hints, &res);
        if (gai != 0) {
            server_debug_log("tcp getaddrinfo failed: %s", gai_strerror(gai));
            npi_end();
            return 1;
        }
        for (struct addrinfo* p = res; p; p = p->ai_next) {
            g_srv_fd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
            if (g_srv_fd < 0) continue;
            int one = 1;
            setsockopt(g_srv_fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
            if (bind(g_srv_fd, p->ai_addr, p->ai_addrlen) == 0) break;
            close(g_srv_fd);
            g_srv_fd = -1;
        }
        freeaddrinfo(res);
        if (g_srv_fd < 0) {
            server_debug_log("tcp bind failed");
            npi_end();
            return 1;
        }
        struct sockaddr_storage ss;
        socklen_t slen = sizeof(ss);
        if (getsockname(g_srv_fd, reinterpret_cast<struct sockaddr*>(&ss), &slen) == 0) {
            if (ss.ss_family == AF_INET) g_port = ntohs(reinterpret_cast<struct sockaddr_in*>(&ss)->sin_port);
            else if (ss.ss_family == AF_INET6) g_port = ntohs(reinterpret_cast<struct sockaddr_in6*>(&ss)->sin6_port);
        }
        server_debug_log("tcp bind ok host=%s port=%d", g_host.c_str(), g_port);
    } else {
        g_srv_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (g_srv_fd < 0) {
            server_debug_log("socket: failed");
            npi_end();
            return 1;
        }
        unlink(g_sock_path);
        server_debug_log("socket_path: %s", g_sock_path);
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, g_sock_path, sizeof(addr.sun_path) - 1);
        if (bind(g_srv_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            server_debug_log("bind: failed path=%s", g_sock_path);
            close(g_srv_fd);
            npi_end();
            return 1;
        }
        chmod(g_sock_path, 0600);
        server_debug_log("bind: ok");
    }

    if (listen(g_srv_fd, 8) < 0) {
        server_debug_log("listen: failed");
        close(g_srv_fd);
        unlink(g_sock_path);
        npi_end();
        return 1;
    }
    server_debug_log("listen: ok");

    {
        SessionInfo endpoint;
        endpoint.session_id = g_session_id;
        endpoint.transport = g_transport;
        endpoint.socket_path = g_sock_path;
        endpoint.host = g_transport == "tcp" ? g_host : "";
        endpoint.bind_host = g_transport == "tcp" ? g_bind_host : "";
        endpoint.port = g_transport == "tcp" ? g_port : 0;
        endpoint.server_host = current_host_name();
        endpoint.auth_token = g_transport == "tcp" ? g_auth_token : "";
        write_endpoint_file(endpoint);
    }

    // Accept loop
    while (true) {
        int client_fd = accept(g_srv_fd, nullptr, nullptr);
        if (client_fd < 0) continue;

        bool quit = false;
        handle_client(client_fd, quit);
        close(client_fd);

        if (quit) break;
    }

    // Cleanup
    server_debug_log("normal_exit: cleanup begin");
    close(g_srv_fd);
    unlink(g_sock_path);
    npi_end();
    server_debug_log("normal_exit: cleanup done");
    if (g_debug_log) {
        fclose(g_debug_log);
        g_debug_log = nullptr;
    }

    return 0;
}

} // namespace xdebug_design
