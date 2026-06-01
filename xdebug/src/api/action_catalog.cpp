#include "api/action_catalog.h"
#include "api/action_registry_init.h"
#include "api/response.h"

namespace xdebug {

namespace {

Json string_array(const std::set<std::string>& values) {
    Json array = Json::array();
    for (const auto& value : values) array.push_back(value);
    return array;
}

std::set<std::string> actions_for_category(const std::string& category) {
    std::set<std::string> out;
    std::vector<ActionSpec> specs = default_action_registry().list_specs(false);
    for (size_t i = 0; i < specs.size(); ++i) {
        if (specs[i].category == category) out.insert(specs[i].name);
    }
    return out;
}

Json action_name_array(bool include_removed) {
    Json out = Json::array();
    std::vector<ActionSpec> specs = default_action_registry().list_specs(include_removed);
    for (size_t i = 0; i < specs.size(); ++i) {
        if (!include_removed && specs[i].status == ActionStatus::Removed) continue;
        if (include_removed && specs[i].status != ActionStatus::Removed) continue;
        out.push_back(specs[i].name);
    }
    return out;
}

} // namespace

const std::set<std::string>& design_actions() {
    static const std::set<std::string> actions = actions_for_category("design");
    return actions;
}

const std::set<std::string>& waveform_actions() {
    static const std::set<std::string> actions = actions_for_category("waveform");
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
        }},
        {"contract", {
            {"source", "ActionRegistry"},
            {"schema_root", "xdebug/schemas/v1"},
            {"action_count", default_action_registry().list_specs(false).size()}
        }}
    };
    return response;
}

Json catalog_actions_response(const Json& request) {
    Json response = make_response(request, "actions");
    Json descriptors = default_action_registry().list_descriptors(false);
    Json implemented = action_name_array(false);
    Json removed = action_name_array(true);
    response["summary"] = {
        {"action_count", implemented.size()},
        {"removed_count", removed.size()}
    };
    response["data"] = {
        {"implemented", implemented},
        {"actions", descriptors},
        {"removed", removed},
        {"modes", {
            {"design", string_array(design_actions())},
            {"waveform", string_array(waveform_actions())},
            {"combined", Json::array({"trace.active_driver"})},
            {"builtin", Json::array({"actions", "schema", "batch"})},
            {"session", Json::array({"session.open", "session.ensure", "session.list", "session.doctor",
                                      "session.kill", "session.close", "session.gc"})}
        }}
    };
    return response;
}

} // namespace xdebug
