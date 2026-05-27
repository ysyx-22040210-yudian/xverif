#pragma once

#include "api/json_types.h"
#include "backend/engine_adapter.h"
#include "combined/active_trace_service.h"
#include "session/session_store.h"

#include <string>

namespace xdebug {

class Dispatcher {
public:
    explicit Dispatcher(const std::string& executable_dir);
    Json dispatch(const Json& request);

private:
    Json handle_session(const Json& request, const std::string& action);
    Json handle_batch(const Json& request);
    Json forward_action(const Json& request, EngineKind kind);
    Json resolve_target(const Json& request) const;
    bool supports_action(EngineKind kind, const std::string& action) const;
    std::string mode_for_target(const Json& target) const;

    EngineAdapter adapter_;
    ActiveTraceService active_trace_;
    SessionStore sessions_;
};

} // namespace xdebug
