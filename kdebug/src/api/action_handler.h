#pragma once

#include "api/action_context.h"
#include "api/action_result.h"

#include <string>

namespace kdebug {

class ActionHandler {
public:
    virtual ~ActionHandler() {}
    virtual std::string name() const = 0;
    virtual ActionResult run(const ActionContext& ctx) = 0;
};

} // namespace kdebug

