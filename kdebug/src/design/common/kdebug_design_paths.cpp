#include "kdebug_design_paths.h"

#include <cstdio>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include "common/path_utils.h"

namespace kdebug_design {

namespace {

const kdebug_core::ToolConfig& tool_config() {
    static const kdebug_core::ToolConfig config =
        kdebug_core::make_tool_config("kdebug-engine", ".kdebug/engine", "kdebug-engine", "1.2");
    return config;
}

std::string kdebug_home_dir() {
    return kdebug_core::home_dir() + "/.kdebug";
}

bool ensure_dir(const std::string& path) {
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

bool remove_file_if_exists(const std::string& path) {
    if (unlink(path.c_str()) == 0) return true;
    return access(path.c_str(), F_OK) != 0;
}

} // namespace

std::string kdebug_design_home_dir() {
    return kdebug_core::tool_home_dir(tool_config());
}

std::string kdebug_design_sessions_dir() {
    return kdebug_core::tool_sessions_dir(tool_config());
}

std::string session_dir_name(const std::string& session_id) {
    return kdebug_core::session_dir_name(session_id);
}

std::string kdebug_design_session_dir(const std::string& session_id) {
    return kdebug_core::tool_session_dir(tool_config(), session_id);
}

std::string kdebug_design_registry_path() {
    return kdebug_core::registry_path(tool_config());
}

std::string kdebug_design_registry_lock_path() {
    return kdebug_core::registry_lock_path(tool_config());
}

std::string kdebug_design_session_json_path(const std::string& session_id) {
    return kdebug_core::session_json_path(tool_config(), session_id);
}

std::string kdebug_design_socket_path(const std::string& session_id) {
    return kdebug_core::socket_path(tool_config(), session_id);
}

std::string kdebug_design_endpoint_path(const std::string& session_id) {
    return kdebug_core::endpoint_path(tool_config(), session_id);
}

std::string kdebug_design_debug_log_path(const std::string& session_id) {
    return kdebug_core::debug_log_path(tool_config(), session_id);
}

std::string kdebug_design_legacy_registry_path() {
    return kdebug_home_dir() + "/design/legacy.registry";
}

bool kdebug_design_ensure_home() {
    bool ok = ensure_dir(kdebug_home_dir()) &&
              ensure_dir(kdebug_design_home_dir()) &&
              ensure_dir(kdebug_design_sessions_dir());
    if (ok) {
        int fd = open(kdebug_design_registry_lock_path().c_str(), O_RDWR | O_CREAT, 0600);
        if (fd >= 0) close(fd);
    }
    return ok;
}

bool kdebug_design_ensure_session_dir(const std::string& session_id) {
    return kdebug_design_ensure_home() && ensure_dir(kdebug_design_session_dir(session_id));
}

bool kdebug_design_remove_session_dir(const std::string& session_id) {
    std::string dir = kdebug_design_session_dir(session_id);
    remove_file_if_exists(dir + "/session.json");
    remove_file_if_exists(dir + "/socket");
    remove_file_if_exists(kdebug_design_socket_path(session_id));
    remove_file_if_exists(dir + "/endpoint.json");
    // Preserve debug.log and logs/ for post-failure diagnostics.
    return true;
}

} // namespace kdebug_design
