#include "logging/action_log.h"

#include "common/path_utils.h"

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <sys/stat.h>
#include <unistd.h>

namespace xdebug_core {

namespace {

const size_t kMaxString = 4096;
const size_t kMaxArray = 64;
const size_t kMaxObject = 128;
const int kMaxDepth = 8;

bool ensure_dir(const std::string& path) {
    if (path.empty()) return false;
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

bool ensure_dir_recursive(const std::string& path) {
    if (path.empty()) return false;
    std::string cur;
    size_t i = 0;
    if (path[0] == '/') {
        cur = "/";
        i = 1;
    }
    while (i <= path.size()) {
        size_t slash = path.find('/', i);
        std::string part = path.substr(i, slash == std::string::npos ? std::string::npos : slash - i);
        if (!part.empty()) {
            if (cur.size() > 1) cur += "/";
            cur += part;
            if (!ensure_dir(cur)) return false;
        }
        if (slash == std::string::npos) break;
        i = slash + 1;
    }
    return true;
}

std::string now_iso8601() {
    using namespace std::chrono;
    system_clock::time_point now = system_clock::now();
    std::time_t t = system_clock::to_time_t(now);
    std::tm tm;
    localtime_r(&t, &tm);
    std::ostringstream oss;
    oss << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
    auto ms = duration_cast<milliseconds>(now.time_since_epoch()).count() % 1000;
    oss << "." << std::setfill('0') << std::setw(3) << ms;
    char tz[8] = {};
    std::strftime(tz, sizeof(tz), "%z", &tm);
    oss << tz;
    return oss.str();
}

std::string event_id() {
    using namespace std::chrono;
    long long us = duration_cast<microseconds>(system_clock::now().time_since_epoch()).count();
    static unsigned long counter = 0;
    std::ostringstream oss;
    oss << std::hex << us << "-" << getpid() << "-" << counter++;
    return oss.str();
}

std::string xdebug_home() {
    const char* home = std::getenv("HOME");
    return std::string(home ? home : "/tmp") + "/.xdebug";
}

bool heavy_key(const std::string& key) {
    return key == "rows" || key == "raw_rows" || key == "samples" ||
           key == "all_samples" || key == "trace" || key == "expanded_queries" ||
           key == "source_text" || key == "module_body" || key == "transactions" ||
           key == "beats" || key == "timeline" || key == "raw_samples" ||
           key == "all_changes" || key == "all_events";
}

Json sanitize_impl(const Json& value, int depth, bool& truncated) {
    if (depth > kMaxDepth) {
        truncated = true;
        return "<truncated:depth>";
    }
    if (value.is_string()) {
        std::string s = value.get<std::string>();
        if (s.size() > kMaxString) {
            truncated = true;
            return s.substr(0, kMaxString) + "...<truncated:string>";
        }
        return s;
    }
    if (value.is_array()) {
        Json out = Json::array();
        size_t count = 0;
        for (const auto& item : value) {
            if (count >= kMaxArray) {
                truncated = true;
                break;
            }
            out.push_back(sanitize_impl(item, depth + 1, truncated));
            count++;
        }
        if (value.size() > kMaxArray) out.push_back("<truncated:array>");
        return out;
    }
    if (value.is_object()) {
        Json out = Json::object();
        size_t count = 0;
        for (auto it = value.begin(); it != value.end(); ++it) {
            if (count >= kMaxObject) {
                truncated = true;
                break;
            }
            if (heavy_key(it.key())) {
                truncated = true;
                out[it.key()] = "<omitted:large-field>";
            } else {
                out[it.key()] = sanitize_impl(it.value(), depth + 1, truncated);
            }
            count++;
        }
        if (value.size() > kMaxObject) out["<truncated>"] = "object";
        return out;
    }
    return value;
}

void append_event(const std::string& path, Json event) {
    try {
        size_t slash = path.rfind('/');
        if (slash != std::string::npos && !ensure_dir_recursive(path.substr(0, slash))) return;
        std::ofstream out(path.c_str(), std::ios::app);
        if (!out) return;
        std::string line = event.dump();
        const size_t max_line = 256 * 1024;
        if (line.size() > max_line) {
            event["log_truncated"] = true;
            event["context"] = {{"message", "log event exceeded max line size and was truncated"}};
            line = event.dump();
        }
        out << line << "\n";
    } catch (...) {
    }
}

Json base_event(const std::string& layer,
                const std::string& component,
                const std::string& session_id,
                const std::string& action,
                const std::string& phase,
                bool ok,
                const Json& context) {
    Json event;
    event["ts"] = now_iso8601();
    event["event_id"] = event_id();
    event["pid"] = static_cast<int>(getpid());
    event["layer"] = layer;
    event["component"] = component;
    event["session_id"] = session_id.empty() ? "adhoc" : session_id;
    event["action"] = action;
    event["phase"] = phase;
    event["ok"] = ok;
    bool truncated = false;
    event["context"] = sanitize_impl(context, 0, truncated);
    if (truncated) event["log_truncated"] = true;
    return event;
}

} // namespace

std::string public_session_dir(const std::string& session_id) {
    return xdebug_home() + "/sessions/" +
           session_dir_name(session_id.empty() ? "adhoc" : session_id);
}

std::string public_action_log_path(const std::string& session_id) {
    return public_session_dir(session_id) + "/logs/actions.ndjson";
}

std::string component_log_path(const std::string& component,
                               const std::string& session_id,
                               const std::string& log_name) {
    return xdebug_home() + "/" + component + "/sessions/" +
           session_dir_name(session_id.empty() ? "adhoc" : session_id) +
           "/logs/" + log_name + ".ndjson";
}

Json sanitize_for_log(const Json& value) {
    bool truncated = false;
    Json out = sanitize_impl(value, 0, truncated);
    if (truncated && out.is_object()) out["log_truncated"] = true;
    return out;
}

Json request_summary_for_log(const Json& request) {
    Json target = request.value("target", Json::object());
    Json args = request.value("args", Json::object());
    Json out;
    if (request.contains("request_id")) out["request_id"] = request["request_id"];
    out["action"] = request.value("action", std::string());
    if (target.is_object()) {
        Json t;
        for (const char* k : {"session_id", "name", "mode", "daidir", "dbdir", "fsdb", "transport", "host", "bind_host", "port"}) {
            if (target.contains(k)) t[k] = target[k];
        }
        out["target"] = sanitize_for_log(t);
    }
    if (args.is_object()) {
        Json keys = Json::array();
        for (auto it = args.begin(); it != args.end(); ++it) keys.push_back(it.key());
        out["arg_keys"] = keys;
        if (args.contains("name")) out["name"] = args["name"];
        if (args.contains("session_id")) out["arg_session_id"] = args["session_id"];
    }
    if (request.contains("limits")) out["limits"] = sanitize_for_log(request["limits"]);
    if (request.contains("output")) out["output"] = sanitize_for_log(request["output"]);
    return out;
}

Json response_summary_for_log(const Json& response) {
    Json out;
    out["ok"] = response.value("ok", false);
    out["action"] = response.value("action", std::string());
    if (response.contains("request_id")) out["request_id"] = response["request_id"];
    if (response.contains("session")) out["session"] = sanitize_for_log(response["session"]);
    if (response.contains("summary")) out["summary"] = sanitize_for_log(response["summary"]);
    if (response.contains("meta")) out["meta"] = sanitize_for_log(response["meta"]);
    if (response.contains("error") && !response["error"].is_null()) out["error"] = sanitize_for_log(response["error"]);
    return out;
}

void update_public_session_manifest(const std::string& session_id,
                                    const std::string& mode,
                                    const std::string& daidir,
                                    const std::string& fsdb) {
    try {
        std::string dir = public_session_dir(session_id);
        if (!ensure_dir_recursive(dir)) return;
        Json manifest;
        manifest["session_id"] = session_id.empty() ? "adhoc" : session_id;
        if (!mode.empty()) manifest["mode"] = mode;
        if (!daidir.empty()) manifest["daidir"] = daidir;
        if (!fsdb.empty()) manifest["fsdb"] = fsdb;
        manifest["last_log_at"] = now_iso8601();
        std::string path = dir + "/session.json";
        Json old;
        std::ifstream in(path.c_str());
        if (in) {
            try { in >> old; } catch (...) {}
        }
        if (old.is_object() && old.contains("created_at")) manifest["created_at"] = old["created_at"];
        else manifest["created_at"] = manifest["last_log_at"];
        manifest["log_path"] = public_action_log_path(session_id);
        std::ofstream out(path.c_str(), std::ios::trunc);
        if (out) out << manifest.dump(2) << "\n";
    } catch (...) {
    }
}

void log_action_event(const std::string& layer,
                      const std::string& component,
                      const std::string& session_id,
                      const std::string& action,
                      const std::string& phase,
                      bool ok,
                      long long elapsed_ms,
                      const Json& context) {
    Json event = base_event(layer, component, session_id, action, phase, ok, context);
    event["elapsed_ms"] = elapsed_ms;
    if (layer == "public") {
        append_event(public_action_log_path(session_id), event);
    } else {
        append_event(component_log_path(component, session_id, "actions"), event);
    }
}

void log_lifecycle_event(const std::string& component,
                         const std::string& session_id,
                         const std::string& phase,
                         bool ok,
                         const Json& context) {
    Json event = base_event("backend", component, session_id, "", phase, ok, context);
    append_event(component_log_path(component, session_id, "lifecycle"), event);
}

void log_transport_event(const std::string& component,
                         const std::string& session_id,
                         const std::string& phase,
                         bool ok,
                         const Json& context) {
    Json event = base_event("backend", component, session_id, "", phase, ok, context);
    append_event(component_log_path(component, session_id, "transport"), event);
}

} // namespace xdebug_core
