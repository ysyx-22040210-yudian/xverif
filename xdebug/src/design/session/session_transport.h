#pragma once

#include "session_registry.h"

#include <string>

namespace xdebug_design {

std::string current_host_name();
std::string generate_auth_token();
bool is_tcp_transport(const SessionInfo& session);
bool is_local_session_host(const SessionInfo& session);

bool write_endpoint_file(const SessionInfo& session);
bool read_endpoint_file(const std::string& session_id, SessionInfo& endpoint);

int connect_session_endpoint(const SessionInfo& session);
bool ping_session_endpoint(const SessionInfo& session);
bool protocol_version_matches_endpoint(const SessionInfo& session);
bool send_quit_to_endpoint(const SessionInfo& session);

} // namespace xdebug_design
