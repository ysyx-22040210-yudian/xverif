#include "session/session_catalog.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

int main() {
    char temp[] = "/tmp/kdebug-session-catalog.XXXXXX";
    char* home = mkdtemp(temp);
    assert(home != nullptr);
    assert(setenv("HOME", home, 1) == 0);

    const std::string kdebug_home = std::string(home) + "/.kdebug";
    const std::string engine_home = kdebug_home + "/engine";
    assert(mkdir(kdebug_home.c_str(), 0700) == 0);
    assert(mkdir(engine_home.c_str(), 0700) == 0);

    std::ofstream canonical((engine_home + "/registry.json").c_str());
    canonical << R"JSON({
  "version": 1,
  "sessions": [
    {
      "session_id": "wave",
      "fsdb_file": "/tmp/waves.fsdb",
      "socket_path": "/tmp/wave.sock"
    },
    {
      "session_id": "design",
      "dbdir_path": "/tmp/simv.daidir",
      "socket_path": "/tmp/design.sock"
    },
    {
      "session_id": "combined",
      "dbdir_path": "/tmp/simv.daidir",
      "fsdb_file": "/tmp/waves.fsdb"
    }
  ]
})JSON";
    canonical.close();

    // A stale legacy frontend registry must not shadow canonical engine state.
    std::ofstream legacy((kdebug_home + "/registry.json").c_str());
    legacy << R"JSON([{"id":"stale","mode":"waveform","fsdb":"/tmp/stale.fsdb"}])JSON";
    legacy.close();

    kdebug::SessionCatalog catalog;
    std::vector<kdebug::SessionRecord> records = catalog.list();
    assert(records.size() == 3);

    kdebug::SessionRecord record;
    assert(catalog.get("wave", record));
    assert(record.mode == "waveform");
    assert(record.fsdb == "/tmp/waves.fsdb");
    assert(record.socket_path == "/tmp/wave.sock");

    assert(catalog.get("design", record));
    assert(record.mode == "design");
    assert(record.daidir == "/tmp/simv.daidir");

    assert(catalog.get("combined", record));
    assert(record.mode == "combined");
    assert(!catalog.get("stale", record));

    // Corrupt registry content must behave like an empty registry rather than
    // surfacing partial data or crashing target resolution.
    std::ofstream corrupt((engine_home + "/registry.json").c_str());
    corrupt << R"JSON({"sessions": [)JSON";
    corrupt.close();
    assert(catalog.list().empty());
    assert(!catalog.get("wave", record));

    // Invalid records are skipped individually. A valid record after malformed
    // or incomplete entries must still be discoverable.
    std::ofstream mixed((engine_home + "/registry.json").c_str());
    mixed << R"JSON({
  "sessions": [
    "not-an-object",
    {"session_id": "", "fsdb_file": "/tmp/missing-id.fsdb"},
    {"session_id": "missing-resource"},
    {"session_id": "legacy-design-file", "design_file": "/tmp/legacy.daidir"},
    {
      "session_id": "file-transport",
      "fsdb_file": "/tmp/file.fsdb",
      "transport": "file",
      "file_dir": "/tmp/kdebug-file-transport"
    },
    {
      "session_id": "tcp-transport",
      "dbdir_path": "/tmp/tcp.daidir",
      "transport": "tcp",
      "host": "launcher",
      "bind_host": "127.0.0.1",
      "port": 43123,
      "server_host": "worker"
    }
  ]
})JSON";
    mixed.close();
    records = catalog.list();
    assert(records.size() == 3);
    assert(!catalog.get("missing-resource", record));

    assert(catalog.get("legacy-design-file", record));
    assert(record.mode == "design");
    assert(record.daidir == "/tmp/legacy.daidir");
    assert(record.transport == "uds");

    assert(catalog.get("file-transport", record));
    assert(record.mode == "waveform");
    assert(record.transport == "file");
    assert(record.file_dir == "/tmp/kdebug-file-transport");

    assert(catalog.get("tcp-transport", record));
    assert(record.mode == "design");
    assert(record.transport == "tcp");
    assert(record.host == "launcher");
    assert(record.bind_host == "127.0.0.1");
    assert(record.port == 43123);
    assert(record.server_host == "worker");
    return 0;
}
