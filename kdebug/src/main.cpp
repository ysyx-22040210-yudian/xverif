#include "api/dispatcher.h"
#include "api/help_text.h"
#include "api/request_parser.h"
#include "api/response.h"
#include "api/stdio_loop.h"
#include "api/kout_renderer.h"
#include "logging/action_log.h"
#include "process/process_runner.h"

#include <deque>
#include <fstream>
#include <cstdlib>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {

std::string read_stream(std::istream& input) {
    std::ostringstream text;
    text << input.rdbuf();
    return text.str();
}

enum class OutputFormat { Kout, Json };

struct CliOptions {
    OutputFormat format = OutputFormat::Kout;
    std::string input_arg;
};

struct ShortcutParseResult {
    bool matched = false;
    bool ok = false;
    kdebug::Json request = kdebug::Json::object();
    std::string error;
};

std::string executable_dir();

bool is_shortcut_command(const std::string& arg) {
    static const char* commands[] = {
        "action", "actions", "schema",
        "session-open", "session-list", "session-close", "session-doctor", "session-kill", "session-gc",
        "scope-list", "value-at", "value-batch", "trace-driver", "trace-graph",
        "source-context", "active-driver", "active-driver-chain"
    };
    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); ++i) {
        if (arg == commands[i]) return true;
    }
    return false;
}

bool take_value(int argc, char** argv, int& i, std::string& value, std::string& error) {
    if (i + 1 >= argc) {
        error = std::string("missing value for ") + argv[i];
        return false;
    }
    value = argv[++i];
    return true;
}

kdebug::Json parse_scalar_value(const std::string& value) {
    if (value == "true") return true;
    if (value == "false") return false;
    if (value == "null") return nullptr;
    if (!value.empty() && (value[0] == '{' || value[0] == '[')) {
        try {
            return kdebug::Json::parse(value);
        } catch (...) {
            return value;
        }
    }
    char* end = nullptr;
    long long integer = std::strtoll(value.c_str(), &end, 10);
    if (end && *end == '\0') return integer;
    char* fend = nullptr;
    double real = std::strtod(value.c_str(), &fend);
    if (fend && *fend == '\0' && value.find('.') != std::string::npos) return real;
    return value;
}

kdebug::Json split_csv(const std::string& text) {
    kdebug::Json out = kdebug::Json::array();
    std::string item;
    std::istringstream in(text);
    while (std::getline(in, item, ',')) {
        if (!item.empty()) out.push_back(item);
    }
    return out;
}

void set_nested_arg(kdebug::Json& root, const std::string& dotted_key, const kdebug::Json& value) {
    size_t dot = dotted_key.find('.');
    if (dot == std::string::npos) {
        root[dotted_key] = value;
        return;
    }
    std::string head = dotted_key.substr(0, dot);
    std::string tail = dotted_key.substr(dot + 1);
    if (!root.contains(head) || !root[head].is_object()) root[head] = kdebug::Json::object();
    set_nested_arg(root[head], tail, value);
}

bool apply_key_value(kdebug::Json& object, const std::string& item, std::string& error) {
    size_t eq = item.find('=');
    if (eq == std::string::npos || eq == 0) {
        error = "expected key=value, got: " + item;
        return false;
    }
    set_nested_arg(object, item.substr(0, eq), parse_scalar_value(item.substr(eq + 1)));
    return true;
}

void print_shortcut_help() {
    std::cout
        << "kdebug parameter shortcuts\n"
        << "Usage:\n"
        << "  kdebug actions [--json]\n"
        << "  kdebug schema --action <name> [--kind request|response] [--json]\n"
        << "  kdebug session-open --name <id> [--daidir simv.daidir] [--fsdb waves.fsdb]\n"
        << "  kdebug session-list [--json]\n"
        << "  kdebug session-close --session <id>\n"
        << "  kdebug scope-list --fsdb <waves.fsdb>|--session <id> [--path top] [--max-rows N]\n"
        << "  kdebug value-at --fsdb <waves.fsdb>|--session <id> --signal <sig> --time <time> [--format hex]\n"
        << "  kdebug value-batch --fsdb <waves.fsdb>|--session <id> --signal <sig> [--signal <sig> ...] --time <time>\n"
        << "  kdebug trace-driver --daidir <simv.daidir>|--session <id> --signal <sig> [--include-source]\n"
        << "  kdebug active-driver --session <id>|--daidir <simv.daidir> --fsdb <waves.fsdb> --signal <sig> --time <time>\n"
        << "  kdebug action <action> [--session id] [--daidir path] [--fsdb path] [--arg key=value] [--target key=value]\n"
        << "\n"
        << "JSON request files and stdin remain supported: kdebug --json request.json or kdebug --json -\n";
}

bool env_wants_json() {
    const char* value = std::getenv("KVERIF_OUTPUT");
    return value != nullptr && std::string(value) == "json";
}

bool request_wants_json(const kdebug::Json& request) {
    if (!request.contains("output") || !request["output"].is_object()) return false;
    if (!request["output"].contains("format") || !request["output"]["format"].is_string()) return false;
    return request["output"]["format"].get<std::string>() == "json";
}

void print_response(const kdebug::Json& response, OutputFormat format) {
    if (format == OutputFormat::Json) {
        std::cout << response.dump(2) << "\n";
    } else {
        std::cout << kdebug::render_kout_response(response);
    }
}

ShortcutParseResult parse_shortcut(int argc, char** argv, OutputFormat& format) {
    ShortcutParseResult result;
    if (argc < 2) return result;
    int command_index = 1;
    while (command_index < argc) {
        std::string opt(argv[command_index]);
        if (opt == "--json") {
            format = OutputFormat::Json;
            ++command_index;
        } else if (opt == "--text" || opt == "--kout") {
            format = OutputFormat::Kout;
            ++command_index;
        } else {
            break;
        }
    }
    if (command_index >= argc) return result;
    std::string command(argv[command_index]);
    if (!is_shortcut_command(command)) return result;
    result.matched = true;

    for (int i = command_index + 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "-h" || arg == "--help") {
            result.error = "__HELP__";
            return result;
        }
    }

    std::string action = command;
    if (command == "session-open") action = "session.open";
    else if (command == "session-list") action = "session.list";
    else if (command == "session-close") action = "session.close";
    else if (command == "session-doctor") action = "session.doctor";
    else if (command == "session-kill") action = "session.kill";
    else if (command == "session-gc") action = "session.gc";
    else if (command == "scope-list") action = "scope.list";
    else if (command == "value-at") action = "value.at";
    else if (command == "value-batch") action = "value.batch_at";
    else if (command == "trace-driver") action = "trace.driver";
    else if (command == "trace-graph") action = "trace.graph";
    else if (command == "source-context") action = "source.context";
    else if (command == "active-driver") action = "trace.active_driver";
    else if (command == "active-driver-chain") action = "trace.active_driver_chain";

    int start = command_index + 1;
    if (command == "action") {
        if (argc <= command_index + 1 || std::string(argv[command_index + 1]).find("--") == 0) {
            result.error = "action shortcut requires an action name";
            return result;
        }
        action = argv[command_index + 1];
        start = command_index + 2;
    }

    kdebug::Json request = kdebug::Json::object();
    request["api_version"] = kdebug::kApiVersion;
    request["action"] = action;
    request["target"] = kdebug::Json::object();
    request["args"] = kdebug::Json::object();
    request["limits"] = kdebug::Json::object();
    request["output"] = kdebug::Json::object();

    kdebug::Json& target = request["target"];
    kdebug::Json& args = request["args"];
    kdebug::Json& limits = request["limits"];
    kdebug::Json& output = request["output"];

    for (int i = start; i < argc; ++i) {
        std::string arg(argv[i]);
        std::string value;
        if (arg == "--json") {
            format = OutputFormat::Json;
            output["format"] = "json";
        } else if (arg == "--text" || arg == "--kout") {
            format = OutputFormat::Kout;
        } else if (arg == "--session" || arg == "--session-id") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            target["session_id"] = value;
            args["session_id"] = value;
        } else if (arg == "--name") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["name"] = value;
        } else if (arg == "--daidir") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            target["daidir"] = value;
        } else if (arg == "--fsdb") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            target["fsdb"] = value;
        } else if (arg == "--signal") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (action == "value.batch_at") {
                if (!args.contains("signals") || !args["signals"].is_array()) args["signals"] = kdebug::Json::array();
                args["signals"].push_back(value);
            } else {
                args["signal"] = value;
            }
        } else if (arg == "--signals") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["signals"] = split_csv(value);
        } else if (arg == "--time" || arg == "--at") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (action == "trace.active_driver" || action == "trace.active_driver_chain") args["requested_time"] = value;
            else args["time"] = value;
        } else if (arg == "--requested-time") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["requested_time"] = value;
        } else if (arg == "--format" || arg == "--radix") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["format"] = value;
            args["radix"] = value;
        } else if (arg == "--path") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["path"] = value;
        } else if (arg == "--scope") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["scope"] = value;
            if (action == "scope.list") args["path"] = value;
        } else if (arg == "--kind") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["kind"] = value;
        } else if (arg == "--action") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["action"] = value;
        } else if (arg == "--transport") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["transport"] = value;
        } else if (arg == "--host") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["host"] = value;
        } else if (arg == "--bind-host") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["bind_host"] = value;
        } else if (arg == "--port") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            args["port"] = parse_scalar_value(value);
        } else if (arg == "--include-source") {
            args["include_source"] = true;
        } else if (arg == "--include-trace") {
            args["include_trace"] = true;
        } else if (arg == "--include-control") {
            args["include_control"] = true;
        } else if (arg == "--include-raw") {
            args["include_raw"] = true;
        } else if (arg == "--verbosity") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            output["verbosity"] = value;
        } else if (arg == "--max-rows") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            limits["max_rows"] = parse_scalar_value(value);
        } else if (arg == "--max-results" || arg == "--max-items") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            limits["max_results"] = parse_scalar_value(value);
            limits["max_items"] = parse_scalar_value(value);
        } else if (arg == "--max-depth") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            limits["max_depth"] = parse_scalar_value(value);
            args["max_depth"] = parse_scalar_value(value);
        } else if (arg == "--timeout-ms") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            limits["timeout_ms"] = parse_scalar_value(value);
        } else if (arg == "--arg") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (!apply_key_value(args, value, result.error)) return result;
        } else if (arg == "--target") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (!apply_key_value(target, value, result.error)) return result;
        } else if (arg == "--limit") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (!apply_key_value(limits, value, result.error)) return result;
        } else if (arg == "--output") {
            if (!take_value(argc, argv, i, value, result.error)) return result;
            if (!apply_key_value(output, value, result.error)) return result;
        } else {
            result.error = "unknown shortcut argument: " + arg;
            return result;
        }
    }

    if (target.empty()) request.erase("target");
    if (args.empty()) request.erase("args");
    if (limits.empty()) request.erase("limits");
    if (output.empty()) request.erase("output");
    result.request = request;
    result.ok = true;
    return result;
}

int dispatch_request(const kdebug::Json& request, OutputFormat format) {
    kdebug::Dispatcher dispatcher(executable_dir());
    kdebug::Json response = dispatcher.dispatch(request);
    print_response(response, format);
    return response.value("ok", false) ? 0 : 1;
}

std::string executable_dir() {
    char path[4096] = {};
    ssize_t length = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (length <= 0) return ".";
    std::string full(path, static_cast<size_t>(length));
    size_t slash = full.rfind('/');
    return slash == std::string::npos ? "." : full.substr(0, slash);
}

std::string parent_dir(const std::string& path) {
    size_t slash = path.rfind('/');
    if (slash == std::string::npos) return ".";
    if (slash == 0) return "/";
    return path.substr(0, slash);
}

bool file_exists(const std::string& path) {
    struct stat st;
    return stat(path.c_str(), &st) == 0;
}

bool ensure_dir(const std::string& path) {
    if (path.empty()) return false;
    if (mkdir(path.c_str(), 0700) == 0) return true;
    struct stat st;
    return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}

bool ensure_dir_recursive(const std::string& path) {
    if (path.empty()) return false;
    std::string cur;
    size_t i = 0;
    if (path[0] == '/') {
        cur = "/";
        i = 1;
    }
    while (i <= path.size()) {
        size_t slash = path.find('/', i);
        std::string part = path.substr(i, slash == std::string::npos ? std::string::npos : slash - i);
        if (!part.empty()) {
            if (cur.size() > 1) cur += "/";
            cur += part;
            if (!ensure_dir(cur)) return false;
        }
        if (slash == std::string::npos) break;
        i = slash + 1;
    }
    return true;
}

long long file_size(const std::string& path) {
    struct stat st;
    if (stat(path.c_str(), &st) != 0) return -1;
    return static_cast<long long>(st.st_size);
}

std::string kdebug_home_from_session(const std::string& session_id) {
    std::string public_dir = kdebug_core::public_session_dir(session_id);
    return parent_dir(parent_dir(public_dir));
}

std::string component_session_dir(const std::string& component, const std::string& session_id) {
    return parent_dir(parent_dir(kdebug_core::component_log_path(component, session_id, "lifecycle")));
}

kdebug::Json log_paths_for_session(const std::string& session_id) {
    kdebug::Json paths;
    paths["public_session"] = kdebug_core::public_session_dir(session_id);
    paths["public_actions"] = kdebug_core::public_action_log_path(session_id);
    paths["public_stdio"] = kdebug_core::public_stdio_log_path(session_id);
    paths["engine_session"] = component_session_dir("engine", session_id);
    paths["engine_lifecycle"] = kdebug_core::component_log_path("engine", session_id, "lifecycle");
    paths["engine_transport"] = kdebug_core::component_log_path("engine", session_id, "transport");
    paths["engine_crash_marker"] = kdebug_core::component_log_path("engine", session_id, "crash_marker");
    paths["engine_log_health"] = parent_dir(paths["engine_lifecycle"].get<std::string>()) + "/log_health.ndjson";
    paths["public_log_health"] = parent_dir(paths["public_actions"].get<std::string>()) + "/log_health.ndjson";
    return paths;
}

kdebug::Json log_doctor_response(const std::string& session_id) {
    kdebug::Json response;
    response["ok"] = true;
    response["action"] = "log.doctor";
    response["summary"] = {{"session_id", session_id}};
    kdebug::Json paths = log_paths_for_session(session_id);
    kdebug::Json rows = kdebug::Json::array();
    for (auto it = paths.begin(); it != paths.end(); ++it) {
        std::string path = it.value().get<std::string>();
        rows.push_back({{"name", it.key()}, {"path", path}, {"exists", file_exists(path)}, {"bytes", file_size(path)}});
    }
    response["data"] = {{"logs", rows}};
    return response;
}

void print_log_tail_file(const std::string& name, const std::string& path, int lines) {
    std::ifstream in(path.c_str());
    if (!in) return;
    std::deque<std::string> tail;
    std::string line;
    while (std::getline(in, line)) {
        tail.push_back(line);
        while (static_cast<int>(tail.size()) > lines) tail.pop_front();
    }
    if (tail.empty()) return;
    std::cout << "== " << name << " " << path << " ==\n";
    for (const auto& item : tail) std::cout << item << "\n";
}

int run_log_tail(const std::string& session_id, int lines) {
    kdebug::Json paths = log_paths_for_session(session_id);
    for (const char* name : {"public_actions", "public_stdio", "engine_lifecycle", "engine_transport", "engine_crash_marker"}) {
        print_log_tail_file(name, paths[name].get<std::string>(), lines);
    }
    return 0;
}

int run_log_bundle(const std::string& session_id, const std::string& out_path) {
    std::string home = kdebug_home_from_session(session_id);
    kdebug::Json paths = log_paths_for_session(session_id);
    std::vector<std::string> rels;
    for (const char* name : {"public_session", "engine_session"}) {
        std::string path = paths[name].get<std::string>();
        if (file_exists(path) && path.compare(0, home.size() + 1, home + "/") == 0) {
            rels.push_back(path.substr(home.size() + 1));
        }
    }
    if (rels.empty()) {
        std::cerr << "no log directories found for session: " << session_id << "\n";
        return 1;
    }
    kdebug::ProcessRequest req;
    req.executable = "/bin/tar";
    req.argv.push_back("-czf");
    req.argv.push_back(out_path);
    req.argv.push_back("-C");
    req.argv.push_back(home);
    for (const auto& rel : rels) req.argv.push_back(rel);
    req.timeout_ms = 30000;
    kdebug::ProcessResult result = kdebug::ProcessRunner().run(req);
    if (result.exit_code != 0) {
        std::cerr << result.stderr_text;
        return result.exit_code == 0 ? 1 : result.exit_code;
    }
    std::cout << out_path << "\n";
    return 0;
}

bool write_redacted_log_copy(const std::string& source, const std::string& dest) {
    std::ifstream in(source.c_str());
    if (!in) return false;
    if (!ensure_dir_recursive(parent_dir(dest))) return false;
    std::ofstream out(dest.c_str(), std::ios::trunc);
    if (!out) return false;
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) {
            out << "\n";
            continue;
        }
        try {
            kdebug_core::Json j = kdebug_core::Json::parse(line);
            out << kdebug_core::sanitize_for_log(j).dump() << "\n";
        } catch (...) {
            out << line << "\n";
        }
    }
    return true;
}

int run_redacted_log_bundle(const std::string& session_id, const std::string& out_path) {
    std::string old_mode = std::getenv("KDEBUG_LOG_PATH_MODE") ? std::getenv("KDEBUG_LOG_PATH_MODE") : "";
    setenv("KDEBUG_LOG_PATH_MODE", "hash", 1);
    std::string tmp = "/tmp/kdebug-log-bundle-" + std::to_string(getpid());
    ensure_dir_recursive(tmp);
    kdebug::Json paths = log_paths_for_session(session_id);
    for (const char* name : {"public_actions", "public_stdio", "engine_lifecycle", "engine_transport",
                             "engine_crash_marker", "engine_log_health", "public_log_health"}) {
        std::string source = paths[name].get<std::string>();
        if (!file_exists(source)) continue;
        write_redacted_log_copy(source, tmp + "/" + std::string(name) + ".ndjson");
    }
    if (!old_mode.empty()) setenv("KDEBUG_LOG_PATH_MODE", old_mode.c_str(), 1);
    else unsetenv("KDEBUG_LOG_PATH_MODE");

    kdebug::ProcessRequest req;
    req.executable = "/bin/tar";
    req.argv.push_back("-czf");
    req.argv.push_back(out_path);
    req.argv.push_back("-C");
    req.argv.push_back(tmp);
    req.argv.push_back(".");
    req.timeout_ms = 30000;
    kdebug::ProcessResult result = kdebug::ProcessRunner().run(req);
    if (result.exit_code != 0) {
        std::cerr << result.stderr_text;
        return result.exit_code == 0 ? 1 : result.exit_code;
    }
    std::cout << out_path << "\n";
    return 0;
}

int run_log_command(int argc, char** argv, OutputFormat format) {
    if (argc < 3) {
        std::cerr << "usage: kdebug log tail|doctor|bundle --session <id> [--lines N] [--out file]\n";
        return 1;
    }
    std::string sub(argv[2]);
    std::string session_id;
    std::string out_path;
    int lines = 40;
    bool redact = false;
    for (int i = 3; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--session" && i + 1 < argc) session_id = argv[++i];
        else if (arg == "--out" && i + 1 < argc) out_path = argv[++i];
        else if (arg == "--lines" && i + 1 < argc) lines = std::atoi(argv[++i]);
        else if (arg == "--redact") redact = true;
        else if (arg == "--json") format = OutputFormat::Json;
        else {
            std::cerr << "unknown log argument: " << arg << "\n";
            return 1;
        }
    }
    if (session_id.empty()) {
        std::cerr << "missing --session\n";
        return 1;
    }
    if (sub == "doctor") {
        print_response(log_doctor_response(session_id), format);
        return 0;
    }
    if (sub == "tail") return run_log_tail(session_id, lines <= 0 ? 40 : lines);
    if (sub == "bundle") {
        if (out_path.empty()) {
            std::cerr << "missing --out\n";
            return 1;
        }
        if (redact) return run_redacted_log_bundle(session_id, out_path);
        return run_log_bundle(session_id, out_path);
    }
    std::cerr << "unknown log subcommand: " << sub << "\n";
    return 1;
}

} // namespace

int main(int argc, char** argv) {
    if (argc == 2) {
        std::string arg(argv[1]);
        if (arg == "-h" || arg == "-help") {
            std::cout << kdebug::help_text(executable_dir());
            return 0;
        }
    }

    CliOptions options;
    options.format = env_wants_json() ? OutputFormat::Json : OutputFormat::Kout;
    if (argc >= 2 && std::string(argv[1]) == "log") {
        return run_log_command(argc, argv, options.format);
    }
    ShortcutParseResult shortcut = parse_shortcut(argc, argv, options.format);
    if (shortcut.matched) {
        if (shortcut.error == "__HELP__") {
            print_shortcut_help();
            return 0;
        }
        if (!shortcut.ok) {
            kdebug::Json response = kdebug::make_error(kdebug::Json::object(), "", "INVALID_CLI", shortcut.error);
            print_response(response, options.format);
            return 1;
        }
        return dispatch_request(shortcut.request, options.format);
    }
    bool stdio_loop = false;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--stdio-loop") {
            stdio_loop = true;
        } else if (arg == "--json") {
            options.format = OutputFormat::Json;
        } else if (arg == "--text" || arg == "--kout") {
            options.format = OutputFormat::Kout;
        } else if (options.input_arg.empty()) {
            options.input_arg = arg;
        } else {
            kdebug::Json request = kdebug::Json::object();
            kdebug::Json response = kdebug::make_error(request, "", "JSON_ONLY",
                                                       "usage: kdebug [--json|--text] [request.json|-]");
            print_response(response, options.format);
            return 1;
        }
    }

    if (stdio_loop) {
        return kdebug::run_stdio_loop(executable_dir(),
                                      options.format == OutputFormat::Json);
    }

    std::string input;
    if (options.input_arg.empty() || options.input_arg == "-") {
        input = read_stream(std::cin);
    } else {
        std::ifstream file(options.input_arg);
        if (!file) {
            kdebug::Json request = kdebug::Json::object();
            kdebug::Json response = kdebug::make_error(request, "", "INVALID_INPUT",
                                                       "failed to open JSON request file");
            print_response(response, options.format);
            return 1;
        }
        input = read_stream(file);
    }

    kdebug::Json request;
    std::string error;
    if (!kdebug::parse_request_text(input, request, error)) {
        kdebug::Json response = kdebug::make_error(kdebug::Json::object(), "", "INVALID_JSON", error);
        kdebug_core::log_action_event("public", "kdebug", "adhoc", "", "parse_failed", false, 0,
                                      {{"error", response["error"]}});
        print_response(response, options.format);
        return 1;
    }
    if (request_wants_json(request)) options.format = OutputFormat::Json;
    std::string action;
    if (!kdebug::validate_request(request, action, error)) {
        const std::string code = request.value("api_version", std::string()) == kdebug::kApiVersion
            ? "INVALID_REQUEST" : "UNSUPPORTED_API_VERSION";
        kdebug::Json response = kdebug::make_error(request, request.value("action", std::string()),
                                                   code, error, false);
        kdebug_core::log_action_event("public", "kdebug", "adhoc", request.value("action", std::string()),
                                      "validate_failed", false, 0,
                                      {{"request", kdebug_core::sanitize_for_log(request)}, {"error", response["error"]}});
        print_response(response, options.format);
        return 1;
    }

    kdebug::Dispatcher dispatcher(executable_dir());
    kdebug::Json response = dispatcher.dispatch(request);
    print_response(response, options.format);
    return response.value("ok", false) ? 0 : 1;
}
