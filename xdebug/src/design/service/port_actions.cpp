#include "action_support.h"

#include "../protocol/protocol.h"

namespace xdebug_design {

json run_port_like_action(const json& request, const std::string& action) {
    json response = base_response(request, action);
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    std::string path = args.value("path", args.value("instance", args.value("signal", args.value("interface", ""))));
    if (path.empty()) {
        return error_response(request, action, "MISSING_FIELD", "args.path, args.instance, args.signal, or args.interface is required");
    }
    int limit = request.value("limits", json::object()).value("max_results", args.value("limit", 0));
    std::string cmd = action == "port.trace" ? CMD_PORT_TRACE_AI :
                      action == "instance.map" ? CMD_INSTANCE_MAP_AI : CMD_INTERFACE_RESOLVE_AI;
    cmd += " " + path;
    if (limit > 0) cmd += " --limit " + std::to_string(limit);
    json payload;
    std::string status, message;
    if (!send_json_command(session_id, cmd, payload, status, message)) {
        return error_response(request, action, "SESSION_UNHEALTHY", message.empty() ? status : message);
    }
    response["ok"] = payload.value("ok", true);
    response["summary"] = {{"query", payload.value("query", path)}, {"port_count", payload.value("port_count", 0)},
        {"modport_port_count", payload.value("modport_port_count", 0)}, {"truncated", payload.value("truncated", false)}};
    response["data"] = payload;
    response["meta"]["truncated"] = payload.value("truncated", false);
    if (!response["ok"].get<bool>()) {
        json err = payload.value("error", json::object());
        response["error"] = {{"code", err.value("code", "TRACE_NO_RESULT")},
            {"message", err.value("message", "port/interface query failed")}, {"recoverable", true},
            {"candidates", json::array()}, {"suggested_actions", json::array()}};
    }
    return response;
}

} // namespace xdebug_design
