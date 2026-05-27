#include "api/request_parser.h"
#include "api/response.h"

namespace xdebug {

bool parse_request_text(const std::string& text, Json& request, std::string& error) {
    try {
        request = Json::parse(text);
    } catch (const std::exception& e) {
        error = e.what();
        return false;
    }
    if (!request.is_object()) {
        error = "request must be a JSON object";
        return false;
    }
    return true;
}

bool validate_request(const Json& request, std::string& action, std::string& error) {
    if (!request.contains("api_version") || !request["api_version"].is_string()) {
        error = "api_version is required";
        return false;
    }
    if (request["api_version"].get<std::string>() != kApiVersion) {
        error = "expected xdebug.v1";
        return false;
    }
    if (!request.contains("action") || !request["action"].is_string()) {
        error = "action is required";
        return false;
    }
    action = request["action"].get<std::string>();
    if (action.empty()) {
        error = "action is required";
        return false;
    }
    for (const char* field : {"target", "args", "limits", "output"}) {
        if (request.contains(field) && !request[field].is_object()) {
            error = std::string(field) + " must be an object";
            return false;
        }
    }
    return true;
}

} // namespace xdebug
