#pragma once

#include "api/action_context.h"
#include "api/request_envelope.h"

#include <string>

namespace kdebug {

struct ResourceResolution {
    bool ok = true;
    ResourceContext context;
    std::string code;
    std::string message;
};

class ResourceResolver {
public:
    ResourceResolution resolve(const RequestEnvelope& request, const ActionSpec& spec) const;
};

} // namespace kdebug

