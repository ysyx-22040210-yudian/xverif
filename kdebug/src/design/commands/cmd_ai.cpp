#include "cmd_ai.h"

#include "../service/action_support.h"

#include <cstdio>
#include <iostream>
#include <string>

namespace kdebug_design {

namespace {

int print_json_and_return(const json& payload) {
    printf("%s\n", payload.dump(2).c_str());
    return payload.value("ok", true) ? 0 : 1;
}

} // namespace

int cmd_ai(int argc, char** argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s ai <query|schema|actions>\n", argv[0]);
        return 1;
    }
    std::string subcmd = argv[2];
    if (subcmd == "schema") {
        printf("%s\n", schema_payload().dump(2).c_str());
        return 0;
    }
    if (subcmd == "actions") {
        printf("%s\n", actions_payload().dump(2).c_str());
        return 0;
    }
    if (subcmd != "query") {
        json req = {{"api_version", API_VERSION}, {"action", ""}};
        return print_json_and_return(error_response(req, "", "UNKNOWN_ACTION", "unknown ai subcommand: " + subcmd));
    }
    std::string input;
    if (argc >= 5 && std::string(argv[3]) == "--json") input = argv[4];
    else if (argc >= 4 && std::string(argv[3]) == "-") input = read_stream(std::cin);
    else if (argc >= 4) {
        input = read_file(argv[3]);
        if (input.empty()) {
            json req = {{"api_version", API_VERSION}, {"action", ""}};
            return print_json_and_return(error_response(req, "", "INVALID_REQUEST", "failed to read request file"));
        }
    } else {
        json req = {{"api_version", API_VERSION}, {"action", ""}};
        return print_json_and_return(error_response(req, "", "INVALID_REQUEST", "ai query requires a file, -, or --json"));
    }
    try {
        return print_json_and_return(handle_request(json::parse(input)));
    } catch (const std::exception& e) {
        json req = {{"api_version", API_VERSION}, {"action", ""}};
        return print_json_and_return(error_response(req, "", "INVALID_REQUEST", e.what()));
    }
}

} // namespace kdebug_design
