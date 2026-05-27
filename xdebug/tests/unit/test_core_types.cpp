#include "ai/ai_response.h"
#include "common/path_utils.h"
#include "protocol/core_protocol.h"
#include "session/session_types.h"

#include <cassert>
#include <string>

int main() {
    xdebug_core::ToolConfig config = xdebug_core::make_tool_config("xdebug", ".xdebug", "xdebug", "1.0");
    assert(config.tool_name == "xdebug");
    assert(config.home_dir_name == ".xdebug");

    xdebug_core::SessionInfo session;
    session.database_kind = xdebug_core::DatabaseKind::Daidir;
    assert(std::string(xdebug_core::database_kind_name(session.database_kind)) == "daidir");

    xdebug_core::AiResponse error = xdebug_core::make_ai_error("trace.driver", "failed");
    assert(!error.ok);
    assert(error.action == "trace.driver");

    assert(std::string(xdebug_core::CMD_PING) == "PING");
    assert(xdebug_core::registry_path(config).find(".xdebug/registry.json") != std::string::npos);
    assert(xdebug_core::socket_path(config, "case_a").find(".xdebug/sessions/s_") != std::string::npos);
    return 0;
}
