#pragma once

#include "action_support.h"

namespace xdebug_waveform {

int run_session_action(const Json& req, const std::string& action, const Json& target,
                       const Json& args, long long elapsed_ms, bool& handled);
int run_protocol_action(const Json& req, const std::string& action, const Json& args,
                        const Json& limits, const std::string& sid, const SessionInfo& info,
                        long long elapsed_ms, bool& handled);

} // namespace xdebug_waveform
