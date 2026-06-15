#include "process_runner.h"

#include <cerrno>
#include <cstring>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

namespace xdebug {

ProcessResult ProcessRunner::run(const ProcessRequest& request) const {
    ProcessResult result;

    Pipe stdin_pipe;
    Pipe stdout_pipe;
    if (!stdin_pipe.valid() || !stdout_pipe.valid()) {
        result.exit_code = -1;
        result.stderr_text = std::string("failed to create pipe: ") + std::strerror(errno);
        return result;
    }

    pid_t pid = fork();
    if (pid < 0) {
        result.exit_code = -1;
        result.stderr_text = std::string("failed to fork: ") + std::strerror(errno);
        return result;
    }

    if (pid == 0) {
        // Child process
        dup2(stdin_pipe.read_end.get(), STDIN_FILENO);
        dup2(stdout_pipe.write_end.get(), STDOUT_FILENO);

        // Close all pipe ends in child (dup'd ones remain as stdin/stdout)
        stdin_pipe.read_end.reset();
        stdin_pipe.write_end.reset();
        stdout_pipe.read_end.reset();
        stdout_pipe.write_end.reset();

        if (!request.working_dir.empty()) {
            if (chdir(request.working_dir.c_str()) != 0) _exit(126);
        }

        // Build argv array
        std::vector<const char*> cargv;
        cargv.push_back(request.executable.c_str());
        for (const auto& a : request.argv) {
            cargv.push_back(a.c_str());
        }
        cargv.push_back(nullptr);

        execv(request.executable.c_str(), const_cast<char* const*>(cargv.data()));
        _exit(127);
    }

    // Parent process
    stdin_pipe.read_end.reset();   // Close read end (child reads from it)
    stdout_pipe.write_end.reset(); // Close write end (child writes to it)

    // Write stdin
    if (!request.stdin_text.empty()) {
        const char* data = request.stdin_text.data();
        size_t remaining = request.stdin_text.size();
        while (remaining > 0) {
            ssize_t n = write(stdin_pipe.write_end.get(), data, remaining);
            if (n <= 0) break;
            data += n;
            remaining -= static_cast<size_t>(n);
        }
    }
    stdin_pipe.write_end.reset(); // Close write end to signal EOF to child

    // Read stdout
    char buffer[4096];
    for (;;) {
        ssize_t n = read(stdout_pipe.read_end.get(), buffer, sizeof(buffer));
        if (n <= 0) break;
        result.stdout_text.append(buffer, static_cast<size_t>(n));
    }
    stdout_pipe.read_end.reset();

    // Wait for child
    int status = 0;
    waitpid(pid, &status, 0);

    if (WIFEXITED(status)) {
        result.exit_code = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        result.exit_code = -1;
        result.stderr_text = "child killed by signal " + std::to_string(WTERMSIG(status));
    }

    return result;
}

} // namespace xdebug
