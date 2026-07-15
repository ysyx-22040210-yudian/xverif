#pragma once

#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "common/kdebug_design_paths.h"

#define INTERNAL_API_VERSION "kdebug.internal.v1"

// Socket path configuration
#define SOCK_PATH_PREFIX    ".kdebug_design"
#define SOCK_PATH_LEN       256
#define REGISTRY_FILE       "registry.json"

// Get socket path for a given session ID
inline void get_sock_path(char* buf, const std::string& session_id) {
    snprintf(buf, SOCK_PATH_LEN, "%s", kdebug_design::kdebug_design_socket_path(session_id).c_str());
}

// Get registry file path
inline void get_registry_path(char* buf) {
    snprintf(buf, SOCK_PATH_LEN, "%s", kdebug_design::kdebug_design_registry_path().c_str());
}

inline void get_registry_lock_path(char* buf) {
    snprintf(buf, SOCK_PATH_LEN, "%s", kdebug_design::kdebug_design_registry_lock_path().c_str());
}

inline void get_debug_log_path(char* buf, const std::string& session_id) {
    snprintf(buf, SOCK_PATH_LEN, "%s", kdebug_design::kdebug_design_debug_log_path(session_id).c_str());
}
