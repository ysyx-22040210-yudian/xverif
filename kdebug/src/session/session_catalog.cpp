#include "session/session_catalog.h"

#include <cstdlib>
#include <fstream>

namespace kdebug {

namespace {

std::string canonical_registry_path() {
    const char* home = std::getenv("HOME");
    return std::string(home ? home : "/tmp") + "/.kdebug/engine/registry.json";
}

} // namespace

SessionCatalog::SessionCatalog() : path_(canonical_registry_path()) {}

Json SessionCatalog::read_all() const {
    std::ifstream in(path_.c_str());
    if (!in) return Json::array();
    try {
        Json root;
        in >> root;
        if (!root.is_object() || !root.contains("sessions") ||
            !root["sessions"].is_array()) {
            return Json::array();
        }
        return root["sessions"];
    } catch (...) {
        return Json::array();
    }
}

bool SessionCatalog::parse_record(const Json& item, SessionRecord& record) {
    if (!item.is_object()) return false;
    record.id = item.value("session_id", std::string());
    record.daidir = item.value("dbdir_path", item.value("design_file", std::string()));
    record.fsdb = item.value("fsdb_file", std::string());
    record.socket_path = item.value("socket_path", std::string());
    record.transport = item.value("transport", std::string("uds"));
    record.file_dir = item.value("file_dir", std::string());
    record.host = item.value("host", std::string());
    record.bind_host = item.value("bind_host", std::string());
    record.port = item.value("port", 0);
    record.server_host = item.value("server_host", std::string());
    if (record.id.empty() || (record.daidir.empty() && record.fsdb.empty())) return false;
    record.mode = !record.daidir.empty() && !record.fsdb.empty()
        ? "combined"
        : (!record.daidir.empty() ? "design" : "waveform");
    return true;
}

bool SessionCatalog::get(const std::string& id, SessionRecord& record) const {
    for (const auto& item : read_all()) {
        SessionRecord candidate;
        if (!parse_record(item, candidate) || candidate.id != id) continue;
        record = candidate;
        return true;
    }
    return false;
}

std::vector<SessionRecord> SessionCatalog::list() const {
    std::vector<SessionRecord> records;
    for (const auto& item : read_all()) {
        SessionRecord record;
        if (parse_record(item, record)) records.push_back(record);
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
    if (!record.socket_path.empty()) item["socket_path"] = record.socket_path;
    item["transport"] = record.transport.empty() ? "uds" : record.transport;
    if (!record.file_dir.empty()) item["file_dir"] = record.file_dir;
    if (!record.host.empty()) item["host"] = record.host;
    if (!record.bind_host.empty()) item["bind_host"] = record.bind_host;
    if (record.port > 0) item["port"] = record.port;
    if (!record.server_host.empty()) item["server_host"] = record.server_host;
    return item;
}

} // namespace kdebug
