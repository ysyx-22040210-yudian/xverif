#pragma once

#include "fd.h"

#include <chrono>
#include <string>
#include <vector>

namespace xdebug {

struct ProcessResult {
    int exit_code = -1;
    std::string stdout_text;
    std::string stderr_text;
    bool timed_out = false;
    bool exited() const { return !timed_out; }
};

struct ProcessRequest {
    std::string executable;
    std::vector<std::string> argv;
    std::string stdin_text;
    std::string working_dir;
};

// Runs a child process, pipes stdin to it, captures stdout.
// Encapsulates the fork/exec/pipe/waitpid lifecycle in RAII style.
class ProcessRunner {
public:
    ProcessResult run(const ProcessRequest& request) const;
};

} // namespace xdebug
