#include "ai/ai_response.h"
#include "common/path_utils.h"
#include "protocol/core_protocol.h"
#include "session/session_types.h"

#include <cassert>
#include <cstdlib>
#include <string>

int main() {
    kdebug_core::ToolConfig config = kdebug_core::make_tool_config("kdebug", ".kdebug", "kdebug", "1.0");
    assert(config.tool_name == "kdebug");
    assert(config.home_dir_name == ".kdebug");

    kdebug_core::SessionInfo session;
    session.dbdir_path = "/tmp/simv.daidir";
    assert(session.database_kind() == kdebug_core::DatabaseKind::Daidir);
    assert(std::string(kdebug_core::database_kind_name(session.database_kind())) == "daidir");

    session.dbdir_path.clear();
    session.fsdb_file = "/tmp/waves.fsdb";
    assert(session.database_kind() == kdebug_core::DatabaseKind::Fsdb);
    assert(std::string(kdebug_core::database_kind_name(session.database_kind())) == "fsdb");

    session.dbdir_path = "/tmp/simv.daidir";
    assert(session.database_kind() == kdebug_core::DatabaseKind::Combined);
    assert(std::string(kdebug_core::database_kind_name(session.database_kind())) == "combined");

    kdebug_core::AiResponse error = kdebug_core::make_ai_error("trace.driver", "failed");
    assert(!error.ok);
    assert(error.action == "trace.driver");

    assert(std::string(kdebug_core::CMD_PING) == "PING");
    assert(kdebug_core::registry_path(config).find(".kdebug/registry.json") != std::string::npos);
    assert(kdebug_core::is_valid_session_name("A"));
    assert(kdebug_core::is_valid_session_name("case_1"));
    assert(kdebug_core::is_valid_session_name("Case_0123456789_abc"));
    assert(kdebug_core::is_valid_session_name(std::string("A") + std::string(63, 'x')));
    assert(!kdebug_core::is_valid_session_name(""));
    assert(!kdebug_core::is_valid_session_name("1case"));
    assert(!kdebug_core::is_valid_session_name("_case"));
    assert(!kdebug_core::is_valid_session_name("case-a"));
    assert(!kdebug_core::is_valid_session_name("case.a"));
    assert(!kdebug_core::is_valid_session_name("case a"));
    assert(!kdebug_core::is_valid_session_name(std::string("A") + std::string(64, 'x')));
    const std::string dir_name = kdebug_core::session_dir_name("abcdefghijklmnopXYZ");
    assert(dir_name.find("abcdefghijklmnop_") == 0);
    assert(dir_name.size() == 16 + 1 + 16);
    assert(dir_name == kdebug_core::session_dir_name("abcdefghijklmnopXYZ"));
    assert(dir_name != kdebug_core::session_dir_name("abcdefghijklmnopXYA"));
    assert(kdebug_core::session_dir_name("bad/name").find("bad_name_") == 0);
    assert(kdebug_core::socket_path(config, "case_a").find(".kdebug/sessions/case_a_") != std::string::npos);
    const char* old_home = std::getenv("HOME");
    const std::string saved_home = old_home ? old_home : "";
    setenv("HOME",
           "/tmp/pytest-of-user/pytest-999/test_a_very_long_kdebug_session_home_path/home",
           1);
    const std::string short_socket = kdebug_core::socket_path(config, "case_a");
    assert(short_socket.find("/tmp/kdebug-") == 0);
    assert(short_socket.size() < 104);
    if (old_home) setenv("HOME", saved_home.c_str(), 1);
    else unsetenv("HOME");

    assert(kdebug_core::resource_content_matches(100, 4096, 100, 4096));
    assert(!kdebug_core::resource_identity_differs(10, 20, 10, 20));
    assert(kdebug_core::resource_identity_differs(10, 20, 11, 20));
    assert(kdebug_core::resource_identity_differs(10, 20, 10, 21));
    assert(!kdebug_core::resource_content_matches(100, 4096, 101, 4096));
    assert(!kdebug_core::resource_content_matches(100, 4096, 100, 8192));
    return 0;
}
