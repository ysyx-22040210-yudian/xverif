#include "../design/commands/cmd_ai.h"
#include "server.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using namespace xdebug_design;

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--debug") == 0) {
            setenv("XDEBUG_DESIGN_DEBUG", "1", 1);
            break;
        }
    }

    if (argc >= 2 && std::strcmp(argv[1], "--server") == 0) {
        std::vector<char*> server_argv;
        server_argv.push_back(argv[0]);
        for (int i = 2; i < argc; ++i) server_argv.push_back(argv[i]);
        server_argv.push_back(nullptr);
        return server_main(static_cast<int>(server_argv.size()) - 1, server_argv.data());
    }

    if (argc == 4 && std::strcmp(argv[1], "ai") == 0 &&
        std::strcmp(argv[2], "query") == 0 && std::strcmp(argv[3], "-") == 0) {
        return cmd_ai(argc, argv);
    }

    std::fprintf(stderr, "ERROR: xdebug internal design engine accepts JSON requests only\n");
    return 2;
}
