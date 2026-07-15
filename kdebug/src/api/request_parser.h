#pragma once

#include "api/json_types.h"

#include <string>

namespace kdebug {

bool parse_request_text(const std::string& text, Json& request, std::string& error);
bool validate_request(const Json& request, std::string& action, std::string& error);

} // namespace kdebug
