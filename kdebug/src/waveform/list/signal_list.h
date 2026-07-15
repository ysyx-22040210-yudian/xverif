#pragma once
#include <string>
#include <vector>

namespace kdebug_waveform {

struct SignalList {
    std::string name;
    std::vector<std::string> signals;
};

} // namespace kdebug_waveform
