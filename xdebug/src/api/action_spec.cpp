#include "api/action_spec.h"

namespace xdebug {

std::string to_string(ActionStatus status) {
    switch (status) {
    case ActionStatus::Experimental: return "experimental";
    case ActionStatus::Stable: return "stable";
    case ActionStatus::Deprecated: return "deprecated";
    case ActionStatus::Removed: return "removed";
    }
    return "experimental";
}

std::string to_string(ResourceRequirement resource) {
    switch (resource) {
    case ResourceRequirement::None: return "none";
    case ResourceRequirement::Design: return "design";
    case ResourceRequirement::Waveform: return "waveform";
    case ResourceRequirement::Combined: return "combined";
    case ResourceRequirement::Any: return "any";
    case ResourceRequirement::Session: return "session";
    }
    return "none";
}

ActionStatus action_status_from_string(const std::string& value) {
    if (value == "stable") return ActionStatus::Stable;
    if (value == "deprecated") return ActionStatus::Deprecated;
    if (value == "removed") return ActionStatus::Removed;
    return ActionStatus::Experimental;
}

ResourceRequirement resource_requirement_from_string(const std::string& value) {
    if (value == "design") return ResourceRequirement::Design;
    if (value == "waveform") return ResourceRequirement::Waveform;
    if (value == "combined") return ResourceRequirement::Combined;
    if (value == "any") return ResourceRequirement::Any;
    if (value == "session") return ResourceRequirement::Session;
    return ResourceRequirement::None;
}

Json action_spec_descriptor(const ActionSpec& spec) {
    Json descriptor = {
        {"name", spec.name},
        {"category", spec.category},
        {"status", to_string(spec.status)},
        {"requires", to_string(spec.resource)}
    };
    if (!spec.request_schema.empty()) descriptor["request_schema"] = spec.request_schema;
    if (!spec.response_schema.empty()) descriptor["response_schema"] = spec.response_schema;
    if (!spec.handler_kind.empty()) descriptor["handler_kind"] = spec.handler_kind;
    if (!spec.request_examples.empty()) descriptor["request_examples"] = spec.request_examples;
    if (!spec.response_examples.empty()) descriptor["response_examples"] = spec.response_examples;
    return descriptor;
}

} // namespace xdebug

