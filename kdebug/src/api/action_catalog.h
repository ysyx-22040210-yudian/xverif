#pragma once

#include "api/json_types.h"

#include <set>
#include <string>

namespace kdebug {

const std::set<std::string>& design_actions();
const std::set<std::string>& waveform_actions();
Json catalog_schema_response(const Json& request);
Json catalog_actions_response(const Json& request);

} // namespace kdebug
