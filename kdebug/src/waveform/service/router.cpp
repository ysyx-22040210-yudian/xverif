#include "action_support.h"
#include "action_registry.h"
#include "router_actions.h"
#include "logging/action_log.h"

#include <chrono>
#include <string>

namespace kdebug_waveform {

int run_query(const Json& req, long long elapsed_ms) {
    std::string action;
    if (!get_string(req, "action", action)) {
        return print_error_and_return(req, "", "MISSING_FIELD", "request.action is required", elapsed_ms);
    }

    Json target_for_log = req.value("target", Json::object());
    Json args_for_log = req.value("args", Json::object());
    std::string log_sid = string_or(target_for_log, "session_id", string_or(args_for_log, "session_id",
        string_or(args_for_log, "name", string_or(target_for_log, "name", "adhoc"))));

    kdebug_core::log_action_event("backend", "waveform", log_sid, action, "begin", true, 0,
                                  {{"request", kdebug_core::request_summary_for_log(req)}});

    auto log_return = [&](const Json& out, int rc) -> int {
        kdebug_core::log_action_event("backend", "waveform", log_sid, action, "end",
            out.value("ok", rc == 0), elapsed_ms,
            {{"response", kdebug_core::response_summary_for_log(out)},
             {"request", out.value("ok", false) ? kdebug_core::request_summary_for_log(req)
                                                : kdebug_core::sanitize_for_log(req)}});
        print_json(finalize_response(req, out));
        return rc;
    };

    if (!action_known(action)) {
        Json out = error_response(req, action, "UNKNOWN_ACTION",
            "action is not implemented: " + action, true, elapsed_ms);
        return log_return(out, 1);
    }

    Json target = req.value("target", Json::object());
    Json args = req.value("args", Json::object());
    Json limits = req.value("limits", Json::object());

    bool verbosity_valid = true;
    response_verbosity(req, &verbosity_valid);
    if (!verbosity_valid) {
        return print_error_and_return(req, action, "INVALID_REQUEST",
            "output.verbosity must be compact, full, or debug", elapsed_ms);
    }

    int max_rows = int_or(limits, "max_rows", int_or(limits, "max_events", 1000));

    // 1. Session actions (open, list, gc, kill, doctor, etc.)
    bool handled = false;
    int handler_rc = run_session_action(req, action, target, args, elapsed_ms, handled);
    if (handled) return handler_rc;

    // 2. Resolve session for all other actions
    std::string sid;
    SessionInfo info;
    std::string err;
    if (!resolve_session(target, sid, info, err)) {
        const char* code = err.find("target.session_id is required") != std::string::npos
            ? "SESSION_REQUIRED" : "SESSION_NOT_FOUND";
        return print_error_and_return(req, action, code, err, elapsed_ms);
    }

    // 3. Dispatch through WaveformActionRegistry (covers value.*, scope.list, list.*,
    //    rc.generate, verify.conditions, cursor.*, signal.*, expr.eval_at, window.verify,
    //    handshake.inspect, detect_anomaly, sampled_pulse.inspect, inspect_signal,
    //    axi.channel_stall/outstanding_timeline/request_response_pair/latency_outlier,
    //    apb.transfer_window, etc.)
    const WaveformActionHandler* handler = default_waveform_action_registry().find(action);
    if (handler) {
        WaveformActionContext ctx{req, action, args, limits, sid, info, elapsed_ms, max_rows};
        int rc = handler->run(ctx);
        // Handler already printed output; log end event for consistency
        kdebug_core::log_action_event("backend", "waveform", log_sid, action, "end",
            rc == 0, elapsed_ms,
            {{"response", {{"ok", rc == 0}, {"action", action}}},
             {"request", kdebug_core::request_summary_for_log(req)}});
        return rc;
    }

    // 4. Protocol actions (apb.*, axi.*, event.* that aren't handled above)
    handler_rc = run_protocol_action(req, action, args, limits, sid, info, elapsed_ms, handled);
    if (handled) return handler_rc;

    // 5. Unknown action
    return print_error_and_return(req, action, "UNKNOWN_ACTION",
        "unhandled action: " + action, elapsed_ms);
}

} // namespace kdebug_waveform
