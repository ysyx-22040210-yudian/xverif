#include "session_registry.h"
#include "../common/kdebug_design_paths.h"
#include "common/path_utils.h"
#include "json.hpp"

#include <fcntl.h>
#include <unistd.h>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <signal.h>
#include <sys/file.h>
#include <sstream>

namespace kdebug_design {

using json = nlohmann::json;

SessionRegistry::SessionRegistry() {
    kdebug_design_ensure_home();
    registry_path_ = kdebug_design_registry_path();
}

SessionRegistry::~SessionRegistry() {
}

bool SessionRegistry::lock_file(int fd) {
    return flock(fd, LOCK_EX) == 0;
}

bool SessionRegistry::unlock_file(int fd) {
    return flock(fd, LOCK_UN) == 0;
}

static json session_to_json(const SessionInfo& session) {
    return json{
        {"session_id", session.session_id},
        {"transport", session.transport.empty() ? "uds" : session.transport},
        {"socket_path", session.socket_path},
        {"file_dir", session.file_dir},
        {"host", session.host},
        {"bind_host", session.bind_host},
        {"port", session.port},
        {"server_host", session.server_host},
        {"auth_token", session.auth_token},
        {"design_file", session.design_file},
        {"dbdir_path", session.dbdir_path},
        {"fsdb_file", session.fsdb_file},
        {"server_pid", session.server_pid},
        {"created_at", static_cast<long long>(session.created_at)},
        {"last_active", static_cast<long long>(session.last_active)},
        {"dbdir_mtime", session.dbdir_mtime},
        {"dbdir_size", session.dbdir_size},
        {"dbdir_dev", session.dbdir_dev},
        {"dbdir_inode", session.dbdir_inode},
        {"fsdb_mtime", session.fsdb_mtime},
        {"fsdb_size", session.fsdb_size},
        {"fsdb_dev", session.fsdb_dev},
        {"fsdb_inode", session.fsdb_inode}
    };
}

static bool json_to_session(const json& j, SessionInfo& session) {
    if (!j.is_object()) return false;
    if (j.contains("session_id")) {
        if (j["session_id"].is_string()) session.session_id = j["session_id"].get<std::string>();
        else if (j["session_id"].is_number_integer()) session.session_id = std::to_string(j["session_id"].get<int>());
    } else {
        session.session_id.clear();
    }
    session.transport = j.value("transport", std::string("uds"));
    session.socket_path = j.value("socket_path", "");
    session.file_dir = j.value("file_dir", std::string());
    session.host = j.value("host", std::string());
    session.bind_host = j.value("bind_host", std::string());
    session.port = j.value("port", 0);
    session.server_host = j.value("server_host", std::string());
    session.auth_token = j.value("auth_token", std::string());
    session.design_file = j.value("design_file", "");
    session.dbdir_path = j.value("dbdir_path", "");
    session.fsdb_file = j.value("fsdb_file", "");
    session.server_pid = static_cast<pid_t>(j.value("server_pid", 0));
    session.created_at = static_cast<time_t>(j.value("created_at", 0LL));
    session.last_active = static_cast<time_t>(j.value("last_active", 0LL));
    session.dbdir_mtime = j.value("dbdir_mtime", 0L);
    session.dbdir_size = j.value("dbdir_size", 0LL);
    session.dbdir_dev = j.value("dbdir_dev", 0ULL);
    session.dbdir_inode = j.value("dbdir_inode", 0ULL);
    session.fsdb_mtime = j.value("fsdb_mtime", 0L);
    session.fsdb_size = j.value("fsdb_size", 0LL);
    session.fsdb_dev = j.value("fsdb_dev", 0ULL);
    session.fsdb_inode = j.value("fsdb_inode", 0ULL);
    if (session.socket_path.empty() && !session.session_id.empty()) {
        session.socket_path = kdebug_design_socket_path(session.session_id);
    }
    if (session.dbdir_path.empty()) session.dbdir_path = session.design_file;
    if (session.design_file.empty()) session.design_file = session.dbdir_path;
    return !session.session_id.empty() &&
           (!session.dbdir_path.empty() || !session.fsdb_file.empty());
}

bool SessionRegistry::parse_legacy_line(const char* line, SessionInfo& session) {
    std::vector<std::string> fields;
    std::stringstream ss(line ? line : "");
    std::string field;
    while (std::getline(ss, field, '|')) {
        if (!field.empty() && field.back() == '\n') field.pop_back();
        if (!field.empty() && field.back() == '\r') field.pop_back();
        fields.push_back(field);
    }

    if (fields.size() != 5 && fields.size() != 6 && fields.size() != 11) return false;

    session.session_id = fields[0];
    session.transport = "uds";
    char* end = nullptr;
    session.socket_path = kdebug_design_socket_path(session.session_id);
    session.design_file = fields[2];
    session.server_pid = strtol(fields[3].c_str(), &end, 10);
    if (!end || *end != '\0') return false;
    session.created_at = strtol(fields[4].c_str(), &end, 10);
    if (!end || *end != '\0') return false;
    session.last_active = session.created_at;

    if (fields.size() >= 6) {
        session.last_active = strtol(fields[5].c_str(), &end, 10);
        if (!end || *end != '\0') return false;
    }

    if (fields.size() == 11) {
        session.dbdir_path = fields[6];
        session.dbdir_mtime = strtol(fields[7].c_str(), &end, 10);
        if (!end || *end != '\0') return false;
        session.dbdir_size = strtoll(fields[8].c_str(), &end, 10);
        if (!end || *end != '\0') return false;
        session.dbdir_dev = strtoull(fields[9].c_str(), &end, 10);
        if (!end || *end != '\0') return false;
        session.dbdir_inode = strtoull(fields[10].c_str(), &end, 10);
        if (!end || *end != '\0') return false;
    } else {
        session.dbdir_path = session.design_file;
    }

    if (session.design_file.empty()) session.design_file = session.dbdir_path;
    return !session.session_id.empty();
}

bool SessionRegistry::load_legacy(std::vector<SessionInfo>& sessions) {
    sessions.clear();
    int fd = open(kdebug_design_legacy_registry_path().c_str(), O_RDONLY);
    if (fd < 0) return false;
    FILE* fp = fdopen(fd, "r");
    if (!fp) {
        close(fd);
        return false;
    }

    char line[2048];
    while (fgets(line, sizeof(line), fp)) {
        SessionInfo session;
        if (parse_legacy_line(line, session)) sessions.push_back(session);
    }
    fclose(fp);
    return true;
}

bool SessionRegistry::load_all(std::vector<SessionInfo>& sessions) {
    sessions.clear();
    kdebug_design_ensure_home();

    int fd = open(registry_path_.c_str(), O_RDONLY);
    if (fd < 0) {
        if (load_legacy(sessions)) save_all(sessions);
        return true;
    }

    if (!lock_file(fd)) {
        close(fd);
        return false;
    }

    FILE* fp = fdopen(fd, "r");
    if (!fp) {
        unlock_file(fd);
        close(fd);
        return false;
    }

    std::string text;
    char buf[4096];
    while (fgets(buf, sizeof(buf), fp)) text += buf;
    fclose(fp);

    if (text.empty()) return true;
    try {
        json root = json::parse(text);
        if (!root.is_object() || !root.value("sessions", json::array()).is_array()) return true;
        for (const auto& item : root["sessions"]) {
            SessionInfo session;
            if (json_to_session(item, session)) sessions.push_back(session);
        }
    } catch (...) {
        return false;
    }
    return true;
}

bool SessionRegistry::write_session_file(const SessionInfo& session) {
    if (!kdebug_design_ensure_session_dir(session.session_id)) return false;
    int fd = open(kdebug_design_session_json_path(session.session_id).c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return false;
    json root = {{"version", 1}, {"session", session_to_json(session)}};
    std::string data = root.dump(2) + "\n";
    bool ok = write(fd, data.c_str(), data.size()) == static_cast<ssize_t>(data.size());
    close(fd);
    return ok;
}

bool SessionRegistry::save_all(const std::vector<SessionInfo>& sessions) {
    kdebug_design_ensure_home();
    int fd = open(registry_path_.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return false;
    if (!lock_file(fd)) {
        close(fd);
        return false;
    }

    json root;
    root["version"] = 1;
    root["sessions"] = json::array();
    for (const auto& session : sessions) root["sessions"].push_back(session_to_json(session));
    std::string data = root.dump(2) + "\n";
    bool ok = write(fd, data.c_str(), data.size()) == static_cast<ssize_t>(data.size());
    unlock_file(fd);
    close(fd);
    if (!ok) return false;
    for (const auto& session : sessions) write_session_file(session);
    return true;
}

bool SessionRegistry::add(const SessionInfo& session) {
    std::vector<SessionInfo> sessions;
    load_all(sessions);
    for (const auto& s : sessions) {
        if (s.session_id == session.session_id) return false;
    }
    sessions.push_back(session);
    return save_all(sessions);
}

bool SessionRegistry::upsert(const SessionInfo& session) {
    std::vector<SessionInfo> sessions;
    load_all(sessions);
    bool replaced = false;
    for (auto& s : sessions) {
        if (s.session_id == session.session_id) {
            s = session;
            replaced = true;
            break;
        }
    }
    if (!replaced) sessions.push_back(session);
    return save_all(sessions);
}

bool SessionRegistry::touch(const std::string& session_id, time_t last_active) {
    SessionInfo session;
    if (!get(session_id, session)) return false;
    session.last_active = last_active;
    return upsert(session);
}

bool SessionRegistry::remove(const std::string& session_id) {
    std::vector<SessionInfo> sessions;
    if (!load_all(sessions)) return false;
    std::vector<SessionInfo> kept;
    bool found = false;
    for (const auto& session : sessions) {
        if (session.session_id == session_id) {
            found = true;
            continue;
        }
        kept.push_back(session);
    }
    if (!found) return false;
    bool ok = save_all(kept);
    kdebug_design_remove_session_dir(session_id);
    return ok;
}

bool SessionRegistry::get(const std::string& session_id, SessionInfo& session) {
    std::vector<SessionInfo> sessions;
    if (!load_all(sessions)) return false;
    for (const auto& s : sessions) {
        if (s.session_id == session_id) {
            session = s;
            return true;
        }
    }
    return false;
}

bool SessionRegistry::get_latest(SessionInfo& session) {
    std::vector<SessionInfo> sessions;
    if (!load_all(sessions) || sessions.empty()) return false;
    size_t latest_idx = 0;
    for (size_t i = 1; i < sessions.size(); ++i) {
        if (sessions[i].created_at > sessions[latest_idx].created_at) latest_idx = i;
    }
    session = sessions[latest_idx];
    return true;
}

bool SessionRegistry::exists(const std::string& session_id) {
    SessionInfo session;
    return get(session_id, session);
}

bool SessionRegistry::is_valid_session_name(const std::string& name) {
    return kdebug_core::is_valid_session_name(name);
}

bool SessionRegistry::cleanup_stale() {
    std::vector<SessionInfo> sessions;
    if (!load_all(sessions)) return false;
    std::vector<SessionInfo> valid_sessions;
    for (const auto& session : sessions) {
        bool is_alive = (kill(session.server_pid, 0) == 0);
        bool endpoint_exists = (session.transport == "tcp" || session.transport == "file")
            ? (access(kdebug_design_endpoint_path(session.session_id).c_str(), F_OK) == 0)
            : (access(session.socket_path.c_str(), F_OK) == 0);
        if (is_alive && endpoint_exists) {
            valid_sessions.push_back(session);
        } else {
            kdebug_design_remove_session_dir(session.session_id);
        }
    }
    return save_all(valid_sessions);
}

bool SessionRegistry::clear_all() {
    std::vector<SessionInfo> sessions;
    if (load_all(sessions)) {
        for (const auto& session : sessions) kdebug_design_remove_session_dir(session.session_id);
    }
    std::vector<SessionInfo> empty;
    return save_all(empty);
}

} // namespace kdebug_design
