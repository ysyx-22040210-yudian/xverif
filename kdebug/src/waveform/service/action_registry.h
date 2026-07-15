#pragma once

#include "action_handler.h"

#include <memory>
#include <string>
#include <unordered_map>

namespace kdebug_waveform {

class WaveformActionRegistry {
public:
    void add(std::unique_ptr<WaveformActionHandler> handler);
    const WaveformActionHandler* find(const std::string& action) const;

private:
    std::unordered_map<std::string, std::unique_ptr<WaveformActionHandler> > handlers_;
};

const WaveformActionRegistry& default_waveform_action_registry();

} // namespace kdebug_waveform
