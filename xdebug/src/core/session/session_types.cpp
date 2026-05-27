#include "session/session_types.h"

namespace xdebug_core {

Fingerprint::Fingerprint()
    : mtime(0),
      size(0),
      dev(0),
      inode(0) {}

DatabaseRef::DatabaseRef()
    : kind(DatabaseKind::Fsdb) {}

SessionInfo::SessionInfo()
    : transport("uds"),
      port(0),
      database_kind(DatabaseKind::Fsdb),
      server_pid(0),
      created_at(0),
      last_active(0) {}

const char* database_kind_name(DatabaseKind kind) {
    switch (kind) {
    case DatabaseKind::Fsdb:
        return "fsdb";
    case DatabaseKind::Daidir:
        return "daidir";
    }
    return "unknown";
}

} // namespace xdebug_core
