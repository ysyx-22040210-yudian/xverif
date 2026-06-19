#include "../commands/cmd_ai.h"
#include "action_support.h"

#include "../apb/apb_config.h"
#include "../apb/apb_manager.h"
#include "../axi/axi_config.h"
#include "../axi/axi_manager.h"
#include "../client/client.h"
#include "../event/event_config.h"
#include "../event/event_manager.h"
#include "../list/list_manager.h"
#include "../protocol/protocol.h"
#include "../session/session_manager.h"
#include "../session/session_registry.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <fcntl.h>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>
#include <unistd.h>

namespace xdebug_waveform {

const char* kApiVersion = "xdebug.internal.v1";

std::string read_stream(std::istream& is) {
    std::ostringstream oss;
    oss << is.rdbuf();
    return oss.str();
}

bool read_file(const std::string& path, std::string& out) {
    std::ifstream ifs(path);
    if (!ifs) return false;
    out = read_stream(ifs);
    return true;
}

std::string trim(std::string s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) s.erase(s.begin());
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) s.pop_back();
    return s;
}

std::string create_session_quiet(SessionManager& manager, const std::string& fsdb, const std::string& name,
                                        const SessionTransportOptions& transport);

bool resolve_session(const Json& target,
                            std::string& session_id,
                            SessionInfo& info,
                            std::string& error) {
    SessionManager manager;
    session_id.clear();
    auto sid_it = target.find("session_id");
    if (sid_it != target.end()) {
        if (!sid_it->is_string()) {
            error = "target.session_id must be a string";
            return false;
        }
        session_id = sid_it->get<std::string>();
        if (!manager.get_session(session_id, info)) {
            error = "session not found: " + session_id;
            return false;
        }
        if (!manager.ensure_session_current(session_id) || !manager.get_session(session_id, info)) {
            error = "session unavailable: " + session_id;
            return false;
        }
        return true;
    }

    error = "target.session_id is required; open a session explicitly first";
    return false;
}

std::string create_session_quiet(SessionManager& manager, const std::string& fsdb, const std::string& name,
                                        const SessionTransportOptions& transport) {
    fflush(stdout);
    int saved_stdout = dup(STDOUT_FILENO);
    int saved_stderr = dup(STDERR_FILENO);
    int devnull = open("/dev/null", O_WRONLY);
    if (saved_stdout >= 0) fcntl(saved_stdout, F_SETFD, FD_CLOEXEC);
    if (saved_stderr >= 0) fcntl(saved_stderr, F_SETFD, FD_CLOEXEC);
    if (devnull >= 0) fcntl(devnull, F_SETFD, FD_CLOEXEC);
    if (saved_stdout >= 0 && devnull >= 0) {
        dup2(devnull, STDOUT_FILENO);
    }
    if (saved_stderr >= 0 && devnull >= 0) {
        dup2(devnull, STDERR_FILENO);
    }
    std::string sid = manager.create_session(fsdb, name, transport);
    fflush(stdout);
    fflush(stderr);
    if (saved_stdout >= 0) {
        dup2(saved_stdout, STDOUT_FILENO);
        close(saved_stdout);
    }
    if (saved_stderr >= 0) {
        dup2(saved_stderr, STDERR_FILENO);
        close(saved_stderr);
    }
    if (devnull >= 0) close(devnull);
    return sid;
}

void fill_session(Json& out, const SessionInfo& info) {
    out["session"] = {
        {"id", info.session_id},
        {"fsdb", info.fsdb_file},
        {"pid", info.server_pid},
        {"transport", info.transport},
        {"socket_path", info.socket_path},
        {"file_dir", info.file_dir},
        {"host", info.host},
        {"port", info.port}
    };
}

bool capture_server_json(const std::string& session_id,
                                const std::string& cmd,
                                Json& data,
                                std::string& error) {
    std::string payload;
    if (!send_command_capture(session_id, cmd.c_str(), payload)) {
        error = trim(payload);
        if (error.compare(0, strlen(ERROR_PREFIX), ERROR_PREFIX) == 0) {
            error = trim(error.substr(strlen(ERROR_PREFIX)));
        }
        if (error.empty()) error = "server command failed";
        return false;
    }
    try {
        data = Json::parse(payload);
    } catch (const std::exception&) {
        data = trim(payload);
    }
    return true;
}

bool capture_server_text(const std::string& session_id,
                                const std::string& cmd,
                                std::string& payload,
                                std::string& error) {
    if (!send_command_capture(session_id, cmd.c_str(), payload)) {
        error = trim(payload);
        if (error.compare(0, strlen(ERROR_PREFIX), ERROR_PREFIX) == 0) {
            error = trim(error.substr(strlen(ERROR_PREFIX)));
        }
        if (error.empty()) error = "server command failed";
        return false;
    }
    payload = trim(payload);
    return true;
}

Json session_info_json(const SessionInfo& s) {
    Json j;
    j["id"] = s.session_id;
    j["pid"] = s.server_pid;
    j["transport"] = s.transport;
    j["socket_path"] = s.socket_path;
    j["file_dir"] = s.file_dir;
    j["host"] = s.host;
    j["bind_host"] = s.bind_host;
    j["port"] = s.port;
    j["server_host"] = s.server_host;
    j["fsdb"] = s.fsdb_file;
    j["created_at"] = static_cast<long long>(s.created_at);
    j["last_active"] = static_cast<long long>(s.last_active);
    j["fsdb_mtime"] = s.fsdb_mtime;
    j["fsdb_size"] = s.fsdb_size;
    j["fsdb_dev"] = s.fsdb_dev;
    j["fsdb_inode"] = s.fsdb_inode;
    return j;
}


} // namespace xdebug_waveform
