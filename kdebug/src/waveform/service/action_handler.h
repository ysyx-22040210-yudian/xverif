#pragma once

#include "action_context.h"

namespace kdebug_waveform {

class WaveformActionHandler {
public:
    virtual ~WaveformActionHandler() {}

    virtual const char* action_name() const = 0;
    virtual int run(const WaveformActionContext& ctx) const = 0;
};

} // namespace kdebug_waveform
