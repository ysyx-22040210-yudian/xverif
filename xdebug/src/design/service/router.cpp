#include "action_support.h"

namespace xdebug_design {

namespace {

json run_batch(const json& request) {
    json response = base_response(request, "batch");
    json args = request.value("args", json::object());
    json requests = args.value("requests", json::array());
    std::string mode = args.value("mode", "continue_on_error");
    json results = json::array();
    bool all_ok = true;
    for (auto child : requests) {
        if (!child.contains("api_version")) child["api_version"] = API_VERSION;
        json child_resp = handle_request(child);
        if (!child_resp.value("ok", false)) all_ok = false;
        results.push_back(child_resp);
        if (!child_resp.value("ok", false) && mode == "stop_on_error") break;
    }
    response["ok"] = all_ok;
    response["summary"] = {{"count", results.size()}, {"all_ok", all_ok}};
    response["data"] = {{"results", results}};
    return response;
}

json handle_session_action(const json& request, const std::string& action) {
    json response = base_response(request, action);
    SessionManager manager;
    if (action == "session.open" || action == "session.ensure") {
        std::vector<std::string> args = target_dbdir_args(request);
        if (args.empty()) return error_response(request, action, "INVALID_TARGET", "target.dbdir is required");
        SessionEnsureResult result = manager.ensure_session(args, request_session_name(request), request_transport_options(request));
        if (!result.ok) return error_response(request, action, ensure_error_code(result), result.message);
        response["session"] = session_to_json(result.info);
        response["session"]["reused"] = result.reused;
        response["session"]["healthy"] = true;
        response["summary"] = {{"id", result.session_id}, {"session_id", result.session_id},
                               {"status", result.status}, {"reused", result.reused}};
        response["data"] = {{"session", response["session"]}};
        return response;
    }
    if (action == "session.list") {
        json sessions = json::array();
        for (const auto& s : manager.list_sessions()) sessions.push_back(session_to_json(s));
        response["summary"] = {{"count", sessions.size()}};
        response["data"] = {{"sessions", sessions}};
        return response;
    }
    if (action == "session.doctor") {
        json target = request.value("target", json::object());
        json args = request.value("args", json::object());
        std::string sid;
        if (target.contains("session_id")) sid = json_session_id(target["session_id"]);
        if (sid.empty() && args.contains("session_id")) sid = json_session_id(args["session_id"]);
        if (sid.empty()) return error_response(request, action, "MISSING_FIELD", "target.session_id or args.session_id string is required");
        SessionHealth h = manager.diagnose_session(sid);
        response["ok"] = h.healthy;
        response["session"] = session_to_json(h.info);
        response["summary"] = {{"id", sid}, {"session_id", sid}, {"healthy", h.healthy},
            {"status", session_health_status_name(h.status)}, {"message", h.message}};
        response["data"] = {{"health", response["summary"]}};
        if (!h.healthy) response["error"] = {{"code", "SESSION_UNHEALTHY"}, {"message", h.message},
            {"recoverable", true}, {"candidates", json::array()}, {"suggested_actions", json::array()}};
        return response;
    }
    if (action == "session.kill" || action == "session.close") {
        json args = request.value("args", json::object());
        if (args.value("id", "") == "all") {
            bool ok = manager.kill_all_sessions();
            response["ok"] = ok;
            response["summary"] = {{"target", "all"}, {"killed", ok}};
            return response;
        }
        std::string sid;
        json target = request.value("target", json::object());
        if (target.contains("session_id")) sid = json_session_id(target["session_id"]);
        else if (args.contains("session_id")) sid = json_session_id(args["session_id"]);
        else if (args.contains("id")) sid = json_session_id(args["id"]);
        if (sid.empty()) return error_response(request, action, "MISSING_FIELD", "session id string is required");
        bool ok = manager.kill_session(sid);
        response["ok"] = ok;
        response["summary"] = {{"id", sid}, {"session_id", sid}, {"killed", ok}};
        if (!ok) response["error"] = {{"code", "SESSION_NOT_FOUND"}, {"message", "failed to kill session"},
            {"recoverable", true}, {"candidates", json::array()}, {"suggested_actions", json::array()}};
        return response;
    }
    return error_response(request, action, "UNKNOWN_ACTION", "unknown session action");
}

} // namespace

json schema_payload() {
    return {{"api_version", API_VERSION}, {"request", {{"api_version", API_VERSION}, {"request_id", "optional-id"},
        {"action", "trace.driver"}, {"target", {{"dbdir", "/path/to/simv.daidir"}, {"session_id", nullptr}, {"auto_ensure", true}}},
        {"args", {{"name", "case_a"}, {"transport", "uds"}, {"bind_host", "127.0.0.1"}, {"port", 0}}},
        {"limits", {{"max_results", 50}, {"max_depth", 1}, {"max_paths", 10}, {"timeout_ms", 5000}}},
        {"output", {{"verbosity", "compact"}, {"include_source", true}, {"include_control_dependencies", true},
                    {"include_expr", true}, {"include_graph", false}}}}},
        {"response", {{"ok", true}, {"action", "trace.driver"}, {"tool", {{"name", "xdebug_design"}, {"version", TOOL_VERSION}}},
            {"session", json::object()}, {"summary", json::object()}, {"data", json::object()}, {"findings", json::array()},
            {"suggested_next_actions", json::array()}, {"warnings", json::array()}, {"error", nullptr}, {"meta", json::object()}}},
        {"transport", {{"default", "uds"}, {"values", json::array({"uds", "tcp"})},
            {"tcp", "session.open/session.ensure accept args.transport=tcp with optional bind_host/host/port. port 0 or omitted lets the server bind an automatically assigned port and write it to endpoint.json."}}}};
}

json actions_payload() {
    json implemented = json::array({"session.open", "session.ensure", "session.list", "session.doctor", "session.kill", "session.close",
        "trace.driver", "trace.load", "trace.query", "signal.resolve", "signal.canonicalize",
        "trace.expand", "trace.graph", "trace.path", "trace.explain", "control.explain", "source.context",
        "expr.normalize", "procedural.assignment", "sequential.update", "fsm.explain", "counter.explain",
        "port.trace", "instance.map", "interface.resolve", "batch"});
    return {{"api_version", API_VERSION}, {"implemented", implemented}, {"experimental", json::array()}};
}

json handle_request(const json& request) {
    std::string action = request.value("action", "");
    if (request.value("api_version", std::string(API_VERSION)) != API_VERSION) {
        return error_response(request, action, "UNSUPPORTED_API_VERSION", "expected xdebug.internal.v1", false);
    }
    if (action.empty()) return error_response(request, action, "MISSING_FIELD", "action is required");
    if (action == "batch") return run_batch(request);
    if (starts_with(action, "session.")) return handle_session_action(request, action);
    if (action == "trace.driver") return run_trace_action(request, "driver");
    if (action == "trace.load") return run_trace_action(request, "load");
    if (action == "trace.query") {
        std::string mode = request.value("args", json::object()).value("mode", "driver");
        return run_trace_action(request, mode == "load" ? "load" : "driver");
    }
    if (action == "signal.resolve") return run_signal_resolve_action(request);
    if (action == "signal.canonicalize") return canonicalize_signal(request);
    if (action == "trace.expand" || action == "trace.graph") return trace_expand_like(request, false);
    if (action == "trace.path") return trace_path(request);
    if (action == "trace.explain") return trace_expand_like(request, true);
    if (action == "control.explain") return control_explain(request);
    if (action == "source.context") return source_context(request);
    if (action == "expr.normalize") return run_expr_normalize_action(request);
    if (action == "procedural.assignment") return run_procedural_assignment_action(request);
    if (action == "sequential.update") return run_sequential_update_action(request);
    if (action == "fsm.explain") return run_fsm_explain_action(request);
    if (action == "counter.explain") return run_counter_explain_action(request);
    if (action == "port.trace" || action == "instance.map" || action == "interface.resolve") return run_port_like_action(request, action);
    return error_response(request, action, "UNKNOWN_ACTION", "unknown action: " + action, true);
}

} // namespace xdebug_design
