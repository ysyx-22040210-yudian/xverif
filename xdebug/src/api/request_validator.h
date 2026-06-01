#pragma once

#include "api/action_spec.h"
#include "api/request_envelope.h"

#include <string>

namespace xdebug {

struct ValidationResult {
    bool ok = true;
    std::string code;
    std::string message;
};

class RequestValidator {
public:
    ValidationResult validate(const RequestEnvelope& request, const ActionSpec& spec) const;
};

} // namespace xdebug

