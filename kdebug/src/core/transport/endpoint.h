#pragma once

#include <string>

namespace kdebug_core {

struct Endpoint {
    std::string transport;
    std::string socket_path;
    std::string host;
    std::string bind_host;
    int port;
    std::string auth_token;

    Endpoint() : transport("uds"), port(0) {}
};

} // namespace kdebug_core
