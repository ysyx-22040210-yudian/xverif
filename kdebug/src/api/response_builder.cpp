#include "api/response_builder.h"
#include "api/response.h"

namespace kdebug {

Json ResponseBuilder::success(const RequestEnvelope& request, const ActionSpec& spec, const ActionResult& result) const {
    if (result.envelope.is_object()) return result.envelope;
    Json response = make_response(request.raw, spec.name, result.ok);
    response["summary"] = result.summary;
    response["data"] = result.data;
    response["warnings"] = result.warnings;
    response["meta"] = result.meta.is_object() ? result.meta : Json::object();
    if (!response["meta"].contains("truncated")) response["meta"]["truncated"] = false;
    if (!result.ok && !result.error.is_null()) response["error"] = result.error;
    if (!spec.response_schema.empty()) response["schema_version"] = spec.response_schema;
    return response;
}

Json ResponseBuilder::error(const RequestEnvelope& request,
                            const std::string& action,
                            const std::string& code,
                            const std::string& message,
                            bool recoverable) const {
    Json response = make_error(request.raw, action, code, message, recoverable);
    response["schema_version"] = "kdebug.error.v1";
    return response;
}

} // namespace kdebug
