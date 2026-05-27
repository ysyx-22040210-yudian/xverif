#include "api/dispatcher.h"
#include "api/request_parser.h"
#include "api/response.h"

#include <fstream>
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
    std::string input;
    if (argc == 1 || (argc == 2 && std::string(argv[1]) == "-")) {
        input = read_stream(std::cin);
    } else if (argc == 2) {
        std::ifstream file(argv[1]);
        if (!file) {
            xdebug::Json request = xdebug::Json::object();
            std::cout << xdebug::make_error(request, "", "INVALID_INPUT",
                                             "failed to open JSON request file").dump(2) << "\n";
            return 1;
        }
        input = read_stream(file);
    } else {
        xdebug::Json request = xdebug::Json::object();
        std::cout << xdebug::make_error(request, "", "JSON_ONLY",
                                         "usage: xdebug [request.json|-]").dump(2) << "\n";
        return 1;
    }

    xdebug::Json request;
    std::string error;
    if (!xdebug::parse_request_text(input, request, error)) {
        std::cout << xdebug::make_error(xdebug::Json::object(), "", "INVALID_JSON", error).dump(2) << "\n";
        return 1;
    }
    std::string action;
    if (!xdebug::validate_request(request, action, error)) {
        const std::string code = request.value("api_version", std::string()) == xdebug::kApiVersion
            ? "INVALID_REQUEST" : "UNSUPPORTED_API_VERSION";
        std::cout << xdebug::make_error(request, request.value("action", std::string()),
                                         code, error, false).dump(2) << "\n";
        return 1;
    }

    xdebug::Dispatcher dispatcher(executable_dir());
    xdebug::Json response = dispatcher.dispatch(request);
    std::cout << response.dump(2) << "\n";
    return response.value("ok", false) ? 0 : 1;
}
