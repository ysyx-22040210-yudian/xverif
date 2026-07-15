#pragma once

#include <string>

namespace kdebug_core {

inline bool is_tcp_transport(const std::string& transport) {
    return transport == "tcp";
}

inline bool is_uds_transport(const std::string& transport) {
    return transport.empty() || transport == "uds";
}

} // namespace kdebug_core
