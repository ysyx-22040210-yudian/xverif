#include "api/dispatcher.h"
#include "api/help_text.h"
#include "api/request_parser.h"
#include "api/response.h"
#include "api/xout_renderer.h"
#include "logging/action_log.h"

#include <fstream>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <unistd.h>

namespace {

std::string read_stream(std::istream& input) {
    std::ostringstream text;
    text << input.rdbuf();
    return text.str();
}

enum class OutputFormat { Xout, Json };

struct CliOptions {
    OutputFormat format = OutputFormat::Xout;
    std::string input_arg;
};

bool env_wants_json() {
    const char* value = std::getenv("XVERIF_OUTPUT");
    return value != nullptr && std::string(value) == "json";
}

bool request_wants_json(const xdebug::Json& request) {
    if (!request.contains("output") || !request["output"].is_object()) return false;
    if (!request["output"].contains("format") || !request["output"]["format"].is_string()) return false;
    return request["output"]["format"].get<std::string>() == "json";
}

void print_response(const xdebug::Json& response, OutputFormat format) {
    if (format == OutputFormat::Json) {
        std::cout << response.dump(2) << "\n";
    } else {
        std::cout << xdebug::render_xout_response(response);
    }
}

std::string executable_dir() {
    char path[4096] = {};
    ssize_t length = readlink("/proc/self/exe", path, sizeof(path) - 1);
    if (length <= 0) return ".";
    std::string full(path, static_cast<size_t>(length));
    size_t slash = full.rfind('/');
    return slash == std::string::npos ? "." : full.substr(0, slash);
}

} // namespace

int main(int argc, char** argv) {
    if (argc == 2) {
        std::string arg(argv[1]);
        if (arg == "-h" || arg == "-help") {
            std::cout << xdebug::help_text(executable_dir());
            return 0;
        }
    }

    CliOptions options;
    options.format = env_wants_json() ? OutputFormat::Json : OutputFormat::Xout;
    for (int i = 1; i < argc; ++i) {
        std::string arg(argv[i]);
        if (arg == "--json") {
            options.format = OutputFormat::Json;
        } else if (arg == "--text" || arg == "--xout") {
            options.format = OutputFormat::Xout;
        } else if (options.input_arg.empty()) {
            options.input_arg = arg;
        } else {
            xdebug::Json request = xdebug::Json::object();
            xdebug::Json response = xdebug::make_error(request, "", "JSON_ONLY",
                                                       "usage: xdebug [--json|--text] [request.json|-]");
            print_response(response, options.format);
            return 1;
        }
    }

    std::string input;
    if (options.input_arg.empty() || options.input_arg == "-") {
        input = read_stream(std::cin);
    } else {
        std::ifstream file(options.input_arg);
        if (!file) {
            xdebug::Json request = xdebug::Json::object();
            xdebug::Json response = xdebug::make_error(request, "", "INVALID_INPUT",
                                                       "failed to open JSON request file");
            print_response(response, options.format);
            return 1;
        }
        input = read_stream(file);
    }

    xdebug::Json request;
    std::string error;
    if (!xdebug::parse_request_text(input, request, error)) {
        xdebug::Json response = xdebug::make_error(xdebug::Json::object(), "", "INVALID_JSON", error);
        xdebug_core::log_action_event("public", "xdebug", "adhoc", "", "parse_failed", false, 0,
                                      {{"error", response["error"]}});
        print_response(response, options.format);
        return 1;
    }
    if (request_wants_json(request)) options.format = OutputFormat::Json;
    std::string action;
    if (!xdebug::validate_request(request, action, error)) {
        const std::string code = request.value("api_version", std::string()) == xdebug::kApiVersion
            ? "INVALID_REQUEST" : "UNSUPPORTED_API_VERSION";
        xdebug::Json response = xdebug::make_error(request, request.value("action", std::string()),
                                                   code, error, false);
        xdebug_core::log_action_event("public", "xdebug", "adhoc", request.value("action", std::string()),
                                      "validate_failed", false, 0,
                                      {{"request", xdebug_core::sanitize_for_log(request)}, {"error", response["error"]}});
        print_response(response, options.format);
        return 1;
    }

    xdebug::Dispatcher dispatcher(executable_dir());
    xdebug::Json response = dispatcher.dispatch(request);
    print_response(response, options.format);
    return response.value("ok", false) ? 0 : 1;
}
