#pragma once

#include "api/json_types.h"

#include <string>

namespace kdebug {

enum class EngineKind;

// Maps public kdebug JSON requests to internal engine requests.
// Responsibilities:
//   - daidir -> dbdir mapping for design engine
//   - Stripping irrelevant target fields (fsdb from design, daidir from waveform)
//   - Setting api_version to kdebug.internal.v1
class EngineRequestMapper {
public:
    // Maps a public request into the internal engine format.
    // The original request is not modified.
    Json map(EngineKind kind, const Json& request) const;
};

} // namespace kdebug
