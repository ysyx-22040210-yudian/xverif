#include "command_parser.h"

#include <cstring>
#include <sstream>

namespace xdebug_waveform {

CommandLine parse_command_line(const char* raw) {
    CommandLine cl;

    if (!raw || !*raw) return cl;

    std::istringstream iss(raw);
    std::string token;

    // First token is always the verb
    if (!(iss >> token)) return cl;
    cl.verb = token;

    // Remaining tokens are positional arguments or flags
    while (iss >> token) {
        if (token.empty()) continue;

        // Check for key=value pattern (e.g. "addr=0x1000", "id=5")
        size_t eq = token.find('=');
        if (eq != std::string::npos && eq > 0 && eq < token.size() - 1) {
            std::string key = token.substr(0, eq);
            std::string value = token.substr(eq + 1);
            cl.flags[key] = value;
            continue;
        }

        // Known value-less flags: "json", "last"
        // These appear as standalone tokens without arguments
        if (token == "json" || token == "last") {
            cl.flags[token] = "";
            continue;
        }

        // Everything else is a positional argument
        cl.positional.push_back(token);
    }

    return cl;
}

} // namespace xdebug_waveform
