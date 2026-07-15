#pragma once

#include "api/json_types.h"

namespace kdebug {

struct ActionResult {
    bool ok = true;
    Json envelope = nullptr;
    Json summary = Json::object();
    Json data = Json::object();
    Json warnings = Json::array();
    Json meta = Json::object();
    Json error = nullptr;
};

} // namespace kdebug
