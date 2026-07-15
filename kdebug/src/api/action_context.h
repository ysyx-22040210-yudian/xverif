#pragma once

#include "api/action_spec.h"
#include "api/json_types.h"

namespace kdebug {

struct ResourceContext {
    Json target = Json::object();
    bool design = false;
    bool waveform = false;
    bool session = false;
};

struct ActionContext {
    Json request = Json::object();
    ActionSpec spec;
    ResourceContext resources;
};

} // namespace kdebug

