#pragma once

#include <string>
#include <vector>

#include "session/session_types.h"

namespace kdebug_core {

class SessionRegistry {
public:
    virtual ~SessionRegistry() {}
    virtual bool load_all(std::vector<SessionInfo>& sessions) = 0;
    virtual bool upsert(const SessionInfo& session) = 0;
    virtual bool remove(const std::string& session_id) = 0;
    virtual bool get(const std::string& session_id, SessionInfo& session) = 0;
};

} // namespace kdebug_core
