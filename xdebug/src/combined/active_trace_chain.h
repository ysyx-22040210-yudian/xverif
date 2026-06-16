#pragma once

#include "api/json_types.h"

namespace xdebug {

class ActiveTraceChainService {
public:
    Json run(const Json& request, const Json& target) const;
};

} // namespace xdebug
