#pragma once

#include <string>

namespace kdebug_waveform {

std::string kdebug_waveform_home_dir();
std::string kdebug_waveform_sessions_dir();
std::string kdebug_waveform_session_dir(int session_id);
std::string kdebug_waveform_session_dir(const std::string& session_id);
std::string kdebug_waveform_registry_path();
std::string kdebug_waveform_registry_lock_path();
std::string kdebug_waveform_session_json_path(int session_id);
std::string kdebug_waveform_session_json_path(const std::string& session_id);
std::string kdebug_waveform_socket_path(int session_id);
std::string kdebug_waveform_socket_path(const std::string& session_id);
std::string kdebug_waveform_endpoint_path(const std::string& session_id);
std::string kdebug_waveform_debug_log_path(int session_id);
std::string kdebug_waveform_debug_log_path(const std::string& session_id);
std::string kdebug_waveform_lists_path(int session_id);
std::string kdebug_waveform_lists_path(const std::string& session_id);
std::string kdebug_waveform_apb_path(int session_id);
std::string kdebug_waveform_apb_path(const std::string& session_id);
std::string kdebug_waveform_axi_path(int session_id);
std::string kdebug_waveform_axi_path(const std::string& session_id);
std::string kdebug_waveform_axi_exports_dir(const std::string& session_id);
std::string kdebug_waveform_events_path(int session_id);
std::string kdebug_waveform_events_path(const std::string& session_id);
std::string kdebug_waveform_streams_path(int session_id);
std::string kdebug_waveform_streams_path(const std::string& session_id);
std::string kdebug_waveform_stream_exports_dir(const std::string& session_id);
std::string kdebug_waveform_cursors_path(int session_id);
std::string kdebug_waveform_cursors_path(const std::string& session_id);

std::string kdebug_waveform_legacy_registry_path();
std::string kdebug_waveform_legacy_lists_path();
std::string kdebug_waveform_legacy_apb_path();
std::string kdebug_waveform_legacy_axi_path();
std::string kdebug_waveform_legacy_events_path();

bool kdebug_waveform_ensure_home();
bool kdebug_waveform_ensure_session_dir(int session_id);
bool kdebug_waveform_ensure_session_dir(const std::string& session_id);
bool kdebug_waveform_remove_session_dir(int session_id);
bool kdebug_waveform_remove_session_dir(const std::string& session_id);
bool kdebug_waveform_legacy_registry_has_session(int session_id);

} // namespace kdebug_waveform
