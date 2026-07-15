#pragma once

#include <string>

namespace kdebug_waveform {

struct ApbConfig {
    std::string name;
    std::string paddr;
    std::string pwdata;
    std::string prdata;
    std::string pwrite;
    std::string penable;
    std::string psel;
    std::string pready;
    std::string pslverr;
    std::string clk;
    std::string rst_n;
    bool posedge = true;
};

} // namespace kdebug_waveform
