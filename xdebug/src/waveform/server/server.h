#pragma once

namespace xdebug_waveform {

// Server main function - called when --server flag is passed
// argv: [exe, --server, session_id, fsdb_file]
int server_main(int argc, char** argv);

} // namespace xdebug_waveform
