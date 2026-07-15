#include "ai/ai_response.h"

namespace kdebug_core {

AiResponse::AiResponse()
    : ok(false) {}

AiResponse make_ai_error(const std::string& action, const std::string& error) {
    AiResponse response;
    response.ok = false;
    response.action = action;
    response.error = error;
    return response;
}

} // namespace kdebug_core
