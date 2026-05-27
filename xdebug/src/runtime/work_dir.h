#pragma once

#include <string>

namespace xdebug {

std::string runtime_work_dir(const std::string& component);
bool ensure_runtime_work_dir(const std::string& path);

class ScopedRuntimeWorkDir {
public:
    explicit ScopedRuntimeWorkDir(const std::string& component);
    ~ScopedRuntimeWorkDir();

    bool ok() const;
    const std::string& path() const;

private:
    std::string path_;
    std::string previous_;
    bool changed_;
};

} // namespace xdebug
