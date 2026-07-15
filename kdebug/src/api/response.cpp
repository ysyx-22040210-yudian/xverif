#include "api/response.h"

namespace kdebug {

Json make_response(const Json& request, const std::string& action, bool ok) {
    Json response;
    response["api_version"] = kApiVersion;
    if (request.contains("request_id")) response["request_id"] = request["request_id"];
    response["ok"] = ok;
    response["action"] = action;
    response["tool"] = {{"name", "kdebug"}, {"version", kToolVersion}};
    response["session"] = nullptr;
    response["summary"] = Json::object();
    response["data"] = ok ? Json::object() : Json(nullptr);
    response["findings"] = Json::array();
    response["suggested_next_actions"] = Json::array();
    response["warnings"] = Json::array();
    response["error"] = nullptr;
    response["meta"] = {{"truncated", false}};
    return response;
}

Json make_error(const Json& request,
                const std::string& action,
                const std::string& code,
                const std::string& message,
                bool recoverable) {
    Json response = make_response(request, action, false);
    response["error"] = {
        {"code", code},
        {"message", message},
        {"recoverable", recoverable},
        {"candidates", Json::array()},
        {"suggested_actions", Json::array()}
    };
    return response;
}

Json normalize_engine_response(const Json& engine_response) {
    Json response = engine_response;
    response["api_version"] = kApiVersion;
    if (response.contains("tool") && response["tool"].is_object()) {
        response["tool"]["name"] = "kdebug";
        response["tool"]["version"] = kToolVersion;
    }
    if (response.contains("suggested_next_actions") &&
        response["suggested_next_actions"].is_array()) {
        for (auto& next : response["suggested_next_actions"]) {
            if (next.is_object() && next.contains("tool")) next["tool"] = "kdebug";
        }
    }
    return response;
}

} // namespace kdebug
