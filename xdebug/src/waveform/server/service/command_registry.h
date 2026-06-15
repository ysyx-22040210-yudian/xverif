#pragma once

#include "command_parser.h"

#include <functional>
#include <memory>
#include <string>
#include <unordered_map>

namespace xdebug_waveform {

// A command handler receives the parsed command line and the client fd.
// It should send the response directly to the client and return true on success.
using CommandHandler = std::function<bool(int client_fd, const CommandLine& cl)>;

// Lightweight registry mapping command verbs to handlers.
// Provides the same dispatch pattern used by WaveformActionRegistry on the service side.
class CommandRegistry {
public:
    void add(const std::string& verb, CommandHandler handler) {
        handlers_[verb] = std::move(handler);
    }

    const CommandHandler* find(const std::string& verb) const {
        auto it = handlers_.find(verb);
        return it != handlers_.end() ? &it->second : nullptr;
    }

    bool dispatch(int client_fd, const CommandLine& cl) const {
        const auto* handler = find(cl.verb);
        if (!handler) return false;
        return (*handler)(client_fd, cl);
    }

private:
    std::unordered_map<std::string, CommandHandler> handlers_;
};

} // namespace xdebug_waveform
