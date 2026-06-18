#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_design {

using Json = nlohmann::ordered_json;

// Unified action handler interface.

class EngineActionHandler {
public:
    virtual ~EngineActionHandler() = default;

    virtual const char* action_name() const = 0;
    virtual bool needs_design() const = 0;
    virtual bool needs_waveform() const = 0;
    virtual Json run(const Json& request) const = 0;

    // XOUT text rendering.  Default recursively renders summary + data tree.
    // Subclasses may override additively:
    //   std::string render_xout(const Json& r) const override {
    //       std::string base = EngineActionHandler::render_xout(r);
    //       // ... append custom sections ...
    //       return base;
    //   }
    virtual std::string render_xout(const Json& response) const;
};

} // namespace xdebug_design
