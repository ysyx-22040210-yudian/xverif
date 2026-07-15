#include "api/help_text.h"

#include <fstream>
#include <sstream>

namespace kdebug {

namespace {

std::string read_file(const std::string& path) {
    std::ifstream file(path.c_str());
    if (!file) return std::string();
    std::ostringstream text;
    text << file.rdbuf();
    return text.str();
}

const char* fallback_help_text() {
    return
        "kdebug - unified kdebug parameter and protocol interface\n"
        "=======================================================\n\n"
        "Usage\n"
        "-----\n"
        "  kdebug -h\n"
        "  kdebug -help\n"
        "      Print this human-readable help and exit with status 0.\n\n"
        "  kdebug -\n"
        "      Read one JSON request from stdin and print one KOUT text response.\n\n"
        "  kdebug request.json\n"
        "      Read one JSON request file and print one KOUT text response.\n\n"
        "  kdebug --json -\n"
        "      Print the original JSON response for scripts and schema tests.\n\n"
        "  kdebug actions [--json]\n"
        "      List available actions without writing a JSON request.\n\n"
        "  kdebug schema --action <name> [--kind request|response] [--json]\n"
        "      Print one action schema.\n\n"
        "  kdebug value-at --fsdb <waves.fsdb>|--session <id> --signal <sig> --time <time>\n"
        "      Query one signal value.\n\n"
        "  kdebug trace-driver --daidir <simv.daidir>|--session <id> --signal <sig>\n"
        "      Query static RTL driver evidence from the elaboration database.\n\n"
        "  kdebug active-driver --daidir <simv.daidir> --fsdb <waves.fsdb> --signal <sig> --time <time>\n"
        "      Join waveform time with design causality and locate the active driver.\n\n"
        "Request / output contract\n"
        "-------------------------\n"
        "  Human users should prefer parameter-style commands. JSON fields\n"
        "  api_version/action/target/args/limits/output remain the stable protocol\n"
        "  for scripts, MCP, stdio-loop, schema tests, and reproducible bug reports.\n"
        "  Default output is KOUT structured text; use --json or output.format=json for JSON.\n\n"
        "Common actions\n"
        "--------------\n"
        "  actions, schema, session.open, session.doctor, trace.driver,\n"
        "  trace.graph, trace.path, rc.generate, value.at, value.batch_at, event.export,\n"
        "  verify.conditions, apb.query, axi.query, axi.analysis, axi.export,\n"
        "  trace.active_driver.\n\n"
        "Action choice guidance\n"
        "----------------------\n"
        "  Use signal.statistics for active/high cycles, signal.changes for\n"
        "  transition timelines, window.verify for holds, and event.find for\n"
        "  first/last occurrence queries. event.find also accepts inline\n"
        "  args.expr + args.clk + args.signals for one-off event queries.\n"
        "  signal.changes compact output omits\n"
        "  rows unless include_rows/include_all_changes is set.\n\n"
        "  session.open always creates a new session. Same-name live sessions\n"
        "  return SESSION_ID_EXISTS; stale sessions return SESSION_STALE.\n"
        "  Close or gc stale sessions explicitly before opening again.\n"
        "  Session names must match ^[A-Za-z][A-Za-z0-9_]{0,63}$.\n\n"
        "Session transport\n"
        "-----------------\n"
        "  Default transport is UDS. Set KDEBUG_TRANSPORT=uds|tcp|file to\n"
        "  choose the default for newly opened sessions. Use TCP only when UDS sockets are not\n"
        "  reachable, such as container/namespace boundaries or explicitly\n"
        "  requested remote/cross-process daemon access. For local TCP use\n"
        "  session.open args.transport=tcp, bind_host=127.0.0.1, port=0.\n"
        "  port:0 lets the daemon choose an available port; host is the\n"
        "  client-reachable endpoint address for remote/container cases.\n"
        "  Use args.transport=file when the client cannot connect to a compute\n"
        "  node TCP port; requests and responses are exchanged under the\n"
        "  backend session transport directory in ~/.kdebug. File transport v2\n"
        "  state directories are:\n"
        "      requests/    client-published pending requests\n"
        "      claims/      worker-claimed running requests\n"
        "      responses/   unread responses\n"
        "      done/        archived request/claim/response history\n"
        "      failed/      client_timeout / expired / stale_claim / invalid_request\n"
        "      tmp/         atomic write temp files\n"
        "      heartbeat/   worker liveness files\n"
        "  History is kept by default. File request timeout defaults to 300s; set\n"
        "  KDEBUG_FILE_TRANSPORT_TIMEOUT_MS to adjust it.\n\n"
        "Output control\n"
        "--------------\n"
        "  output.verbosity=compact/full/debug; use include_* switches and limits\n"
        "  such as max_items, max_examples, limits.max_rows when details are needed.\n\n"
        "Logs\n"
        "----\n"
        "  Public logs live under ~/.kdebug/sessions/<session_prefix>_<hash>/logs/actions.ndjson.\n"
        "  Stdio-loop protocol logs live beside actions.ndjson as stdio.ndjson.\n"
        "  Engine lifecycle/transport/crash logs live under ~/.kdebug/engine/sessions/.\n"
        "  MCP direct/LSF logs live under ~/.kverif/mcp/sessions/<alias>/.\n"
        "  Helpers: kdebug log doctor|tail|bundle --session <id>.\n\n"
        "Docs\n"
        "----\n"
        "  kdebug/README.md\n"
        "  skill/SKILL.md\n"
        "  skill/references/kdebug/overview.md\n"
        "  skill/references/kdebug/json-api.md\n";
}

} // namespace

std::string help_text(const std::string& executable_dir) {
    std::string text = read_file(executable_dir + "/help.txt");
    if (!text.empty()) return text;

    size_t slash = executable_dir.rfind('/');
    if (slash != std::string::npos) {
        text = read_file(executable_dir.substr(0, slash) + "/kdebug/help.txt");
        if (!text.empty()) return text;
    }

    return fallback_help_text();
}

} // namespace kdebug
