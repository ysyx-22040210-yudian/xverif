#pragma once

#include "action_support.h"

#include <string>

namespace kdebug_waveform {

struct WaveformActionContext {
    const Json& req;
    const std::string& action;
    const Json& args;
    const Json& limits;
    const std::string& sid;
    const SessionInfo& info;
    long long elapsed_ms;
    int max_rows;
};

} // namespace kdebug_waveform
