#pragma once

#include <string>

namespace xdebug_core {

struct AiResponse {
    bool ok;
    std::string request_id;
    std::string action;
    std::string summary;
    std::string result;
    std::string error;

    AiResponse();
};

AiResponse make_ai_error(const std::string& action, const std::string& error);

} // namespace xdebug_core
