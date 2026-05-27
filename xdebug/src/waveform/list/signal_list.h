#pragma once
#include <string>
#include <vector>

namespace xdebug_waveform {

struct SignalList {
    std::string name;
    std::vector<std::string> signals;
};

} // namespace xdebug_waveform
