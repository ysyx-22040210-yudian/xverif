#pragma once

#include <string>

#include "transport/endpoint.h"

namespace xdebug_core {

struct CommandResult {
    bool ok;
    std::string payload;
    std::string status;
    std::string message;

    CommandResult() : ok(false) {}
};

class DaemonClient {
public:
    virtual ~DaemonClient() {}
    virtual bool ping(const Endpoint& endpoint) = 0;
    virtual CommandResult send(const Endpoint& endpoint, const std::string& command) = 0;
};

} // namespace xdebug_core
