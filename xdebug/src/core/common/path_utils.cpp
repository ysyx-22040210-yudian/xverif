#include "common/path_utils.h"

#include <cstdlib>
#include <sstream>

namespace xdebug_core {

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
    unsigned long long h = 1469598103934665603ULL;
    for (unsigned char c : session_id) {
        h ^= static_cast<unsigned long long>(c);
        h *= 1099511628211ULL;
    }
    std::ostringstream oss;
    oss << "s_" << std::hex << h;
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
    return tool_session_dir(config, session_id) + "/socket";
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
