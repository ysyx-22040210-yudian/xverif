#include "runtime/work_dir.h"

#include <cstdlib>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>

namespace kdebug {

namespace {

bool ensure_dir(const std::string& path) {
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

} // namespace

std::string runtime_work_dir(const std::string& component) {
    const char* home = std::getenv("HOME");
    return std::string(home ? home : "/tmp") + "/.kdebug/work/" + component;
}

bool ensure_runtime_work_dir(const std::string& path) {
    const std::string work = path.substr(0, path.find_last_of('/'));
    const std::string root = work.substr(0, work.find_last_of('/'));
    return ensure_dir(root) && ensure_dir(work) && ensure_dir(path);
}

ScopedRuntimeWorkDir::ScopedRuntimeWorkDir(const std::string& component)
    : path_(runtime_work_dir(component)), changed_(false) {
    char cwd[PATH_MAX] = {};
    if (!getcwd(cwd, sizeof(cwd)) || !ensure_runtime_work_dir(path_)) return;
    previous_ = cwd;
    changed_ = chdir(path_.c_str()) == 0;
}

ScopedRuntimeWorkDir::~ScopedRuntimeWorkDir() {
    if (changed_) chdir(previous_.c_str());
}

bool ScopedRuntimeWorkDir::ok() const {
    return changed_;
}

const std::string& ScopedRuntimeWorkDir::path() const {
    return path_;
}

} // namespace kdebug
