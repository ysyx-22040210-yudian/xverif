#pragma once

#include <cstdlib>

namespace xdebug_core {

// Centralized timeout configuration for session transport.
// Both design and waveform engines share the same env vars and defaults.

inline int file_transport_request_timeout_ms() {
    const char* env = getenv("XDEBUG_FILE_TRANSPORT_TIMEOUT_MS");
    if (!env || !*env) return 300000;  // 5 minutes default
    int value = atoi(env);
    return value > 0 ? value : 300000;
}

inline int file_transport_ping_timeout_ms() {
    const char* env = getenv("XDEBUG_FILE_TRANSPORT_PING_TIMEOUT_MS");
    if (!env || !*env) return 2000;  // 2 seconds default
    int value = atoi(env);
    return value > 0 ? value : 2000;
}

} // namespace xdebug_core
