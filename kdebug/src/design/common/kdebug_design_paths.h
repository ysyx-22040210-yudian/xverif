#pragma once

#include <string>

namespace kdebug_design {

std::string kdebug_design_home_dir();
std::string kdebug_design_sessions_dir();
std::string kdebug_design_session_dir(const std::string& session_id);
std::string kdebug_design_registry_path();
std::string kdebug_design_registry_lock_path();
std::string kdebug_design_session_json_path(const std::string& session_id);
std::string kdebug_design_socket_path(const std::string& session_id);
std::string kdebug_design_endpoint_path(const std::string& session_id);
std::string kdebug_design_debug_log_path(const std::string& session_id);
std::string kdebug_design_legacy_registry_path();

bool kdebug_design_ensure_home();
bool kdebug_design_ensure_session_dir(const std::string& session_id);
bool kdebug_design_remove_session_dir(const std::string& session_id);

} // namespace kdebug_design
