#pragma once

#include "api/json_types.h"

#include <string>
#include <vector>

namespace xdebug {

struct SessionRecord {
    std::string id;
    std::string mode;
    std::string daidir;
    std::string fsdb;
};

class SessionStore {
public:
    SessionStore();

    bool get(const std::string& id, SessionRecord& record) const;
    bool put(const SessionRecord& record);
    bool remove(const std::string& id);
    std::vector<SessionRecord> list() const;

private:
    std::string home_;
    std::string path_;
    bool ensure_home() const;
    Json read_all() const;
    bool write_all(const Json& sessions) const;
};

Json session_record_json(const SessionRecord& record);

} // namespace xdebug
