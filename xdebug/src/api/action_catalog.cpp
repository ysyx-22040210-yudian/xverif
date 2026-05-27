#include "api/action_catalog.h"
#include "api/response.h"

namespace xdebug {

namespace {

Json string_array(const std::set<std::string>& values) {
    Json array = Json::array();
    for (const auto& value : values) array.push_back(value);
    return array;
}

} // namespace

const std::set<std::string>& design_actions() {
    static const std::set<std::string> actions = {
        "trace.driver", "trace.load", "trace.query",
        "signal.resolve", "signal.canonicalize",
        "trace.expand", "trace.graph", "trace.path", "trace.explain",
        "control.explain", "source.context", "expr.normalize",
        "procedural.assignment", "sequential.update", "fsm.explain",
        "counter.explain", "port.trace", "instance.map", "interface.resolve"
    };
    return actions;
}

const std::set<std::string>& waveform_actions() {
    static const std::set<std::string> actions = {
        "cursor.set", "cursor.get", "cursor.list", "cursor.delete", "cursor.use",
        "scope.list", "value.at", "value.batch_at",
        "list.create", "list.add", "list.delete", "list.show",
        "list.value_at", "list.validate", "list.diff",
        "apb.config.load", "apb.config.list", "apb.query", "apb.cursor",
        "axi.config.load", "axi.config.list", "axi.query", "axi.cursor", "axi.analysis",
        "event.config.load", "event.config.list", "event.find", "event.export",
        "verify.conditions", "expr.eval_at", "window.verify",
        "signal.changes", "signal.stability", "signal.trend", "signal.statistics",
        "sampled_pulse.inspect", "inspect_signal", "detect_anomaly",
        "handshake.inspect", "axi.channel_stall", "axi.outstanding_timeline",
        "axi.request_response_pair", "axi.latency_outlier", "apb.transfer_window"
    };
    return actions;
}

Json catalog_schema_response(const Json& request) {
    Json response = make_response(request, "schema");
    response["data"] = {
        {"api_version", kApiVersion},
        {"request", {
            {"required", Json::array({"api_version", "action"})},
            {"target_resources", Json::array({"daidir", "fsdb", "session_id"})},
            {"modes", Json::array({"design", "waveform", "combined"})}
        }},
        {"combined_action", {
            {"action", "trace.active_driver"},
            {"required_target", Json::array({"daidir", "fsdb"})},
            {"required_args", Json::array({"signal", "requested_time"})},
            {"optional_args", Json::array({"include_control", "include_parity"})}
        }}
    };
    return response;
}

Json catalog_actions_response(const Json& request) {
    Json implemented = Json::array({
        "schema", "actions",
        "session.open", "session.ensure", "session.list", "session.doctor",
        "session.kill", "session.close", "session.gc",
        "trace.active_driver", "batch"
    });
    for (const auto& action : design_actions()) implemented.push_back(action);
    for (const auto& action : waveform_actions()) implemented.push_back(action);
    Json response = make_response(request, "actions");
    response["data"] = {
        {"implemented", implemented},
        {"removed", Json::array({"signal.search"})},
        {"modes", {
            {"design", string_array(design_actions())},
            {"waveform", string_array(waveform_actions())},
            {"combined", "all actions plus trace.active_driver"}
        }}
    };
    return response;
}

} // namespace xdebug
