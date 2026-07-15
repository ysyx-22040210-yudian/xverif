#pragma once

#include <string>

namespace kdebug {

/// Run the kdebug stdio loop: read JSONL requests from stdin, write JSONL
/// responses to stdout.  Exits when `stdio.quit` is received or stdin closes.
///
/// @param executable_dir  path to the directory containing the kdebug binary
///                        (used to locate internal engines).
/// @param default_json    when true, responses default to `payload_format=json`;
///                        otherwise they default to `payload_format=kout`.
int run_stdio_loop(const std::string& executable_dir, bool default_json);

} // namespace kdebug
