#include "api/request_validator.h"
#include "api/response.h"

namespace kdebug {

ValidationResult RequestValidator::validate(const RequestEnvelope& request, const ActionSpec& spec) const {
    ValidationResult result;
    if (request.api_version != kApiVersion) {
        result.ok = false;
        result.code = "UNSUPPORTED_API_VERSION";
        result.message = "expected kdebug.v1";
        return result;
    }
    if (request.action != spec.name) {
        result.ok = false;
        result.code = "UNKNOWN_ACTION";
        result.message = "request action does not match ActionSpec";
        return result;
    }
    for (size_t i = 0; i < spec.args.required.size(); ++i) {
        const std::string& key = spec.args.required[i];
        if (!request.args.contains(key) || request.args[key].is_null()) {
            result.ok = false;
            result.code = "MISSING_FIELD";
            result.message = "args." + key + " is required";
            return result;
        }
    }
    return result;
}

} // namespace kdebug

