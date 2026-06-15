#include "../server_internal.h"
#include "command_parser.h"

namespace xdebug_waveform {

bool handle_client(int client_fd, bool& should_quit) {
    should_quit = false;

    // Read command line
    char line[4096] = {};
    if (!read_command_line(client_fd, line, sizeof(line))) return false;

    // Trim whitespace
    char* cmd = trim_command(line);

    if (g_transport == "tcp") {
        std::string expected = std::string(CMD_AUTH) + " " + g_auth_token;
        if (strcmp(cmd, expected.c_str()) != 0) {
            const char* err = "ERROR: AUTH failed\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
            return false;
        }
        const char* ok = "OK\n";
        send_all(client_fd, ok, strlen(ok));
        memset(line, 0, sizeof(line));
        if (!read_command_line(client_fd, line, sizeof(line))) return false;
        cmd = trim_command(line);
    }

    // Handle QUIT
    if (strcmp(cmd, CMD_QUIT) == 0) {
        send_all(client_fd, END_MARKER, strlen(END_MARKER));
        should_quit = true;
        return true;
    }

    // Handle PING
    if (strcmp(cmd, CMD_PING) == 0) {
        const char* pong = "PONG\n" END_MARKER;
        send_all(client_fd, pong, strlen(pong));
        return true;
    }

    if (fsdb_changed()) {
        const char* err = ERROR_PREFIX "FSDB changed; session restart required\n" END_MARKER;
        send_all(client_fd, err, strlen(err));
        return true;
    }

    SessionRegistry registry;
    registry.touch(g_session_id, time(nullptr));

    // Parse command line into structured form for cleaner argument access
    CommandLine cl = parse_command_line(cmd);

    // Handle TIME_RESOLVE <time_spec> [allow_max]
    if (cl.verb == CMD_TIME_RESOLVE) {
        if (cl.positional.size() >= 1) {
            npiFsdbTime t = 0;
            std::string error;
            bool allow_max = cl.positional.size() >= 2 && cl.positional[1] == "allow_max";
            if (!parse_user_time(cl.positional[0].c_str(), allow_max, t, error)) {
                send_error(client_fd, error);
                return true;
            }
            Json out = resolved_time_json(cl.positional[0], t);
            std::string payload = json_response(out);
            send_all(client_fd, payload.c_str(), payload.size());
        } else {
            send_error(client_fd, "Usage: TIME_RESOLVE <time_spec> [allow_max]");
        }
        return true;
    }

    // Handle VALUE <signal> <time> <fmt>
    if (cl.verb == CMD_VALUE) {
        if (cl.positional.size() >= 3 && cl.positional[2].size() == 1) {
            npiFsdbTime t = 0;
            std::string error;
            if (!parse_user_time(cl.positional[1].c_str(), false, t, error)) {
                send_error(client_fd, error);
                return true;
            }
            handle_value(client_fd, cl.positional[0].c_str(), t, cl.positional[2][0]);
        } else {
            const char* err = ERROR_PREFIX "Usage: VALUE <signal> <time> <fmt>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle LIST_VALUE <list_name> <time> <fmt> [json]
    if (cl.verb == CMD_LIST_VALUE) {
        if (cl.positional.size() >= 3) {
            npiFsdbTime t = 0;
            std::string error;
            if (!parse_user_time(cl.positional[1].c_str(), false, t, error)) {
                send_error(client_fd, error);
                return true;
            }
            bool use_json = cl.has_flag("json");
            handle_list_value(client_fd, cl.positional[0].c_str(), t, cl.positional[2][0], use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: LIST_VALUE <list> <time> <fmt> [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle SIGNAL_CHECK <signal>
    if (cl.verb == CMD_SIGNAL_CHECK) {
        if (cl.positional.size() >= 1) {
            handle_signal_check(client_fd, cl.positional[0].c_str());
        } else {
            const char* err = ERROR_PREFIX "Usage: SIGNAL_CHECK <signal>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle LIST_VALIDATE <list_name> [json]
    if (cl.verb == CMD_LIST_VALIDATE) {
        if (cl.positional.size() >= 1) {
            bool use_json = cl.has_flag("json");
            handle_list_validate(client_fd, cl.positional[0].c_str(), use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: LIST_VALIDATE <list> [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle SCOPE <scope_path> <recursive> <json|text>
    if (cl.verb == CMD_SCOPE) {
        if (cl.positional.size() >= 2) {
            int recursive = (cl.positional[1] == "1");
            bool use_json = cl.positional.size() >= 3 && cl.positional[2] == "json";
            handle_scope(client_fd, cl.positional[0].c_str(), recursive != 0, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: SCOPE <scope> <recursive> <json|text>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle LIST_DIFF <list_name> <begin_time> <end_time>
    if (cl.verb == CMD_LIST_DIFF) {
        if (cl.positional.size() >= 3) {
            npiFsdbTime begin = 0;
            npiFsdbTime end = 0;
            std::string error;
            if (!parse_user_time(cl.positional[1].c_str(), false, begin, error) ||
                !parse_user_time(cl.positional[2].c_str(), true, end, error)) {
                send_error(client_fd, error);
                return true;
            }
            handle_list_diff(client_fd, cl.positional[0].c_str(), begin, end);
        } else {
            const char* err = ERROR_PREFIX "Usage: LIST_DIFF <list> <begin> <end>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // --- APB/AXI/Event handlers: keep existing sscanf-based parsing ---
    // These are more complex (mixed positional + keyword flags) and the
    // CommandParser currently treats keywords as positional; deferring full
    // migration until Phase 2D (JSON internal command).

    // Handle APB_WR <name> [addr <addr>] [num <x>] [last] [json]
    if (strncmp(cmd, CMD_APB_WR, strlen(CMD_APB_WR)) == 0) {
        char name[256] = {};
        char addr_arg[64] = {};
        char num_arg[64] = {};
        bool has_addr = false, has_num = false, has_last = false, use_json = false;
        const char* p = cmd + strlen(CMD_APB_WR);
        if (sscanf(p, " %255s", name) >= 1) {
            const char* rest = strstr(p, name) + strlen(name);
            if (strstr(rest, "addr")) {
                if (sscanf(strstr(rest, "addr") + 4, " %63s", addr_arg) == 1) has_addr = true;
            }
            if (strstr(rest, "num")) {
                if (sscanf(strstr(rest, "num") + 3, " %63s", num_arg) == 1) has_num = true;
            }
            if (strstr(rest, "last")) has_last = true;
            if (strstr(rest, "json")) use_json = true;
            handle_apb_wr(client_fd, name, has_addr ? addr_arg : nullptr,
                          has_num ? atoi(num_arg) : -1, has_last, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: APB_WR <name> [addr <a>] [num <x>] [last] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle APB_RD <name> [addr <addr>] [num <x>] [last] [json]
    if (strncmp(cmd, CMD_APB_RD, strlen(CMD_APB_RD)) == 0) {
        char name[256] = {};
        char addr_arg[64] = {};
        char num_arg[64] = {};
        bool has_addr = false, has_num = false, has_last = false, use_json = false;
        const char* p = cmd + strlen(CMD_APB_RD);
        if (sscanf(p, " %255s", name) >= 1) {
            const char* rest = strstr(p, name) + strlen(name);
            if (strstr(rest, "addr")) {
                if (sscanf(strstr(rest, "addr") + 4, " %63s", addr_arg) == 1) has_addr = true;
            }
            if (strstr(rest, "num")) {
                if (sscanf(strstr(rest, "num") + 3, " %63s", num_arg) == 1) has_num = true;
            }
            if (strstr(rest, "last")) has_last = true;
            if (strstr(rest, "json")) use_json = true;
            handle_apb_rd(client_fd, name, has_addr ? addr_arg : nullptr,
                          has_num ? atoi(num_arg) : -1, has_last, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: APB_RD <name> [addr <a>] [num <x>] [last] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle APB_BEGIN|NEXT|PREV|LAST <name> [all|wr|rd] [json]
    if (strncmp(cmd, CMD_APB_BEGIN, strlen(CMD_APB_BEGIN)) == 0 ||
        strncmp(cmd, CMD_APB_NEXT, strlen(CMD_APB_NEXT)) == 0 ||
        strncmp(cmd, CMD_APB_PREV, strlen(CMD_APB_PREV)) == 0 ||
        strncmp(cmd, CMD_APB_LAST, strlen(CMD_APB_LAST)) == 0) {
        size_t base_len = 0;
        int cmd_type = 0;
        if (strncmp(cmd, CMD_APB_BEGIN, strlen(CMD_APB_BEGIN)) == 0) { base_len = strlen(CMD_APB_BEGIN); cmd_type = 1; }
        else if (strncmp(cmd, CMD_APB_NEXT, strlen(CMD_APB_NEXT)) == 0) { base_len = strlen(CMD_APB_NEXT); cmd_type = 2; }
        else if (strncmp(cmd, CMD_APB_PREV, strlen(CMD_APB_PREV)) == 0) { base_len = strlen(CMD_APB_PREV); cmd_type = 3; }
        else { base_len = strlen(CMD_APB_LAST); cmd_type = 4; }

        char name[256] = {};
        char filter_str[16] = {};
        bool use_json = false;
        const char* p = cmd + base_len;
        if (sscanf(p, " %255s %15s", name, filter_str) >= 1) {
            const char* rest = strstr(p, name);
            if (rest) rest += strlen(name);
            if (strstr(cmd, "json")) use_json = true;

            int filter = 0; // all
            if (strcmp(filter_str, "wr") == 0) filter = 1;
            else if (strcmp(filter_str, "rd") == 0) filter = 2;

            if (cmd_type == 1) handle_apb_begin(client_fd, name, filter, use_json);
            else if (cmd_type == 2) handle_apb_next(client_fd, name, filter, use_json);
            else if (cmd_type == 3) handle_apb_prev(client_fd, name, filter, use_json);
            else handle_apb_last(client_fd, name, filter, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: APB_{BEGIN|NEXT|PREV|LAST} <name> [all|wr|rd] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle AXI_WR|AXI_RD <name> [addr <addr>] [id <id>] [num <x>] [last] [json]
    if (strncmp(cmd, CMD_AXI_WR, strlen(CMD_AXI_WR)) == 0 ||
        strncmp(cmd, CMD_AXI_RD, strlen(CMD_AXI_RD)) == 0) {
        bool is_write = strncmp(cmd, CMD_AXI_WR, strlen(CMD_AXI_WR)) == 0;
        size_t base_len = is_write ? strlen(CMD_AXI_WR) : strlen(CMD_AXI_RD);
        char name[256] = {};
        char addr_arg[64] = {};
        char id_arg[64] = {};
        char num_arg[64] = {};
        bool has_addr = false, has_id = false, has_num = false, has_last = false, use_json = false;
        const char* p = cmd + base_len;
        if (sscanf(p, " %255s", name) >= 1) {
            const char* rest = strstr(p, name) + strlen(name);
            const char* addr_p = strstr(rest, "addr");
            if (addr_p && sscanf(addr_p + 4, " %63s", addr_arg) == 1) has_addr = true;
            const char* id_p = strstr(rest, "id");
            if (id_p && sscanf(id_p + 2, " %63s", id_arg) == 1) has_id = true;
            const char* num_p = strstr(rest, "num");
            if (num_p && sscanf(num_p + 3, " %63s", num_arg) == 1) has_num = true;
            if (strstr(rest, "last")) has_last = true;
            if (strstr(rest, "json")) use_json = true;
            handle_axi_rw(client_fd, name, is_write, has_addr ? addr_arg : nullptr,
                          has_id ? id_arg : nullptr, has_num ? atoi(num_arg) : -1,
                          has_last, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: AXI_WR|AXI_RD <name> [addr <a>] [id <id>] [num <x>] [last] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle AXI_BEGIN|NEXT|PREV|LAST <name> [all|wr|rd] [json]
    if (strncmp(cmd, CMD_AXI_BEGIN, strlen(CMD_AXI_BEGIN)) == 0 ||
        strncmp(cmd, CMD_AXI_NEXT, strlen(CMD_AXI_NEXT)) == 0 ||
        strncmp(cmd, CMD_AXI_PREV, strlen(CMD_AXI_PREV)) == 0 ||
        strncmp(cmd, CMD_AXI_LAST, strlen(CMD_AXI_LAST)) == 0) {
        size_t base_len = 0;
        int cmd_type = 0;
        if (strncmp(cmd, CMD_AXI_BEGIN, strlen(CMD_AXI_BEGIN)) == 0) { base_len = strlen(CMD_AXI_BEGIN); cmd_type = 1; }
        else if (strncmp(cmd, CMD_AXI_NEXT, strlen(CMD_AXI_NEXT)) == 0) { base_len = strlen(CMD_AXI_NEXT); cmd_type = 2; }
        else if (strncmp(cmd, CMD_AXI_PREV, strlen(CMD_AXI_PREV)) == 0) { base_len = strlen(CMD_AXI_PREV); cmd_type = 3; }
        else { base_len = strlen(CMD_AXI_LAST); cmd_type = 4; }

        char name[256] = {};
        char filter_str[16] = {};
        bool use_json = false;
        const char* p = cmd + base_len;
        if (sscanf(p, " %255s %15s", name, filter_str) >= 1) {
            if (strstr(cmd, "json")) use_json = true;
            int filter = 0;
            if (strcmp(filter_str, "wr") == 0) filter = 1;
            else if (strcmp(filter_str, "rd") == 0) filter = 2;
            handle_axi_cursor(client_fd, name, cmd_type, filter, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: AXI_{BEGIN|NEXT|PREV|LAST} <name> [all|wr|rd] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle AXI_LATENCY|AXI_OSD <name> [all|wr|rd] [id <id>] [json]
    if (strncmp(cmd, CMD_AXI_LATENCY, strlen(CMD_AXI_LATENCY)) == 0 ||
        strncmp(cmd, CMD_AXI_OSD, strlen(CMD_AXI_OSD)) == 0) {
        bool latency = strncmp(cmd, CMD_AXI_LATENCY, strlen(CMD_AXI_LATENCY)) == 0;
        size_t base_len = latency ? strlen(CMD_AXI_LATENCY) : strlen(CMD_AXI_OSD);
        char name[256] = {};
        char filter_str[16] = {};
        char id_arg[64] = {};
        bool has_id = false;
        bool use_json = false;
        const char* p = cmd + base_len;
        if (sscanf(p, " %255s %15s", name, filter_str) >= 1) {
            int filter = 0;
            if (strcmp(filter_str, "wr") == 0) filter = 1;
            else if (strcmp(filter_str, "rd") == 0) filter = 2;
            const char* rest = strstr(p, name) + strlen(name);
            const char* id_p = strstr(rest, "id");
            if (id_p && sscanf(id_p + 2, " %63s", id_arg) == 1) has_id = true;
            if (strstr(rest, "json")) use_json = true;
            handle_axi_stat(client_fd, name, latency, filter, has_id ? id_arg : nullptr, use_json);
        } else {
            const char* err = ERROR_PREFIX "Usage: AXI_LATENCY|AXI_OSD <name> [all|wr|rd] [id <id>] [json]\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle EVENT_FIND_CTX|EVENT_EXPORT_CTX <name> <begin> <end> <limit> <json|text> <context> <axi_name|-> <apb_name|-> expr <expr>
    if (strncmp(cmd, CMD_EVENT_FIND_CTX, strlen(CMD_EVENT_FIND_CTX)) == 0 ||
        strncmp(cmd, CMD_EVENT_EXPORT_CTX, strlen(CMD_EVENT_EXPORT_CTX)) == 0) {
        bool find = strncmp(cmd, CMD_EVENT_FIND_CTX, strlen(CMD_EVENT_FIND_CTX)) == 0;
        size_t base_len = find ? strlen(CMD_EVENT_FIND_CTX) : strlen(CMD_EVENT_EXPORT_CTX);
        char name[256] = {};
        char begin_str[256] = {};
        char end_str[256] = {};
        char context_str[256] = {};
        int limit = -1;
        char mode[16] = {};
        char axi_name[256] = {};
        char apb_name[256] = {};
        const char* p = cmd + base_len;
        int matched = sscanf(p, " %255s %255s %255s %d %15s %255s %255s %255s",
                             name, begin_str, end_str, &limit, mode, context_str, axi_name, apb_name);
        const char* expr_p = strstr(p, " expr ");
        if (matched >= 8 && expr_p) {
            expr_p += strlen(" expr ");
            bool use_json = strcmp(mode, "json") == 0;
            if (find) limit = 1;
            npiFsdbTime begin = 0;
            npiFsdbTime end = 0;
            npiFsdbTime context = 0;
            std::string error;
            if (!parse_user_time(begin_str, false, begin, error) ||
                !parse_user_time(end_str, true, end, error) ||
                !parse_user_time(context_str, false, context, error)) {
                send_error(client_fd, error);
                return true;
            }
            handle_event_query(client_fd,
                               name,
                               begin,
                               end,
                               limit,
                               use_json,
                               find,
                               expr_p,
                               strcmp(axi_name, "-") == 0 ? nullptr : axi_name,
                               strcmp(apb_name, "-") == 0 ? nullptr : apb_name,
                               context);
        } else {
            const char* err = ERROR_PREFIX "Usage: EVENT_FIND_CTX|EVENT_EXPORT_CTX <name> <begin> <end> <limit> <json|text> <context> <axi_name|-> <apb_name|-> expr <expr>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle EVENT_FIND|EVENT_EXPORT <name> <begin> <end> <limit> <json|text> expr <expr>
    if (strncmp(cmd, CMD_EVENT_FIND, strlen(CMD_EVENT_FIND)) == 0 ||
        strncmp(cmd, CMD_EVENT_EXPORT, strlen(CMD_EVENT_EXPORT)) == 0) {
        bool find = strncmp(cmd, CMD_EVENT_FIND, strlen(CMD_EVENT_FIND)) == 0;
        size_t base_len = find ? strlen(CMD_EVENT_FIND) : strlen(CMD_EVENT_EXPORT);
        char name[256] = {};
        char begin_str[256] = {};
        char end_str[256] = {};
        int limit = -1;
        char mode[16] = {};
        const char* p = cmd + base_len;
        int matched = sscanf(p, " %255s %255s %255s %d %15s", name, begin_str, end_str, &limit, mode);
        const char* expr_p = strstr(p, " expr ");
        if (matched >= 5 && expr_p) {
            expr_p += strlen(" expr ");
            bool use_json = strcmp(mode, "json") == 0;
            if (find) limit = 1;
            npiFsdbTime begin = 0;
            npiFsdbTime end = 0;
            std::string error;
            if (!parse_user_time(begin_str, false, begin, error) ||
                !parse_user_time(end_str, true, end, error)) {
                send_error(client_fd, error);
                return true;
            }
            handle_event_query(client_fd,
                               name,
                               begin,
                               end,
                               limit,
                               use_json,
                               find,
                               expr_p);
        } else {
            const char* err = ERROR_PREFIX "Usage: EVENT_FIND|EVENT_EXPORT <name> <begin> <end> <limit> <json|text> expr <expr>\n" END_MARKER;
            send_all(client_fd, err, strlen(err));
        }
        return true;
    }

    // Handle AI_QUERY <json>
    if (cl.verb == CMD_AI_QUERY) {
        // AI_QUERY has the entire JSON request as a single argument;
        // use the raw command line to extract the JSON portion
        const char* json_p = cmd + strlen(CMD_AI_QUERY);
        while (*json_p == ' ' || *json_p == '\t') json_p++;
        try {
            Json req = Json::parse(json_p);
            std::string error;
            Json data = ai_dispatch_query(req, error);
            if (!error.empty()) {
                send_error(client_fd, error);
            } else {
                std::string resp = json_response(data);
                send_all(client_fd, resp.c_str(), resp.length());
            }
        } catch (const std::exception& e) {
            send_error(client_fd, std::string("Invalid AI_QUERY JSON: ") + e.what());
        }
        return true;
    }

    // Unknown command
    const char* err = ERROR_PREFIX "Unknown command\n" END_MARKER;
    send_all(client_fd, err, strlen(err));
    return true;
}


}  // namespace xdebug_waveform
