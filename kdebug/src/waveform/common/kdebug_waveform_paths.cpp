#include "kdebug_waveform_paths.h"

#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>

#include "common/path_utils.h"

namespace kdebug_waveform {

namespace {

const kdebug_core::ToolConfig& tool_config() {
    static const kdebug_core::ToolConfig config =
        kdebug_core::make_tool_config("kdebug-waveform", ".kdebug/waveform", "kdebug-engine", "1.0");
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

std::string kdebug_waveform_home_dir() {
    return kdebug_core::tool_home_dir(tool_config());
}

std::string kdebug_waveform_sessions_dir() {
    return kdebug_core::tool_sessions_dir(tool_config());
}

std::string kdebug_waveform_session_dir(int session_id) {
    return kdebug_waveform_session_dir(std::to_string(session_id));
}

std::string kdebug_waveform_session_dir(const std::string& session_id) {
    return kdebug_core::tool_session_dir(tool_config(), session_id);
}

std::string kdebug_waveform_registry_path() {
    return kdebug_core::registry_path(tool_config());
}

std::string kdebug_waveform_registry_lock_path() {
    return kdebug_core::registry_lock_path(tool_config());
}

std::string kdebug_waveform_session_json_path(int session_id) {
    return kdebug_waveform_session_json_path(std::to_string(session_id));
}

std::string kdebug_waveform_session_json_path(const std::string& session_id) {
    return kdebug_core::session_json_path(tool_config(), session_id);
}

std::string kdebug_waveform_socket_path(int session_id) {
    return kdebug_waveform_socket_path(std::to_string(session_id));
}

std::string kdebug_waveform_socket_path(const std::string& session_id) {
    return kdebug_core::socket_path(tool_config(), session_id);
}

std::string kdebug_waveform_endpoint_path(const std::string& session_id) {
    return kdebug_core::endpoint_path(tool_config(), session_id);
}

std::string kdebug_waveform_debug_log_path(int session_id) {
    return kdebug_waveform_debug_log_path(std::to_string(session_id));
}

std::string kdebug_waveform_debug_log_path(const std::string& session_id) {
    return kdebug_core::debug_log_path(tool_config(), session_id);
}

std::string kdebug_waveform_lists_path(int session_id) {
    return kdebug_waveform_lists_path(std::to_string(session_id));
}

std::string kdebug_waveform_lists_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/lists.json";
}

std::string kdebug_waveform_apb_path(int session_id) {
    return kdebug_waveform_apb_path(std::to_string(session_id));
}

std::string kdebug_waveform_apb_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/apb.json";
}

std::string kdebug_waveform_axi_path(int session_id) {
    return kdebug_waveform_axi_path(std::to_string(session_id));
}

std::string kdebug_waveform_axi_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/axi.json";
}

std::string kdebug_waveform_axi_exports_dir(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/axi_exports";
}

std::string kdebug_waveform_events_path(int session_id) {
    return kdebug_waveform_events_path(std::to_string(session_id));
}

std::string kdebug_waveform_events_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/events.json";
}

std::string kdebug_waveform_streams_path(int session_id) {
    return kdebug_waveform_streams_path(std::to_string(session_id));
}

std::string kdebug_waveform_streams_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/streams.json";
}

std::string kdebug_waveform_stream_exports_dir(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/stream_exports";
}

std::string kdebug_waveform_cursors_path(int session_id) {
    return kdebug_waveform_cursors_path(std::to_string(session_id));
}

std::string kdebug_waveform_cursors_path(const std::string& session_id) {
    return kdebug_waveform_session_dir(session_id) + "/cursors.json";
}

std::string kdebug_waveform_legacy_registry_path() {
    return kdebug_home_dir() + "/waveform/legacy.registry";
}

std::string kdebug_waveform_legacy_lists_path() {
    return kdebug_home_dir() + "/waveform/legacy.lists";
}

std::string kdebug_waveform_legacy_apb_path() {
    return kdebug_home_dir() + "/waveform/legacy.apb";
}

std::string kdebug_waveform_legacy_axi_path() {
    return kdebug_home_dir() + "/waveform/legacy.axi";
}

std::string kdebug_waveform_legacy_events_path() {
    return kdebug_home_dir() + "/waveform/legacy.events";
}

bool kdebug_waveform_ensure_home() {
    return ensure_dir(kdebug_home_dir()) &&
           ensure_dir(kdebug_waveform_home_dir()) &&
           ensure_dir(kdebug_waveform_sessions_dir());
}

bool kdebug_waveform_ensure_session_dir(int session_id) {
    return kdebug_waveform_ensure_session_dir(std::to_string(session_id));
}

bool kdebug_waveform_ensure_session_dir(const std::string& session_id) {
    return kdebug_waveform_ensure_home() && ensure_dir(kdebug_waveform_session_dir(session_id));
}

bool kdebug_waveform_remove_session_dir(int session_id) {
    return kdebug_waveform_remove_session_dir(std::to_string(session_id));
}

bool kdebug_waveform_remove_session_dir(const std::string& session_id) {
    std::string dir = kdebug_waveform_session_dir(session_id);
    remove_file_if_exists(dir + "/session.json");
    remove_file_if_exists(dir + "/socket");
    remove_file_if_exists(kdebug_waveform_socket_path(session_id));
    remove_file_if_exists(dir + "/lists.json");
    remove_file_if_exists(dir + "/apb.json");
    remove_file_if_exists(dir + "/axi.json");
    remove_file_if_exists(dir + "/events.json");
    remove_file_if_exists(dir + "/streams.json");
    remove_file_if_exists(dir + "/cursors.json");
    remove_file_if_exists(dir + "/endpoint.json");
    // Preserve debug.log and logs/ for post-failure diagnostics.
    return true;
}

bool kdebug_waveform_legacy_registry_has_session(int session_id) {
    FILE* fp = fopen(kdebug_waveform_legacy_registry_path().c_str(), "r");
    if (!fp) return false;

    char line[4096];
    bool found = false;
    while (fgets(line, sizeof(line), fp)) {
        char* end = nullptr;
        long sid = strtol(line, &end, 10);
        if (end != line && sid == session_id && *end == '|') {
            found = true;
            break;
        }
    }

    fclose(fp);
    return found;
}

} // namespace kdebug_waveform
