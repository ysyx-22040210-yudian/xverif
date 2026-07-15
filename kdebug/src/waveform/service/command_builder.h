#pragma once

#include <string>
#include <vector>

namespace kdebug_waveform {

// Lightweight builder for waveform server text-protocol commands.
// Replaces manual string concatenation like:
//   std::string(CMD_SCOPE) + " " + path + " " + (recursive ? "1" : "0") + " json"
// with:
//   CommandBuilder(CMD_SCOPE).arg(path).arg(recursive ? "1" : "0").arg("json").build()
//
// LIMITATION: Does not perform escaping/quoting of arguments.
// The current text protocol does not define an escape mechanism,
// so arguments containing spaces or special characters may produce
// ambiguous commands. This matches the existing behavior.
class CommandBuilder {
public:
    explicit CommandBuilder(const char* verb) : verb_(verb) {}
    explicit CommandBuilder(const std::string& verb) : verb_(verb) {}

    CommandBuilder& arg(const std::string& value) {
        args_.push_back(value);
        return *this;
    }

    CommandBuilder& arg(const char* value) {
        args_.push_back(value);
        return *this;
    }

    CommandBuilder& arg(bool value) {
        args_.push_back(value ? "1" : "0");
        return *this;
    }

    CommandBuilder& arg(int value) {
        args_.push_back(std::to_string(value));
        return *this;
    }

    std::string build() const {
        if (args_.empty()) return verb_;
        std::string result = verb_;
        for (const auto& a : args_) {
            result += " ";
            result += a;
        }
        return result;
    }

private:
    std::string verb_;
    std::vector<std::string> args_;
};

} // namespace kdebug_waveform
