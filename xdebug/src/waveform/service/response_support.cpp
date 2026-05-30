#include "action_support.h"

#include <algorithm>
#include <cctype>
#include <cstdio>

namespace xdebug_waveform {

Json base_response(const Json& req,
                   const std::string& action,
                   bool ok,
                   long long elapsed_ms) {
    Json out;
    out["api_version"] = kApiVersion;
    if (req.contains("request_id")) out["request_id"] = req["request_id"];
    out["ok"] = ok;
    out["action"] = action;
    out["tool"] = {{"name", "xdebug_waveform"}, {"version", "0.1.0"}};
    out["session"] = Json::object();
    out["summary"] = Json::object();
    out["data"] = ok ? Json::object() : Json(nullptr);
    out["findings"] = Json::array();
    out["suggested_next_actions"] = Json::array();
    out["warnings"] = Json::array();
    out["error"] = nullptr;
    out["meta"] = {{"elapsed_ms", elapsed_ms}, {"truncated", false}};
    return out;
}

Json error_response(const Json& req,
                    const std::string& action,
                    const std::string& code,
                    const std::string& message,
                    bool recoverable,
                    long long elapsed_ms) {
    Json out = base_response(req, action, false, elapsed_ms);
    out["error"] = {
        {"code", code},
        {"message", message},
        {"recoverable", recoverable},
        {"candidates", Json::array()},
        {"suggested_actions", Json::array()}
    };
    if (code == "SIGNAL_NOT_FOUND") {
        out["suggested_next_actions"].push_back({
            {"tool", "xdebug_waveform"},
            {"action", "scope.list"},
            {"reason", "exact signal was not found"}
        });
    }
    return out;
}

std::string response_verbosity(const Json& req, bool* valid) {
    if (valid) *valid = true;
    Json output = req.value("output", Json::object());
    std::string verbosity = "compact";
    if (!output.is_object()) {
        if (valid) *valid = false;
        return "compact";
    }
    auto it = output.find("verbosity");
    if (it != output.end()) {
        if (!it->is_string()) {
            if (valid) *valid = false;
            return "compact";
        }
        verbosity = it->get<std::string>();
    }
    if (verbosity.empty()) verbosity = "compact";
    std::transform(verbosity.begin(), verbosity.end(), verbosity.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (verbosity == "compact" || verbosity == "full" || verbosity == "debug") return verbosity;
    if (valid) *valid = false;
    return "compact";
}

bool compact_mode(const Json& req) {
    std::string verbosity = response_verbosity(req);
    return verbosity != "full" && verbosity != "debug";
}

int max_items_arg(const Json& args, const Json& limits, int def) {
    int value = int_or(args, "max_items", int_or(limits, "max_items", def));
    return value >= 0 ? value : def;
}

int max_examples_arg(const Json& args, const Json& limits, int def) {
    int value = int_or(args, "max_examples", int_or(limits, "max_examples", def));
    return value >= 0 ? value : def;
}

namespace {

bool json_empty_or_null(const Json& v) {
    return v.is_null() || (v.is_object() && v.empty()) || (v.is_array() && v.empty());
}

Json compact_session_json(const Json& full) {
    Json out;
    if (full.contains("id")) out["id"] = full["id"];
    if (full.contains("fsdb")) out["fsdb"] = full["fsdb"];
    return out;
}

Json compact_error_json(const Json& full) {
    if (!full.is_object()) return full;
    Json out;
    if (full.contains("code")) out["code"] = full["code"];
    if (full.contains("message")) out["message"] = full["message"];
    if (full.contains("recoverable")) out["recoverable"] = full["recoverable"];
    if (full.contains("candidates") && !json_empty_or_null(full["candidates"])) out["candidates"] = full["candidates"];
    if (full.contains("suggested_actions") && !json_empty_or_null(full["suggested_actions"])) {
        out["suggested_actions"] = full["suggested_actions"];
    }
    return out;
}

Json compact_response(const Json& full) {
    Json out;
    if (full.contains("request_id")) out["request_id"] = full["request_id"];
    out["ok"] = full.value("ok", false);
    out["action"] = full.value("action", std::string());

    bool ok = out["ok"].get<bool>();
    if (full.contains("summary") && !json_empty_or_null(full["summary"])) out["summary"] = full["summary"];
    if (full.contains("data") && !json_empty_or_null(full["data"])) {
        out["data"] = full["data"];
        std::string action = out.value("action", std::string());
        if ((action == "session.open" || action == "session.list") && out["data"].is_object()) {
            if (out["data"].contains("session")) out["data"]["session"] = compact_session_json(out["data"]["session"]);
            if (out["data"].contains("sessions") && out["data"]["sessions"].is_array()) {
                Json sessions = Json::array();
                for (const auto& s : out["data"]["sessions"]) sessions.push_back(compact_session_json(s));
                out["data"]["sessions"] = sessions;
            }
        }
    }
    if (full.contains("findings") && !json_empty_or_null(full["findings"])) out["findings"] = full["findings"];
    if (!ok && full.contains("error") && !json_empty_or_null(full["error"])) out["error"] = compact_error_json(full["error"]);
    if (!ok && full.contains("suggested_next_actions") && !json_empty_or_null(full["suggested_next_actions"])) {
        out["suggested_next_actions"] = full["suggested_next_actions"];
    }
    if (full.contains("warnings") && !json_empty_or_null(full["warnings"])) out["warnings"] = full["warnings"];
    if (full.contains("meta") && full["meta"].is_object() && full["meta"].value("truncated", false)) out["meta"] = {{"truncated", true}};
    if (!ok && full.contains("session") && !json_empty_or_null(full["session"])) out["session"] = compact_session_json(full["session"]);
    return out;
}

} // namespace

Json finalize_response(const Json& req, const Json& full) {
    std::string verbosity = response_verbosity(req);
    if (verbosity == "full" || verbosity == "debug") return full;
    Json out = compact_response(full);
    Json output = req.value("output", Json::object());
    if (output.is_object() && output.value("include_suggestions", false) &&
        full.contains("suggested_next_actions") && !full["suggested_next_actions"].empty()) {
        out["suggested_next_actions"] = full["suggested_next_actions"];
    }
    return out;
}

void print_json(const Json& j) {
    std::printf("%s\n", j.dump(2).c_str());
}

bool get_string(const Json& obj, const char* key, std::string& out) {
    auto it = obj.find(key);
    if (it == obj.end() || !it->is_string()) return false;
    out = it->get<std::string>();
    return true;
}

std::string string_or(const Json& obj, const char* key, const std::string& def) {
    std::string value;
    return get_string(obj, key, value) ? value : def;
}

int int_or(const Json& obj, const char* key, int def) {
    auto it = obj.find(key);
    if (it == obj.end() || !it->is_number_integer()) return def;
    return it->get<int>();
}

bool bool_or(const Json& obj, const char* key, bool def) {
    auto it = obj.find(key);
    if (it == obj.end() || !it->is_boolean()) return def;
    return it->get<bool>();
}

} // namespace xdebug_waveform
