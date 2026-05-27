#include "server_internal.h"

namespace xdebug_waveform {

int server_main(int argc, char** argv) {
    // argv: [exe, session_id, fsdb_file]
    if (argc < 3) {
        fprintf(stderr, "Server mode requires session_id and fsdb_file arguments\n");
        return 1;
    }

    int arg_idx = 1;

    // Parse session ID
    g_session_id = argv[arg_idx];
    if (!SessionRegistry::is_valid_session_name(g_session_id)) {
        fprintf(stderr, "Invalid session ID: %s\n", argv[arg_idx]);
        return 1;
    }
    server_debug_open_log();
    server_debug_log("server_main: parsed_session_id=%s", g_session_id.c_str());
    arg_idx++;

    // Parse FSDB file
    const char* fsdb_file = argv[arg_idx];
    g_fsdb_file_path = fsdb_file;
    arg_idx++;
    while (arg_idx < argc) {
        std::string opt = argv[arg_idx++];
        if (opt == "--transport" && arg_idx < argc) g_transport = argv[arg_idx++];
        else if (opt == "--bind" && arg_idx < argc) g_bind_host = argv[arg_idx++];
        else if (opt == "--host" && arg_idx < argc) g_host = argv[arg_idx++];
        else if (opt == "--port" && arg_idx < argc) g_port = atoi(argv[arg_idx++]);
        else if (opt == "--auth" && arg_idx < argc) g_auth_token = argv[arg_idx++];
    }
    if (g_transport.empty()) g_transport = "uds";
    if (g_transport == "tcp") {
        if (g_bind_host.empty()) g_bind_host = "127.0.0.1";
        if (g_host.empty()) {
            g_host = (g_bind_host == "0.0.0.0" || g_bind_host == "::") ? current_host_name() : g_bind_host;
        }
    }
    server_debug_log("server_main: transport=%s bind=%s host=%s port=%d",
                     g_transport.c_str(), g_bind_host.c_str(), g_host.c_str(), g_port);
    stat_fsdb(g_fsdb_mtime, g_fsdb_size, g_fsdb_dev, g_fsdb_inode);
    server_debug_log("server_main: fsdb=%s stat mtime=%ld size=%lld dev=%llu inode=%llu",
                     fsdb_file, g_fsdb_mtime, g_fsdb_size, g_fsdb_dev, g_fsdb_inode);

    // Redirect stdout to capture NPI init messages, but keep a copy
    int stdout_copy = dup(STDOUT_FILENO);

    // Initialize NPI
    int npi_argc = 1;
    char** npi_argv = argv;
    server_debug_log("server_main: npi_init_begin");
    int result = npi_init(npi_argc, npi_argv);
    if (result == 0) {
        server_debug_log("server_main: npi_init_failed");
        dprintf(stdout_copy, "[Session %s] ERROR: npi_init failed\n", g_session_id.c_str());
        close(stdout_copy);
        if (g_debug_log) {
            fclose(g_debug_log);
            g_debug_log = nullptr;
        }
        return 1;
    }
    server_debug_log("server_main: npi_init_ok");

    server_debug_log("server_main: npi_fsdb_open_begin fsdb=%s", fsdb_file);
    g_fsdb_file = npi_fsdb_open(fsdb_file);
    if (!g_fsdb_file) {
        server_debug_log("server_main: npi_fsdb_open_failed fsdb=%s", fsdb_file);
        dprintf(stdout_copy, "[Session %s] ERROR: npi_fsdb_open failed: %s\n", g_session_id.c_str(), fsdb_file);
        npi_end();
        close(stdout_copy);
        if (g_debug_log) {
            fclose(g_debug_log);
            g_debug_log = nullptr;
        }
        return 1;
    }
    server_debug_log("server_main: npi_fsdb_open_ok");

    npiFsdbTime minTime, maxTime;
    npi_fsdb_min_time(g_fsdb_file, &minTime);
    npi_fsdb_max_time(g_fsdb_file, &maxTime);
    server_debug_log("server_main: fsdb_time min=%llu max=%llu", minTime, maxTime);

    dprintf(stdout_copy, "[Session %s] Ready (FSDB: %llu ~ %llu)\n", g_session_id.c_str(), minTime, maxTime);
    fflush(stdout);
    close(stdout_copy);

    // Now daemonize I/O
    server_debug_log("server_main: daemonize_io");
    daemonize_io();

    // Set up signal handlers
    signal(SIGTERM, cleanup_and_exit);
    signal(SIGINT, cleanup_and_exit);

    get_sock_path(g_sock_path, g_session_id);
    if (g_transport == "tcp") {
        server_debug_log("server_main: tcp_socket_create_begin");
        struct addrinfo hints;
        memset(&hints, 0, sizeof(hints));
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;
        hints.ai_flags = AI_PASSIVE;
        std::string port_s = std::to_string(g_port);
        struct addrinfo* res = nullptr;
        int gai = getaddrinfo(g_bind_host.c_str(), port_s.c_str(), &hints, &res);
        if (gai != 0) {
            server_debug_log("server_main: tcp_getaddrinfo_failed %s", gai_strerror(gai));
            npi_fsdb_close(g_fsdb_file);
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
            server_debug_log("server_main: tcp_bind_failed errno=%d(%s)", errno, strerror(errno));
            npi_fsdb_close(g_fsdb_file);
            npi_end();
            return 1;
        }
        struct sockaddr_storage ss;
        socklen_t slen = sizeof(ss);
        if (getsockname(g_srv_fd, reinterpret_cast<struct sockaddr*>(&ss), &slen) == 0) {
            if (ss.ss_family == AF_INET) {
                g_port = ntohs(reinterpret_cast<struct sockaddr_in*>(&ss)->sin_port);
            } else if (ss.ss_family == AF_INET6) {
                g_port = ntohs(reinterpret_cast<struct sockaddr_in6*>(&ss)->sin6_port);
            }
        }
        server_debug_log("server_main: tcp_bind_ok host=%s port=%d", g_host.c_str(), g_port);
    } else {
        server_debug_log("server_main: uds_socket_create_begin");
        g_srv_fd = socket(AF_UNIX, SOCK_STREAM, 0);
        if (g_srv_fd < 0) {
            server_debug_log("server_main: socket_create_failed errno=%d(%s)", errno, strerror(errno));
            npi_fsdb_close(g_fsdb_file);
            npi_end();
            if (g_debug_log) {
                fclose(g_debug_log);
                g_debug_log = nullptr;
            }
            return 1;
        }
        unlink(g_sock_path);
        server_debug_log("server_main: socket_path=%s", g_sock_path);
        struct sockaddr_un addr;
        memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, g_sock_path, sizeof(addr.sun_path) - 1);
        if (bind(g_srv_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            server_debug_log("server_main: socket_bind_failed errno=%d(%s)", errno, strerror(errno));
            close(g_srv_fd);
            npi_fsdb_close(g_fsdb_file);
            npi_end();
            if (g_debug_log) {
                fclose(g_debug_log);
                g_debug_log = nullptr;
            }
            return 1;
        }
        chmod(g_sock_path, 0600);
        server_debug_log("server_main: uds_bind_ok");
    }

    server_debug_log("server_main: socket_listen_begin");
    if (listen(g_srv_fd, 8) < 0) {
        server_debug_log("server_main: socket_listen_failed errno=%d(%s)", errno, strerror(errno));
        close(g_srv_fd);
        unlink(g_sock_path);
        npi_fsdb_close(g_fsdb_file);
        npi_end();
        if (g_debug_log) {
            fclose(g_debug_log);
            g_debug_log = nullptr;
        }
        return 1;
    }
    server_debug_log("server_main: socket_listen_ok");

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
        if (!write_endpoint_file(endpoint)) {
            server_debug_log("server_main: endpoint_write_failed");
        } else {
            server_debug_log("server_main: endpoint_write_ok transport=%s host=%s port=%d",
                             endpoint.transport.c_str(), endpoint.host.c_str(), endpoint.port);
        }
    }

    const char* env_timeout = getenv("XDEBUG_WAVEFORM_IDLE_TIMEOUT_SEC");
    int idle_timeout = env_timeout ? atoi(env_timeout) : 1800;
    if (idle_timeout <= 0) idle_timeout = 1800;
    server_debug_log("server_main: idle_timeout_sec=%d", idle_timeout);
    time_t last_active = time(nullptr);
    bool idle_timeout_exit = false;
    bool quit_requested = false;

    // Accept loop
    while (true) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(g_srv_fd, &rfds);
        struct timeval tv;
        tv.tv_sec = 1;
        tv.tv_usec = 0;
        int ready = select(g_srv_fd + 1, &rfds, nullptr, nullptr, &tv);
        if (ready < 0) continue;
        if (ready == 0) {
            if (time(nullptr) - last_active > idle_timeout) {
                idle_timeout_exit = true;
                server_debug_log("server_main: idle_timeout_exit idle_sec=%ld timeout_sec=%d",
                                  static_cast<long>(time(nullptr) - last_active),
                                  idle_timeout);
                break;
            }
            continue;
        }

        int client_fd = accept(g_srv_fd, nullptr, nullptr);
        if (client_fd < 0) continue;

        bool quit = false;
        handle_client(client_fd, quit);
        close(client_fd);
        last_active = time(nullptr);

        if (quit) {
            quit_requested = true;
            server_debug_log("server_main: quit_requested");
            break;
        }
    }

    // Cleanup
    server_debug_log("server_main: cleanup_begin reason=%s",
                     idle_timeout_exit ? "idle_timeout" :
                     (quit_requested ? "quit" : "loop_exit"));
    close(g_srv_fd);
    unlink(g_sock_path);
    if (g_fsdb_file) {
        npi_fsdb_close(g_fsdb_file);
        g_fsdb_file = nullptr;
    }
    {
        SessionRegistry registry;
        registry.remove(g_session_id);
    }
    npi_end();
    if (g_debug_log) {
        server_debug_log("server_main: normal_exit");
        fclose(g_debug_log);
        g_debug_log = nullptr;
    }

    return 0;
}

} // namespace xdebug_waveform
