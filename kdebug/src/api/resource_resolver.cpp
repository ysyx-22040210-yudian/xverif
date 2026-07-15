#include "api/resource_resolver.h"

namespace kdebug {

namespace {

bool has_string(const Json& object, const char* key) {
    return object.is_object() && object.contains(key) && object[key].is_string() &&
           !object[key].get<std::string>().empty();
}

ResourceResolution resource_error(const std::string& message) {
    ResourceResolution result;
    result.ok = false;
    result.code = "RESOURCE_REQUIRED";
    result.message = message;
    return result;
}

} // namespace

ResourceResolution ResourceResolver::resolve(const RequestEnvelope& request, const ActionSpec& spec) const {
    ResourceResolution result;
    result.context.target = request.target;
    result.context.design = has_string(request.target, "daidir");
    result.context.waveform = has_string(request.target, "fsdb");
    result.context.session = has_string(request.target, "session_id");

    switch (spec.resource) {
    case ResourceRequirement::None:
        return result;
    case ResourceRequirement::Design:
        if (result.context.design || result.context.session) return result;
        return resource_error("design action requires target.daidir or a design session");
    case ResourceRequirement::Waveform:
        if (result.context.waveform || result.context.session) return result;
        return resource_error("waveform action requires target.fsdb or a waveform session");
    case ResourceRequirement::Combined:
        if ((result.context.design && result.context.waveform) || result.context.session) return result;
        return resource_error("combined action requires target.daidir and target.fsdb");
    case ResourceRequirement::Any:
        if (result.context.design || result.context.waveform || result.context.session) return result;
        return resource_error("target.daidir or target.fsdb is required");
    case ResourceRequirement::Session:
        if (result.context.session) return result;
        return resource_error("target.session_id is required");
    }
    return result;
}

} // namespace kdebug

