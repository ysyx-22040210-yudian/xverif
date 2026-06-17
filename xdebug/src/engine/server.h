#pragma once

namespace xdebug_design {

// Server main function - called when --server flag is passed
// argv: [exe, --server, session_id, ...design_args...]
int server_main(int argc, char** argv);

} // namespace xdebug_design
