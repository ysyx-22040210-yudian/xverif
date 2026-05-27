#include "api/dispatcher.h"
#include "api/action_catalog.h"
#include "api/response.h"

#include <limits.h>
#include <string>
#include <unistd.h>

namespace xdebug {

namespace {

bool has_string(const Json& object, const char* key) {
    return object.contains(key) && object[key].is_string() &&
           !object[key].get<std::string>().empty();
}

std::string requested_name(const Json& request) {
    Json args = request.value("args", Json::object());
    Json target = request.value("target", Json::object());
    if (has_string(args, "name")) return args["name"].get<std::string>();
    if (has_string(target, "name")) return target["name"].get<std::string>();
    return "";
}

Json engine_error(const Json& request, const std::string& action, const std::string& message) {
    return make_error(request, action, "INTERNAL_ENGINE_FAILED", message);
}

std::string stable_resource_path(const std::string& path) {
    if (path.empty() || path[0] == '/') return path;
    char cwd[PATH_MAX] = {};
    return getcwd(cwd, sizeof(cwd)) ? std::string(cwd) + "/" + path : path;
}

void stabilize_resource_paths(Json& target) {
    if (has_string(target, "daidir")) {
        target["daidir"] = stable_resource_path(target["daidir"].get<std::string>());
    }
    if (has_string(target, "fsdb")) {
        target["fsdb"] = stable_resource_path(target["fsdb"].get<std::string>());
    }
}

} // namespace

Dispatcher::Dispatcher(const std::string& executable_dir)
    : adapter_(executable_dir) {}

bool Dispatcher::supports_action(EngineKind kind, const std::string& action) const {
    return kind == EngineKind::Design
        ? design_actions().count(action) != 0
        : waveform_actions().count(action) != 0;
}

std::string Dispatcher::mode_for_target(const Json& target) const {
    const bool daidir = has_string(target, "daidir");
    const bool fsdb = has_string(target, "fsdb");
    if (daidir && fsdb) return "combined";
    if (daidir) return "design";
    if (fsdb) return "waveform";
    return "";
}

Json Dispatcher::resolve_target(const Json& request) const {
    Json target = request.value("target", Json::object());
    if (has_string(target, "session_id")) {
        SessionRecord record;
        if (sessions_.get(target["session_id"].get<std::string>(), record)) {
            if (!record.daidir.empty()) target["daidir"] = record.daidir;
            if (!record.fsdb.empty()) target["fsdb"] = record.fsdb;
            target["mode"] = record.mode;
        }
    }
    stabilize_resource_paths(target);
    return target;
}

Json Dispatcher::forward_action(const Json& request, EngineKind kind) {
    Json forwarded = request;
    Json target = forwarded.value("target", Json::object());
    Json args = forwarded.value("args", Json::object());
    if (!has_string(target, "session_id") && has_string(args, "name") && !has_string(target, "name")) {
        target["name"] = args["name"];
    }
    forwarded["target"] = target;
    Json response;
    std::string error;
    if (!adapter_.invoke(kind, forwarded, response, error)) {
        return engine_error(request, request.value("action", std::string()), error);
    }
    return response;
}

Json Dispatcher::handle_batch(const Json& request) {
    Json requests = request.value("args", Json::object()).value("requests", Json::array());
    if (!requests.is_array()) {
        return make_error(request, "batch", "MISSING_FIELD", "args.requests[] is required");
    }
    Json response = make_response(request, "batch");
    Json results = Json::array();
    bool all_ok = true;
    std::string mode = request.value("args", Json::object()).value("mode", std::string("continue_on_error"));
    for (auto child : requests) {
        if (!child.contains("api_version")) child["api_version"] = kApiVersion;
        Json result = dispatch(child);
        results.push_back(result);
        if (!result.value("ok", false)) {
            all_ok = false;
            if (mode == "stop_on_error") break;
        }
    }
    response["ok"] = all_ok;
    response["summary"] = {{"count", results.size()}, {"all_ok", all_ok}};
    response["data"] = {{"results", results}};
    if (!all_ok) response["error"] = {{"code", "BATCH_PARTIAL_FAILURE"}, {"message", "one or more child requests failed"}, {"recoverable", true}};
    return response;
}

Json Dispatcher::handle_session(const Json& request, const std::string& action) {
    Json target = resolve_target(request);
    Json args = request.value("args", Json::object());
    if (action == "session.list") {
        Json response = make_response(request, action);
        Json records = Json::array();
        for (const auto& record : sessions_.list()) records.push_back(session_record_json(record));
        response["summary"] = {{"session_count", records.size()}};
        response["data"] = {{"sessions", records}};
        return response;
    }
    if (action == "session.gc") {
        Json wave_request = request;
        wave_request["action"] = "session.gc";
        forward_action(wave_request, EngineKind::Waveform);
        Json response = make_response(request, action);
        response["summary"] = {{"status", "completed"}};
        return response;
    }
    if (action == "session.open" || action == "session.ensure") {
        const std::string name = requested_name(request);
        const std::string mode = mode_for_target(target);
        if (name.empty()) return make_error(request, action, "MISSING_FIELD", "args.name is required");
        if (mode.empty()) return make_error(request, action, "RESOURCE_REQUIRED", "target.daidir or target.fsdb is required");
        SessionRecord existing;
        if (sessions_.get(name, existing)) {
            if (action == "session.ensure" && existing.mode == mode) {
                Json response = make_response(request, action);
                response["session"] = session_record_json(existing);
                response["summary"] = {{"session_id", name}, {"mode", mode}, {"reused", true}};
                return response;
            }
            return make_error(request, action, "SESSION_ID_EXISTS", "session id already exists: " + name);
        }
        Json open_request = request;
        open_request["action"] = "session.open";
        open_request["target"] = target;
        Json design_result = nullptr;
        Json wave_result = nullptr;
        if (mode == "design" || mode == "combined") {
            design_result = forward_action(open_request, EngineKind::Design);
            if (!design_result.value("ok", false)) return design_result;
        }
        if (mode == "waveform" || mode == "combined") {
            wave_result = forward_action(open_request, EngineKind::Waveform);
            if (!wave_result.value("ok", false)) {
                if (!design_result.is_null()) {
                    Json cleanup = request;
                    cleanup["action"] = "session.kill";
                    cleanup["target"] = {{"session_id", name}};
                    forward_action(cleanup, EngineKind::Design);
                }
                return wave_result;
            }
        }
        SessionRecord record;
        record.id = name;
        record.mode = mode;
        record.daidir = target.value("daidir", std::string());
        record.fsdb = target.value("fsdb", std::string());
        if (!sessions_.put(record)) {
            return make_error(request, action, "SESSION_STORE_FAILED", "failed to store xdebug session");
        }
        Json response = make_response(request, action);
        response["session"] = session_record_json(record);
        response["summary"] = {{"session_id", name}, {"mode", mode}, {"reused", false}};
        response["data"] = {{"session", response["session"]}};
        return response;
    }
    std::string id = target.value("session_id", args.value("session_id", args.value("id", std::string())));
    if (id == "all") {
        for (const auto& record : sessions_.list()) {
            Json kill_req = request;
            kill_req["target"] = {{"session_id", record.id}};
            kill_req["args"] = Json::object();
            handle_session(kill_req, "session.kill");
        }
        Json response = make_response(request, action);
        response["summary"] = {{"status", "removed"}, {"target", "all"}};
        return response;
    }
    if (id.empty()) return make_error(request, action, "MISSING_FIELD", "target.session_id is required");
    SessionRecord record;
    if (!sessions_.get(id, record)) return make_error(request, action, "SESSION_NOT_FOUND", "session not found: " + id);
    if (action == "session.kill" || action == "session.close") {
        bool ok = true;
        Json inner = request;
        inner["action"] = "session.kill";
        inner["target"] = {{"session_id", id}};
        if (record.mode == "design" || record.mode == "combined") {
            ok = forward_action(inner, EngineKind::Design).value("ok", false) && ok;
        }
        if (record.mode == "waveform" || record.mode == "combined") {
            ok = forward_action(inner, EngineKind::Waveform).value("ok", false) && ok;
        }
        sessions_.remove(id);
        Json response = make_response(request, action, ok);
        response["summary"] = {{"session_id", id}, {"removed", ok}};
        return response;
    }
    if (action == "session.doctor") {
        Json response = make_response(request, action);
        Json health = Json::object();
        bool healthy = true;
        Json inner = request;
        inner["target"] = {{"session_id", id}};
        if (record.mode == "design" || record.mode == "combined") {
            health["design"] = forward_action(inner, EngineKind::Design);
            healthy = health["design"].value("ok", false) && healthy;
        }
        if (record.mode == "waveform" || record.mode == "combined") {
            health["waveform"] = forward_action(inner, EngineKind::Waveform);
            healthy = health["waveform"].value("ok", false) && healthy;
        }
        response["ok"] = healthy;
        response["session"] = session_record_json(record);
        response["summary"] = {{"session_id", id}, {"mode", record.mode}, {"healthy", healthy}};
        response["data"] = {{"health", health}};
        if (!healthy) response["error"] = {{"code", "SESSION_UNHEALTHY"}, {"message", "one or more session engines are unhealthy"}, {"recoverable", true}};
        return response;
    }
    return make_error(request, action, "UNKNOWN_ACTION", "unknown session action: " + action);
}

Json Dispatcher::dispatch(const Json& request) {
    const std::string action = request.value("action", std::string());
    if (action == "schema") return catalog_schema_response(request);
    if (action == "actions") return catalog_actions_response(request);
    if (action == "batch") return handle_batch(request);
    if (action.compare(0, 8, "session.") == 0) return handle_session(request, action);

    Json target = resolve_target(request);
    Json routed = request;
    routed["target"] = target;
    const std::string mode = target.value("mode", mode_for_target(target));
    if (action == "trace.active_driver") return active_trace_.run(request, target);
    if (supports_action(EngineKind::Design, action)) {
        if (action != "source.context" && action != "expr.normalize" &&
            mode != "design" && mode != "combined" && !has_string(target, "session_id")) {
            return make_error(request, action, "RESOURCE_REQUIRED", "design action requires target.daidir or a design session");
        }
        Json response = forward_action(routed, EngineKind::Design);
        if (response.value("ok", false) && !has_string(target, "session_id") &&
            has_string(target, "daidir") && !requested_name(request).empty()) {
            SessionRecord record;
            record.id = requested_name(request);
            record.mode = mode.empty() ? "design" : mode;
            record.daidir = target.value("daidir", std::string());
            record.fsdb = target.value("fsdb", std::string());
            sessions_.put(record);
        }
        return response;
    }
    if (supports_action(EngineKind::Waveform, action)) {
        if (mode != "waveform" && mode != "combined" && !has_string(target, "session_id")) {
            return make_error(request, action, "RESOURCE_REQUIRED", "waveform action requires target.fsdb or a waveform session");
        }
        Json response = forward_action(routed, EngineKind::Waveform);
        if (response.value("ok", false) && !has_string(target, "session_id") &&
            has_string(target, "fsdb") && !requested_name(request).empty()) {
            SessionRecord record;
            record.id = requested_name(request);
            record.mode = mode.empty() ? "waveform" : mode;
            record.daidir = target.value("daidir", std::string());
            record.fsdb = target.value("fsdb", std::string());
            sessions_.put(record);
        }
        return response;
    }
    return make_error(request, action, "UNKNOWN_ACTION", "unknown action: " + action);
}

} // namespace xdebug
