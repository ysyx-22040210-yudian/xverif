#pragma once

#include <string>

namespace xdebug_design {

std::string xdebug_design_home_dir();
std::string xdebug_design_sessions_dir();
std::string xdebug_design_session_dir(const std::string& session_id);
std::string xdebug_design_registry_path();
std::string xdebug_design_registry_lock_path();
std::string xdebug_design_session_json_path(const std::string& session_id);
std::string xdebug_design_socket_path(const std::string& session_id);
std::string xdebug_design_endpoint_path(const std::string& session_id);
std::string xdebug_design_debug_log_path(const std::string& session_id);
std::string xdebug_design_legacy_registry_path();

bool xdebug_design_ensure_home();
bool xdebug_design_ensure_session_dir(const std::string& session_id);
bool xdebug_design_remove_session_dir(const std::string& session_id);

} // namespace xdebug_design
