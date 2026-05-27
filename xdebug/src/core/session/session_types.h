#pragma once

#include <ctime>
#include <string>
#include <vector>
#include <sys/types.h>

namespace xdebug_core {

enum class DatabaseKind {
    Fsdb,
    Daidir
};

struct Fingerprint {
    long mtime;
    long long size;
    unsigned long long dev;
    unsigned long long inode;

    Fingerprint();
};

struct DatabaseRef {
    DatabaseKind kind;
    std::string canonical_path;
    std::vector<std::string> original_args;

    DatabaseRef();
};

struct SessionInfo {
    std::string session_id;
    std::string transport;
    std::string socket_path;
    std::string host;
    std::string bind_host;
    int port;
    std::string server_host;
    std::string auth_token;
    std::string database_path;
    DatabaseKind database_kind;
    Fingerprint fingerprint;
    pid_t server_pid;
    time_t created_at;
    time_t last_active;

    SessionInfo();
};

const char* database_kind_name(DatabaseKind kind);

} // namespace xdebug_core
