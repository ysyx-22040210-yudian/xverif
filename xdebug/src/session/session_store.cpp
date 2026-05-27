#include "session/session_store.h"

#include <cstdlib>
#include <fstream>
#include <sys/stat.h>

namespace xdebug {

namespace {

bool ensure_dir(const std::string& path) {
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

std::string home_dir() {
    const char* home = std::getenv("HOME");
    return std::string(home ? home : "/tmp") + "/.xdebug";
}

} // namespace

SessionStore::SessionStore()
    : home_(home_dir()), path_(home_ + "/registry.json") {}

bool SessionStore::ensure_home() const {
    return ensure_dir(home_);
}

Json SessionStore::read_all() const {
    std::ifstream in(path_.c_str());
    if (!in) return Json::array();
    try {
        Json sessions;
        in >> sessions;
        return sessions.is_array() ? sessions : Json::array();
    } catch (...) {
        return Json::array();
    }
}

bool SessionStore::write_all(const Json& sessions) const {
    if (!ensure_home()) return false;
    std::ofstream out(path_.c_str(), std::ios::trunc);
    if (!out) return false;
    out << sessions.dump(2) << "\n";
    return static_cast<bool>(out);
}

bool SessionStore::get(const std::string& id, SessionRecord& record) const {
    for (const auto& item : read_all()) {
        if (!item.is_object() || item.value("id", std::string()) != id) continue;
        record.id = id;
        record.mode = item.value("mode", std::string());
        record.daidir = item.value("daidir", std::string());
        record.fsdb = item.value("fsdb", std::string());
        return true;
    }
    return false;
}

bool SessionStore::put(const SessionRecord& record) {
    Json sessions = read_all();
    bool replaced = false;
    for (auto& item : sessions) {
        if (item.value("id", std::string()) == record.id) {
            item = session_record_json(record);
            replaced = true;
            break;
        }
    }
    if (!replaced) sessions.push_back(session_record_json(record));
    return write_all(sessions);
}

bool SessionStore::remove(const std::string& id) {
    Json out = Json::array();
    for (const auto& item : read_all()) {
        if (item.value("id", std::string()) != id) out.push_back(item);
    }
    return write_all(out);
}

std::vector<SessionRecord> SessionStore::list() const {
    std::vector<SessionRecord> records;
    for (const auto& item : read_all()) {
        SessionRecord record;
        record.id = item.value("id", std::string());
        record.mode = item.value("mode", std::string());
        record.daidir = item.value("daidir", std::string());
        record.fsdb = item.value("fsdb", std::string());
        if (!record.id.empty()) records.push_back(record);
    }
    return records;
}

Json session_record_json(const SessionRecord& record) {
    Json item = {
        {"id", record.id},
        {"session_id", record.id},
        {"mode", record.mode}
    };
    if (!record.daidir.empty()) item["daidir"] = record.daidir;
    if (!record.fsdb.empty()) item["fsdb"] = record.fsdb;
    return item;
}

} // namespace xdebug
