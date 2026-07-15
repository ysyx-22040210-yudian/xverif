#pragma once

#include "api/action_result.h"
#include "api/action_spec.h"
#include "api/request_envelope.h"

namespace kdebug {

class ResponseBuilder {
public:
    Json success(const RequestEnvelope& request, const ActionSpec& spec, const ActionResult& result) const;
    Json error(const RequestEnvelope& request,
               const std::string& action,
               const std::string& code,
               const std::string& message,
               bool recoverable = true) const;
};

} // namespace kdebug

