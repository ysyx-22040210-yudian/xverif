#pragma once

#include <string>

#include "session/session_types.h"

namespace xdebug_core {

enum class SessionHealthStatus {
    Healthy,
    RegistryMissing,
    ProcessExited,
    SocketMissing,
    ConnectFailed,
    PingFailed,
    DatabaseMissing,
    DatabaseChanged
};

struct SessionHealth {
    std::string session_id;
    bool healthy;
    SessionHealthStatus status;
    std::string message;
    SessionInfo info;

    SessionHealth() : healthy(false), status(SessionHealthStatus::RegistryMissing) {}
};

inline const char* session_health_status_name(SessionHealthStatus status) {
    switch (status) {
    case SessionHealthStatus::Healthy:
        return "healthy";
    case SessionHealthStatus::RegistryMissing:
        return "registry_missing";
    case SessionHealthStatus::ProcessExited:
        return "process_exited";
    case SessionHealthStatus::SocketMissing:
        return "socket_missing";
    case SessionHealthStatus::ConnectFailed:
        return "connect_failed";
    case SessionHealthStatus::PingFailed:
        return "ping_failed";
    case SessionHealthStatus::DatabaseMissing:
        return "database_missing";
    case SessionHealthStatus::DatabaseChanged:
        return "database_changed";
    }
    return "unknown";
}

} // namespace xdebug_core
