#pragma once

#include "api/json_types.h"

#include <string>

namespace xdebug {

enum class EngineKind {
    Design,
    Waveform
};

class EngineAdapter {
public:
    explicit EngineAdapter(const std::string& executable_dir);

    bool invoke(EngineKind kind,
                const Json& xdebug_request,
                Json& response,
                std::string& error) const;

private:
    std::string engine_path(EngineKind kind) const;
    std::string engine_workdir(EngineKind kind) const;
    std::string executable_dir_;
};

Json engine_request(EngineKind kind, const Json& request);

} // namespace xdebug
