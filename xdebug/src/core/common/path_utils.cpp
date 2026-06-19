#include "common/path_utils.h"

#include <cstdlib>
#include <sstream>
#include <unistd.h>

namespace xdebug_core {

namespace {

unsigned long long stable_path_hash(const std::string& value) {
    unsigned long long hash = 1469598103934665603ULL;
    for (unsigned char c : value) {
        hash ^= static_cast<unsigned long long>(c);
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string short_socket_path(const std::string& nominal_path) {
    std::ostringstream oss;
    oss << "/tmp/xdebug-" << static_cast<unsigned long long>(getuid())
        << "-" << std::hex << stable_path_hash(nominal_path) << ".sock";
    return oss.str();
}

}  // namespace

std::string home_dir() {
    const char* home = std::getenv("HOME");
    return home ? std::string(home) : std::string("/tmp");
}

std::string tool_home_dir(const ToolConfig& config) {
    return home_dir() + "/" + config.home_dir_name;
}

std::string tool_sessions_dir(const ToolConfig& config) {
    return tool_home_dir(config) + "/sessions";
}

std::string session_dir_name(const std::string& session_id) {
    std::ostringstream oss;
    oss << "s_" << std::hex << stable_path_hash(session_id);
    return oss.str();
}

std::string tool_session_dir(const ToolConfig& config, const std::string& session_id) {
    return tool_sessions_dir(config) + "/" + session_dir_name(session_id);
}

std::string registry_path(const ToolConfig& config) {
    return tool_home_dir(config) + "/registry.json";
}

std::string registry_lock_path(const ToolConfig& config) {
    return tool_home_dir(config) + "/registry.lock";
}

std::string socket_path(const ToolConfig& config, const std::string& session_id) {
    const std::string nominal = tool_session_dir(config, session_id) + "/socket";
    // Linux sockaddr_un::sun_path has 108 bytes including the terminating NUL.
    // Keep a little margin and use a deterministic /tmp fallback for long HOME
    // paths commonly produced by pytest and CI workspaces.
    return nominal.size() < 104 ? nominal : short_socket_path(nominal);
}

std::string endpoint_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/endpoint.json";
}

std::string debug_log_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/debug.log";
}

std::string session_json_path(const ToolConfig& config, const std::string& session_id) {
    return tool_session_dir(config, session_id) + "/session.json";
}

} // namespace xdebug_core
