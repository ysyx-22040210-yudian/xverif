#include "api/stdio_loop.h"

#include "api/dispatcher.h"
#include "api/request_parser.h"
#include "api/response.h"
#include "api/xout_renderer.h"

#include <iostream>
#include <string>
#include <unistd.h>

namespace xdebug {

namespace {

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

void write_jsonl(const Json& obj) {
    std::cout << obj.dump() << "\n" << std::flush;
}

Json ready_envelope(int pid) {
    return {
        {"type", "ready"},
        {"protocol", "xdebug-stdio-loop"},
        {"version", 1},
        {"pid", pid},
    };
}

Json quit_envelope(const std::string& id) {
    return {
        {"id", id},
        {"ok", true},
        {"payload_format", "json"},
        {"json", {{"ok", true}, {"action", "stdio.quit"}}},
    };
}

Json loop_error(const std::string& id, const std::string& code, const std::string& message) {
    return {
        {"id", id},
        {"ok", false},
        {"error", {{"code", code}, {"message", message}}},
    };
}

std::string request_id_or_seq(const Json& req, int seq) {
    if (req.contains("request_id") && req["request_id"].is_string()) {
        return req["request_id"].get<std::string>();
    }
    if (req.contains("id") && req["id"].is_string()) {
        return req["id"].get<std::string>();
    }
    return "req-" + std::to_string(seq);
}

bool request_wants_json(const Json& req, bool default_json) {
    if (default_json) return true;
    auto it = req.find("output");
    if (it != req.end() && it->is_object()) {
        auto fmt = it->find("format");
        if (fmt != it->end() && fmt->is_string()) {
            return fmt->get<std::string>() == "json";
        }
    }
    return false;
}

Json make_envelope(const std::string& id, const Json& req, const Json& rsp, bool default_json) {
    Json out;
    out["id"] = id;
    out["ok"] = rsp.value("ok", false);

    if (!rsp.value("ok", false)) {
        out["error"] = rsp.value("error", Json::object());
        return out;
    }

    if (request_wants_json(req, default_json)) {
        out["payload_format"] = "json";
        out["json"] = rsp;
    } else {
        out["payload_format"] = "xout";
        out["xout"] = render_xout_response(rsp);
    }

    return out;
}

} // namespace

// ---------------------------------------------------------------------------
// main loop
// ---------------------------------------------------------------------------

int run_stdio_loop(const std::string& executable_dir, bool default_json) {
    Dispatcher dispatcher(executable_dir);

    // Announce the loop is ready
    write_jsonl(ready_envelope(static_cast<int>(getpid())));

    std::string line;
    int seq = 0;

    while (std::getline(std::cin, line)) {
        ++seq;
        if (line.empty()) continue;

        // Parse the JSON request
        Json req;
        std::string error;
        if (!parse_request_text(line, req, error)) {
            write_jsonl(loop_error("req-" + std::to_string(seq), "INVALID_JSON", error));
            continue;
        }

        const std::string id = request_id_or_seq(req, seq);
        const std::string action = req.value("action", std::string());

        // Handle quit
        if (action == "stdio.quit") {
            write_jsonl(quit_envelope(id));
            return 0;
        }

        // Validate
        std::string validated_action;
        if (!validate_request(req, validated_action, error)) {
            const std::string code =
                req.value("api_version", std::string()) == kApiVersion
                    ? "INVALID_REQUEST"
                    : "UNSUPPORTED_API_VERSION";

            Json rsp = make_error(req, req.value("action", std::string()), code, error, false);
            write_jsonl(make_envelope(id, req, rsp, default_json));
            continue;
        }

        // Dispatch
        Json rsp = dispatcher.dispatch(req);
        write_jsonl(make_envelope(id, req, rsp, default_json));
    }

    return 0;
}

} // namespace xdebug
