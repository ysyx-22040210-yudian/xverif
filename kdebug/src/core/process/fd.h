#pragma once

#include <unistd.h>

namespace kdebug {

// RAII wrapper for a POSIX file descriptor.
// Owns the fd and closes it on destruction.
class Fd {
public:
    Fd() = default;
    explicit Fd(int fd) : fd_(fd) {}
    ~Fd() { reset(); }

    Fd(const Fd&) = delete;
    Fd& operator=(const Fd&) = delete;

    Fd(Fd&& other) noexcept : fd_(other.release()) {}

    Fd& operator=(Fd&& other) noexcept {
        if (this != &other) {
            reset(other.release());
        }
        return *this;
    }

    int get() const { return fd_; }
    bool valid() const { return fd_ >= 0; }

    int release() {
        int old = fd_;
        fd_ = -1;
        return old;
    }

    void reset(int next = -1) {
        if (fd_ >= 0) {
            ::close(fd_);
        }
        fd_ = next;
    }

private:
    int fd_ = -1;
};

// RAII wrapper for a Unix pipe (pair of Fds).
class Pipe {
public:
    Pipe() {
        int fds[2] = {-1, -1};
        if (::pipe(fds) == 0) {
            read_end = Fd(fds[0]);
            write_end = Fd(fds[1]);
        }
    }

    bool valid() const { return read_end.valid() && write_end.valid(); }

    Fd read_end;
    Fd write_end;
};

} // namespace kdebug
