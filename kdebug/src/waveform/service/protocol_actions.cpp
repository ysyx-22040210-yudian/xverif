#include "router_actions.h"

#include "../apb/apb_manager.h"
#include "../axi/axi_manager.h"
#include "../event/event_manager.h"
#include "../protocol/protocol.h"

namespace kdebug_waveform {

int run_protocol_action(const Json& req, const std::string& action, const Json& args,
                        const Json& limits, const std::string& sid, const SessionInfo& info,
                        long long elapsed_ms, bool& handled) {
    handled = action.compare(0, 4, "apb.") == 0 ||
              action.compare(0, 4, "axi.") == 0 ||
              action.compare(0, 6, "event.") == 0;
    if (!handled) return 0;

    std::string err;
    auto ok_out = [&]() {
        Json out = base_response(req, action, true, elapsed_ms);
        fill_session(out, info);
        return out;
    };
    auto emit = [&](const Json& out, int rc = 0) -> int {
        print_json(finalize_response(req, out));
        return rc;
    };

    if (action.compare(0, 4, "apb.") == 0) {
        ApbManager am;
        std::string name = string_or(args, "name", "");
        if (action == "apb.config.load") {
            if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "apb.config.load requires args.name", elapsed_ms);
            Json cfg_json; if (!load_config_json_arg(args, cfg_json, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
            ApbConfig cfg; if (!parse_apb_config(cfg_json, cfg, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
            cfg.name = name;
            if (!am.create_apb(sid, cfg)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to save APB config", elapsed_ms);
            Json out = ok_out(); out["summary"] = {{"name", name}, {"status", "loaded"}}; out["data"]["config"] = apb_config_json(cfg); return emit(out);
        }
        if (name.empty()) am.get_latest_apb(sid, name);
        if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "APB action requires args.name or latest config", elapsed_ms);
        if (action == "apb.config.list") {
            ApbConfig cfg; if (!am.get_apb(sid, name, cfg)) return print_error_and_return(req, action, "INVALID_REQUEST", "APB config not found", elapsed_ms);
            Json out = ok_out(); out["summary"] = {{"name", name}}; out["data"]["config"] = apb_config_json(cfg); return emit(out);
        }
        std::string cmd;
        if (action == "apb.query") {
            std::string dir = string_or(args, "direction", "wr");
            cmd = std::string(dir == "rd" ? CMD_APB_RD : CMD_APB_WR) + " " + name;
            if (args.contains("address")) cmd += " addr " + arg_text(args["address"]);
            if (args.contains("num")) cmd += " num " + std::to_string(args["num"].get<int>());
            if (bool_or(args, "last", false)) cmd += " last";
            cmd += " json";
        } else {
            std::string op = string_or(args, "op", "begin");
            const char* pcmd = op == "next" ? CMD_APB_NEXT : op == "pre" ? CMD_APB_PREV : op == "last" ? CMD_APB_LAST : CMD_APB_BEGIN;
            cmd = std::string(pcmd) + " " + name + " " + string_or(args, "direction", "all") + " json";
        }
        Json data; if (!capture_server_json(sid, cmd, data, err)) return print_error_and_return(req, action, "WAVE_QUERY_FAILED", err, elapsed_ms);
        Json out = ok_out(); out["summary"] = {{"name", name}}; out["data"] = data; return emit(out);
    }

    if (action.compare(0, 4, "axi.") == 0) {
        AxiManager am;
        std::string name = string_or(args, "name", "");
        if (action == "axi.config.load") {
            if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "axi.config.load requires args.name", elapsed_ms);
            Json cfg_json; if (!load_config_json_arg(args, cfg_json, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
            AxiConfig cfg; if (!parse_axi_config(cfg_json, cfg, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
            cfg.name = name;
            if (!am.create_axi(sid, cfg)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to save AXI config", elapsed_ms);
            Json out = ok_out(); out["summary"] = {{"name", name}, {"status", "loaded"}}; out["data"]["config"] = axi_config_json(cfg); return emit(out);
        }
        if (name.empty()) am.get_latest_axi(sid, name);
        if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "AXI action requires args.name or latest config", elapsed_ms);
        if (action == "axi.config.list") {
            AxiConfig cfg; if (!am.get_axi(sid, name, cfg)) return print_error_and_return(req, action, "INVALID_REQUEST", "AXI config not found", elapsed_ms);
            Json out = ok_out(); out["summary"] = {{"name", name}}; out["data"]["config"] = axi_config_json(cfg); return emit(out);
        }
        std::string cmd;
        if (action == "axi.query") {
            std::string dir = string_or(args, "direction", "wr");
            cmd = std::string(dir == "rd" ? CMD_AXI_RD : CMD_AXI_WR) + " " + name;
            if (args.contains("address")) cmd += " addr " + arg_text(args["address"]);
            if (args.contains("id")) cmd += " id " + arg_text(args["id"]);
            if (args.contains("num")) cmd += " num " + std::to_string(args["num"].get<int>());
            if (bool_or(args, "last", false)) cmd += " last";
            cmd += " json";
        } else if (action == "axi.analysis") {
            std::string analysis = string_or(args, "analysis", "latency");
            cmd = std::string(analysis == "osd" ? CMD_AXI_OSD : CMD_AXI_LATENCY) + " " + name + " " + string_or(args, "direction", "all");
            if (args.contains("id")) cmd += " id " + arg_text(args["id"]);
            cmd += " json";
        } else {
            std::string op = string_or(args, "op", "begin");
            const char* pcmd = op == "next" ? CMD_AXI_NEXT : op == "pre" ? CMD_AXI_PREV : op == "last" ? CMD_AXI_LAST : CMD_AXI_BEGIN;
            cmd = std::string(pcmd) + " " + name + " " + string_or(args, "direction", "all") + " json";
        }
        Json data; if (!capture_server_json(sid, cmd, data, err)) return print_error_and_return(req, action, "WAVE_QUERY_FAILED", err, elapsed_ms);
        Json out = ok_out(); out["summary"] = {{"name", name}}; out["data"] = data; return emit(out);
    }

    EventManager em;
    std::string name = string_or(args, "name", "");
    if (action == "event.config.load") {
        if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "event.config.load requires args.name", elapsed_ms);
        Json cfg_json; if (!load_config_json_arg(args, cfg_json, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
        EventConfig cfg; if (!parse_event_config(cfg_json, cfg, err)) return print_error_and_return(req, action, "INVALID_REQUEST", err, elapsed_ms);
        cfg.name = name;
        if (!em.create_event(sid, info.fsdb_file, cfg)) return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to save event config", elapsed_ms);
        Json out = ok_out(); out["summary"] = {{"name", name}, {"status", "loaded"}}; out["data"]["config"] = event_config_json(cfg); return emit(out);
    }
    if (action == "event.config.list") {
        Json out = ok_out();
        if (name.empty()) {
            Json arr = em.list_events(sid, info.fsdb_file);
            out["summary"] = {{"count", arr.size()}};
            out["data"]["events"] = arr;
        } else {
            EventConfig cfg; if (!em.get_event(sid, info.fsdb_file, name, cfg)) return print_error_and_return(req, action, "INVALID_REQUEST", "event config not found", elapsed_ms);
            out["summary"] = {{"name", name}};
            out["data"]["config"] = event_config_json(cfg);
        }
        return emit(out);
    }
    std::string expr; if (!get_string(args, "expr", expr)) return print_error_and_return(req, action, "MISSING_FIELD", "event.find/export requires args.expr", elapsed_ms);
    expr = compact_expr_ws(expr);
    bool inline_event = false;
    if (name.empty() && args.contains("signals") && args["signals"].is_object()) {
        EventConfig cfg;
        cfg.name = "__inline_" + sid;
        cfg.clk = string_or(args, "clk", "");
        cfg.rst_n = string_or(args, "rst_n", "");
        std::string edge = string_or(args, "edge", "posedge");
        cfg.posedge = edge != "negedge";
        for (auto it = args["signals"].begin(); it != args["signals"].end(); ++it) {
            if (!it.value().is_string()) {
                return print_error_and_return(req, action, "INVALID_REQUEST", "event.find inline signals must map alias to string path", elapsed_ms);
            }
            if (it.key() == "clk" && cfg.clk.empty()) {
                cfg.clk = it.value().get<std::string>();
                continue;
            }
            if (it.key() == "rst_n" && cfg.rst_n.empty()) {
                cfg.rst_n = it.value().get<std::string>();
                continue;
            }
            cfg.signals[it.key()] = it.value().get<std::string>();
        }
        if (cfg.clk.empty()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "event.find inline mode requires args.clk or args.signals.clk", elapsed_ms);
        }
        if (cfg.signals.empty()) {
            return print_error_and_return(req, action, "MISSING_FIELD", "event.find inline mode requires args.signals alias map", elapsed_ms);
        }
        if (!em.create_event(sid, info.fsdb_file, cfg)) {
            return print_error_and_return(req, action, "INTERNAL_ERROR", "failed to create temporary inline event config", elapsed_ms);
        }
        name = cfg.name;
        inline_event = true;
    }
    if (name.empty()) em.get_latest_event(sid, info.fsdb_file, name);
    if (name.empty()) return print_error_and_return(req, action, "MISSING_FIELD", "event action requires args.name or inline args.expr + args.signals", elapsed_ms);
    std::string begin, end;
    bool around_window = false;
    if (!build_range_specs(args, begin, end, around_window, err)) {
        return print_error_and_return(req, action, "TIME_SPEC_INVALID", err, elapsed_ms);
    }
    std::string find_mode = string_or(args, "mode", "first");
    if (find_mode == "head") find_mode = "first";
    if (find_mode == "tail") find_mode = "last";
    bool fast_find = action == "event.find" && find_mode == "first";
    int limit = fast_find ? 1 : int_or(args, "limit", int_or(limits, "max_rows", 1000));
    if (action == "event.find" && find_mode == "last") {
        limit = int_or(args, "scan_limit", int_or(limits, "max_rows", 10000));
    }
    if (compact_mode(req) && action == "event.export" && !bool_or(args, "include_rows", false)) {
        limit = max_items_arg(args, limits, 20);
    }
    Json ctx = args.value("context", Json::object());
    std::string cmd;
    if (ctx.is_object() && ctx.contains("window")) {
        std::string window = string_or(ctx, "window", "0ns");
        std::string axi = string_or(ctx, "axi", "-"); if (axi.empty()) axi = "-";
        std::string apb = string_or(ctx, "apb", "-"); if (apb.empty()) apb = "-";
        cmd = std::string(fast_find ? CMD_EVENT_FIND_CTX : CMD_EVENT_EXPORT_CTX) + " " + name + " " + begin + " " + end + " " + std::to_string(limit) + " json " + window + " " + axi + " " + apb + " expr " + expr;
    } else {
        cmd = std::string(fast_find ? CMD_EVENT_FIND : CMD_EVENT_EXPORT) + " " + name + " " + begin + " " + end + " " + std::to_string(limit) + " json expr " + expr;
    }
    Json data;
    if (!capture_server_json(sid, cmd, data, err)) {
        if (inline_event) em.delete_event(sid, info.fsdb_file, name);
        return print_error_and_return(req, action, "WAVE_QUERY_FAILED", err, elapsed_ms);
    }
    if (inline_event) em.delete_event(sid, info.fsdb_file, name);
    if (action == "event.find" && find_mode == "last" && data.is_array() && data.size() > 1) {
        Json last = data.back();
        data = Json::array({last});
    }
    Json aggregate = Json::object();
    bool has_aggregate = action == "event.export" && args.contains("aggregate") && args["aggregate"].is_object();
    bool include_events = true;
    if (has_aggregate) {
        aggregate = aggregate_events(data, args["aggregate"], limit);
        include_events = args["aggregate"].value("events", true);
    }
    Json out = ok_out();
    out["summary"] = {{"name", name}, {"begin", begin}, {"end", end}, {"inline", inline_event},
                      {"mode", find_mode}, {"sampling_mode", "clock_edge"}};
    if (data.is_array()) {
        out["summary"]["event_count"] = data.size();
        if (!data.empty()) {
            if (data.front().is_object() && data.front().contains("time")) out["summary"]["first"] = data.front()["time"];
            if (data.back().is_object() && data.back().contains("time")) out["summary"]["last"] = data.back()["time"];
        }
    }
    if (has_aggregate) {
        out["summary"]["aggregate_count"] = aggregate.value("count", 0);
        out["summary"]["limited"] = aggregate.value("limited", false);
        if (aggregate.contains("group_count")) out["summary"]["group_count"] = aggregate["group_count"];
        out["data"]["aggregate"] = aggregate;
    }
    if (include_events) {
        if (compact_mode(req) && !bool_or(args, "include_rows", false)) {
            Json examples = Json::array();
            int max_examples = max_examples_arg(args, limits, 5);
            if (data.is_array()) {
                for (size_t i = 0; i < data.size() && i < static_cast<size_t>(max_examples); ++i) {
                    Json ev = data[i];
                    if (ev.is_object()) {
                        Json ex = Json::object();
                        if (ev.contains("time")) ex["time"] = ev["time"];
                        if (ev.contains("fields")) ex["fields"] = make_value_map(ev["fields"]);
                        if (ev.contains("signals")) ex["signals"] = make_value_map(ev["signals"]);
                        examples.push_back(ex.empty() ? ev : ex);
                    } else {
                        examples.push_back(ev);
                    }
                }
            }
            out["data"]["examples"] = examples;
            out["meta"]["truncated"] = data.is_array() && data.size() > static_cast<size_t>(max_examples);
        } else {
            out["data"]["events"] = simplify_event_value_objects(data);
        }
    }
    if (!compact_mode(req)) fill_resolved_range(out, sid, begin, end, around_window, err);
    return emit(out);
}

} // namespace kdebug_waveform
