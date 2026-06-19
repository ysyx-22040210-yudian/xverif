#include "ai/ai_response.h"
#include "common/path_utils.h"
#include "protocol/core_protocol.h"
#include "session/session_types.h"

#include <cassert>
#include <cstdlib>
#include <string>

int main() {
    xdebug_core::ToolConfig config = xdebug_core::make_tool_config("xdebug", ".xdebug", "xdebug", "1.0");
    assert(config.tool_name == "xdebug");
    assert(config.home_dir_name == ".xdebug");

    xdebug_core::SessionInfo session;
    session.dbdir_path = "/tmp/simv.daidir";
    assert(session.database_kind() == xdebug_core::DatabaseKind::Daidir);
    assert(std::string(xdebug_core::database_kind_name(session.database_kind())) == "daidir");

    session.dbdir_path.clear();
    session.fsdb_file = "/tmp/waves.fsdb";
    assert(session.database_kind() == xdebug_core::DatabaseKind::Fsdb);
    assert(std::string(xdebug_core::database_kind_name(session.database_kind())) == "fsdb");

    session.dbdir_path = "/tmp/simv.daidir";
    assert(session.database_kind() == xdebug_core::DatabaseKind::Combined);
    assert(std::string(xdebug_core::database_kind_name(session.database_kind())) == "combined");

    xdebug_core::AiResponse error = xdebug_core::make_ai_error("trace.driver", "failed");
    assert(!error.ok);
    assert(error.action == "trace.driver");

    assert(std::string(xdebug_core::CMD_PING) == "PING");
    assert(xdebug_core::registry_path(config).find(".xdebug/registry.json") != std::string::npos);
    assert(xdebug_core::is_valid_session_name("A"));
    assert(xdebug_core::is_valid_session_name("case_1"));
    assert(xdebug_core::is_valid_session_name("Case_0123456789_abc"));
    assert(xdebug_core::is_valid_session_name(std::string("A") + std::string(63, 'x')));
    assert(!xdebug_core::is_valid_session_name(""));
    assert(!xdebug_core::is_valid_session_name("1case"));
    assert(!xdebug_core::is_valid_session_name("_case"));
    assert(!xdebug_core::is_valid_session_name("case-a"));
    assert(!xdebug_core::is_valid_session_name("case.a"));
    assert(!xdebug_core::is_valid_session_name("case a"));
    assert(!xdebug_core::is_valid_session_name(std::string("A") + std::string(64, 'x')));
    const std::string dir_name = xdebug_core::session_dir_name("abcdefghijklmnopXYZ");
    assert(dir_name.find("abcdefghijklmnop_") == 0);
    assert(dir_name.size() == 16 + 1 + 16);
    assert(dir_name == xdebug_core::session_dir_name("abcdefghijklmnopXYZ"));
    assert(dir_name != xdebug_core::session_dir_name("abcdefghijklmnopXYA"));
    assert(xdebug_core::session_dir_name("bad/name").find("bad_name_") == 0);
    assert(xdebug_core::socket_path(config, "case_a").find(".xdebug/sessions/case_a_") != std::string::npos);
    const char* old_home = std::getenv("HOME");
    const std::string saved_home = old_home ? old_home : "";
    setenv("HOME",
           "/tmp/pytest-of-user/pytest-999/test_a_very_long_xdebug_session_home_path/home",
           1);
    const std::string short_socket = xdebug_core::socket_path(config, "case_a");
    assert(short_socket.find("/tmp/xdebug-") == 0);
    assert(short_socket.size() < 104);
    if (old_home) setenv("HOME", saved_home.c_str(), 1);
    else unsetenv("HOME");

    assert(xdebug_core::resource_content_matches(100, 4096, 100, 4096));
    assert(!xdebug_core::resource_identity_differs(10, 20, 10, 20));
    assert(xdebug_core::resource_identity_differs(10, 20, 11, 20));
    assert(xdebug_core::resource_identity_differs(10, 20, 10, 21));
    assert(!xdebug_core::resource_content_matches(100, 4096, 101, 4096));
    assert(!xdebug_core::resource_content_matches(100, 4096, 100, 8192));
    return 0;
}
