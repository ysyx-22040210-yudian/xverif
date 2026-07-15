#pragma once

#include "api/json_types.h"

#include <string>

namespace kdebug {

class EngineAdapter {
public:
    explicit EngineAdapter(const std::string& executable_dir);

    // Invoke the unified kdebug-engine subprocess.
    bool invoke(const Json& kdebug_request,
                Json& response,
                std::string& error) const;

private:
    std::string engine_path() const;
    std::string engine_workdir() const;
    std::string executable_dir_;
};

} // namespace kdebug
