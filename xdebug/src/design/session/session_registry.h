#pragma once

#include "core/session/session_types.h"

#include <string>
#include <vector>
#include <ctime>
#include <sys/types.h>

namespace xdebug_design {

// Unified SessionInfo from core — design fields are dbdir_*.
using SessionInfo = xdebug_core::SessionInfo;

// Session registry - manages persistent storage of session info
class SessionRegistry {
public:
    SessionRegistry();
    ~SessionRegistry();

    // Load all sessions from registry file
    bool load_all(std::vector<SessionInfo>& sessions);

    // Add a new session to registry
    bool add(const SessionInfo& session);

    // Replace or add a session record
    bool upsert(const SessionInfo& session);

    // Update last active timestamp
    bool touch(const std::string& session_id, time_t last_active);

    // Remove a session from registry
    bool remove(const std::string& session_id);

    // Get session by ID
    bool get(const std::string& session_id, SessionInfo& session);

    // Get the latest session (highest ID)
    bool get_latest(SessionInfo& session);

    bool exists(const std::string& session_id);
    static bool is_valid_session_name(const std::string& name);

    // Clean up stale sessions (dead processes)
    bool cleanup_stale();

    // Clear all sessions
    bool clear_all();

private:
    std::string registry_path_;

    // File locking for concurrent access
    bool lock_file(int fd);
    bool unlock_file(int fd);

    bool parse_legacy_line(const char* line, SessionInfo& session);
    bool load_legacy(std::vector<SessionInfo>& sessions);
    bool save_all(const std::vector<SessionInfo>& sessions);
    bool write_session_file(const SessionInfo& session);
};

} // namespace xdebug_design
