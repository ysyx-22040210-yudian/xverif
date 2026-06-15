#pragma once

#include <string>
#include <unordered_map>
#include <vector>

namespace xdebug_waveform {

// Structured representation of a server text-protocol command line.
// For example, the raw command:
//   VALUE top.dut.sig 100ns json
// is parsed into:
//   CommandLine{
//     .verb = "VALUE",
//     .positional = {"top.dut.sig", "100ns", "json"},
//     .flags = {}
//   }
struct CommandLine {
    std::string verb;
    std::vector<std::string> positional;
    std::unordered_map<std::string, std::string> flags;

    // Convenience: true if a flag is present (value-less flag like "json", "last").
    bool has_flag(const std::string& name) const {
        return flags.find(name) != flags.end();
    }

    // Convenience: positional arg access with bounds check.
    const std::string& arg(size_t index) const {
        static const std::string empty;
        return index < positional.size() ? positional[index] : empty;
    }

    bool empty() const { return verb.empty() && positional.empty(); }
};

// Parses a raw command line string into a CommandLine.
// Supports:
//   - Space-delimited positional arguments
//   - Value-less flags: any token that is a known flag name
//   - Key-value flags: "key=value" or "key value" for known keys
//
// LIMITATION: The current text protocol uses positional arguments almost
// exclusively. The flags support is forward-looking for potential
// protocol evolution. Known flag names like "json", "last", "addr",
// "num", "id" are recognized.
//
// Does NOT change the protocol - all existing commands parse identically.
CommandLine parse_command_line(const char* raw);

} // namespace xdebug_waveform
