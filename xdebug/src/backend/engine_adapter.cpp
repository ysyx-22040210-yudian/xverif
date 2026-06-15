#include "backend/engine_adapter.h"
#include "backend/engine_request_mapper.h"
#include "api/response.h"
#include "core/process/process_runner.h"
#include "logging/action_log.h"
#include "runtime/work_dir.h"

#include <string>

namespace xdebug {

namespace {

std::string engine_component(EngineKind kind) {
    return kind == EngineKind::Design ? "design" : "waveform";
}

std::string request_session_id_for_log(const Json& request) {
    Json target = request.value("target", Json::object());
    Json args = request.value("args", Json::object());
    auto get_str = [](const Json& obj, const char* key) -> std::string {
        auto it = obj.find(key);
        return it != obj.end() && it->is_string() ? it->get<std::string>() : std::string();
    };
    std::string sid = get_str(target, "session_id");
    if (!sid.empty()) return sid;
    sid = get_str(args, "session_id");
    if (!sid.empty()) return sid;
    sid = get_str(args, "name");
    if (!sid.empty()) return sid;
    sid = get_str(target, "name");
    return sid.empty() ? "adhoc" : sid;
}

} // namespace

EngineAdapter::EngineAdapter(const std::string& executable_dir)
    : executable_dir_(executable_dir) {}

std::string EngineAdapter::engine_path(EngineKind kind) const {
    return executable_dir_ + "/libexec/" +
           (kind == EngineKind::Design ? "xdebug-design-engine" : "xdebug-waveform-engine");
}

std::string EngineAdapter::engine_workdir(EngineKind kind) const {
    return runtime_work_dir(kind == EngineKind::Design ? "design" : "waveform");
}

bool EngineAdapter::invoke(EngineKind kind,
                           const Json& xdebug_request,
                           Json& response,
                           std::string& error) const {
    const std::string component = engine_component(kind);
    const std::string log_sid = request_session_id_for_log(xdebug_request);
    const std::string path = engine_path(kind);
    const std::string workdir = engine_workdir(kind);

    if (!ensure_runtime_work_dir(workdir)) {
        error = std::string("failed to create engine working directory: ") + workdir;
        xdebug_core::log_lifecycle_event(component, log_sid, "engine.workdir_failed", false,
                                         {{"workdir", workdir}, {"engine_path", path}});
        return false;
    }

    // Build internal request via EngineRequestMapper
    EngineRequestMapper mapper;
    Json internal_request = mapper.map(kind, xdebug_request);
    std::string stdin_text = internal_request.dump();
    stdin_text.push_back('\n');

    // Build process request
    ProcessRequest process_req;
    process_req.executable = path;
    process_req.argv = {"ai", "query", "-"};
    process_req.stdin_text = stdin_text;
    process_req.working_dir = workdir;

    xdebug_core::log_lifecycle_event(component, log_sid, "engine.spawning", true,
                                     {{"engine_path", path}, {"workdir", workdir},
                                      {"action", xdebug_request.value("action", std::string())}});

    ProcessRunner runner;
    ProcessResult result = runner.run(process_req);

    if (result.exit_code != 0 && !result.stderr_text.empty()) {
        error = result.stderr_text;
        xdebug_core::log_lifecycle_event(component, log_sid, "engine.process_failed", false,
                                         {{"exit_code", result.exit_code}, {"message", error},
                                          {"engine_path", path}});
        return false;
    }

    try {
        response = normalize_engine_response(Json::parse(result.stdout_text));
    } catch (const std::exception& e) {
        error = std::string("invalid internal engine response: ") + e.what() +
                " (exit=" + std::to_string(result.exit_code) + ")";
        Json ctx = {{"message", error}, {"output", result.stdout_text},
                    {"action", xdebug_request.value("action", std::string())},
                    {"exit_status", result.exit_code}};
        xdebug_core::log_lifecycle_event(component, log_sid, "engine.response_parse_failed", false, ctx);
        return false;
    }

    Json ctx = {{"action", xdebug_request.value("action", std::string())},
                {"ok", response.value("ok", false)},
                {"exit_status", result.exit_code}};
    xdebug_core::log_lifecycle_event(component, log_sid, "engine.completed",
                                     response.value("ok", true), ctx);
    return true;
}

} // namespace xdebug
