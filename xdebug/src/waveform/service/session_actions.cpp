#include "router_actions.h"

#include "../session/session_registry.h"

namespace xdebug_waveform {

int run_session_action(const Json& req, const std::string& action, const Json& target,
                       const Json& args, long long elapsed_ms, bool& handled) {
    handled = action.compare(0, 8, "session.") == 0;
    if (!handled) return 0;

    auto ok_out = [&]() {
        return base_response(req, action, true, elapsed_ms);
    };
    auto emit = [&](const Json& out, int rc = 0) -> int {
        print_json(finalize_response(req, out));
        return rc;
    };

    if (action == "session.open") {
        std::string fsdb;
        if (!get_string(target, "fsdb", fsdb)) {
            return print_error_and_return(req, action, "MISSING_FIELD", "target.fsdb is required", elapsed_ms);
        }
        std::string name;
        if (!get_string(args, "name", name) && !get_string(target, "name", name)) {
            return print_error_and_return(req, action, "MISSING_FIELD", "session.open requires args.name", elapsed_ms);
        }
        if (!SessionRegistry::is_valid_session_name(name)) {
            return print_error_and_return(req, action, "INVALID_SESSION_ID", "invalid session name: " + name, elapsed_ms);
        }
        SessionManager manager;
        SessionRegistry registry;
        if (registry.exists(name)) {
            return print_error_and_return(req, action, "SESSION_ID_EXISTS", "session id already exists: " + name, elapsed_ms);
        }
        SessionTransportOptions transport;
        transport.transport = string_or(args, "transport", string_or(target, "transport", "uds"));
        transport.bind_host = string_or(args, "bind_host", string_or(args, "bind", string_or(target, "bind_host", string_or(target, "bind", ""))));
        transport.host = string_or(args, "host", string_or(target, "host", ""));
        transport.port = int_or(args, "port", int_or(target, "port", 0));
        std::string sid = create_session_quiet(manager, fsdb, name, transport);
        SessionInfo info;
        if (sid.empty() || !manager.get_session(sid, info)) {
            return print_error_and_return(req, action, "INVALID_TARGET", "failed to open fsdb: " + fsdb, elapsed_ms);
        }
        Json out = ok_out();
        fill_session(out, info);
        out["summary"] = {{"session_id", sid}, {"fsdb", info.fsdb_file}};
        out["data"]["session"] = session_info_json(info);
        return emit(out);
    }

    if (action == "session.list") {
        SessionManager manager;
        Json out = ok_out();
        Json arr = Json::array();
        for (const auto& s : manager.list_sessions()) arr.push_back(session_info_json(s));
        out["summary"] = {{"session_count", arr.size()}};
        out["data"]["sessions"] = arr;
        return emit(out);
    }

    if (action == "session.gc") {
        SessionManager manager;
        manager.gc_sessions();
        Json out = ok_out();
        out["summary"] = {{"status", "completed"}};
        return emit(out);
    }

    if (action == "session.kill") {
        SessionManager manager;
        bool ok = false;
        if (string_or(args, "id", "") == "all" || string_or(args, "session_id", "") == "all") {
            ok = manager.kill_all_sessions();
        } else {
            std::string sid = string_or(target, "session_id", string_or(args, "session_id", string_or(args, "id", "")));
            if (sid.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "session.kill requires target.session_id or args.id", elapsed_ms);
            ok = manager.kill_session(sid);
        }
        if (!ok) return print_error_and_return(req, action, "SESSION_UNHEALTHY", "failed to kill session", elapsed_ms);
        Json out = ok_out();
        out["summary"] = {{"status", "removed"}};
        return emit(out);
    }

    if (action == "session.doctor") {
        std::string sid = string_or(target, "session_id", string_or(args, "session_id", ""));
        if (sid.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "session.doctor requires session_id", elapsed_ms);
        SessionManager manager;
        SessionHealth h = manager.diagnose_session(sid);
        Json out = base_response(req, action, h.healthy, elapsed_ms);
        fill_session(out, h.info);
        out["summary"] = {{"healthy", h.healthy}, {"status", session_health_status_name(h.status)}, {"message", h.message}};
        out["data"]["health"] = out["summary"];
        if (!h.healthy) {
            out["error"] = {{"code", "SESSION_UNHEALTHY"}, {"message", h.message}, {"recoverable", true}, {"candidates", Json::array()}, {"suggested_actions", Json::array()}};
        }
        return emit(out, h.healthy ? 0 : 1);
    }

    return print_error_and_return(req, action, "UNKNOWN_ACTION", "unhandled action: " + action, elapsed_ms);
}

} // namespace xdebug_waveform
