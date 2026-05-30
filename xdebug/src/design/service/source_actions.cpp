#include "action_support.h"

#include <algorithm>
#include <fstream>

namespace xdebug_design {

namespace {

json infer_enclosing_block(const std::vector<std::string>& lines, int line) {
    json enclosing = {{"type", "unknown"}, {"name", ""}, {"begin_line", 1}, {"end_line", (int)lines.size()}};
    int best_line = 0;
    for (int i = std::min(line, (int)lines.size()); i >= 1; --i) {
        std::string text = trim(lines[i - 1]);
        std::string low = lower_copy(text);
        std::string type;
        std::string name;
        if (starts_with(low, "module ") || low.find(" module ") != std::string::npos) {
            type = "module";
            name = next_token_after(text, "module");
        } else if (low.find("always_ff") != std::string::npos) type = "always_ff";
        else if (low.find("always_comb") != std::string::npos) type = "always_comb";
        else if (low.find("always") != std::string::npos) type = "always";
        else if (low.find("case") != std::string::npos) type = "case";
        else if (low.find("if") != std::string::npos && low.find("(") != std::string::npos) type = "if";
        else if (low.find("begin") != std::string::npos) type = "begin";
        if (!type.empty()) {
            enclosing["type"] = type;
            enclosing["name"] = name;
            enclosing["begin_line"] = i;
            best_line = i;
            break;
        }
    }
    if (best_line > 0) {
        std::string end_token = enclosing["type"] == "module" ? "endmodule" :
                                enclosing["type"] == "case" ? "endcase" : "end";
        for (int i = line; i <= (int)lines.size(); ++i) {
            if (lower_copy(lines[i - 1]).find(end_token) != std::string::npos) {
                enclosing["end_line"] = i;
                break;
            }
        }
    }
    return enclosing;
}

} // namespace

json source_context(const json& request) {
    json response = base_response(request, request.value("action", ""));
    json args = request.value("args", json::object());
    std::string file = args.value("file", "");
    int line = args.value("line", 0);
    int context_lines = args.value("context_lines", compact_mode(request) ? 3 : 8);
    bool include_source = include_arg(request, "include_source");
    if (compact_mode(request) && context_lines > 3 && !include_source) context_lines = 3;
    if (file.empty() || line <= 0) {
        return error_response(request, request.value("action", ""), "MISSING_FIELD", "args.file and args.line are required");
    }
    std::ifstream in(file.c_str());
    if (!in) return error_response(request, request.value("action", ""), "SOURCE_NOT_FOUND", "source file not found: " + file);
    std::vector<std::string> lines;
    std::string s;
    while (std::getline(in, s)) lines.push_back(s);
    if (line > static_cast<int>(lines.size())) return error_response(request, request.value("action", ""), "INVALID_REQUEST", "line is out of range");
    int begin = std::max(1, line - context_lines);
    int end = std::min(static_cast<int>(lines.size()), line + context_lines);
    json enclosing = infer_enclosing_block(lines, line);
    response["summary"] = {{"file", file}, {"line", line}};
    response["data"] = {{"file", file}, {"line", line},
        {"symbol", args.value("symbol", std::string())},
        {"context_kind", enclosing.value("type", std::string("unknown"))}};
    response["data"]["enclosing"] = enclosing;
    if (!compact_mode(request) || include_source) {
        json ctx = json::array();
        for (int i = begin; i <= end; ++i) ctx.push_back({{"line", i}, {"text", lines[i - 1]}, {"hit", i == line}});
        response["data"]["context"] = ctx;
    }
    return response;
}

json control_explain(const json& request) {
    json trace_req = request;
    trace_req["action"] = "trace.driver";
    trace_req["args"]["include_trace"] = true;
    json trace_resp = run_trace_action(trace_req, "driver");
    if (!trace_resp.value("ok", false)) return trace_resp;
    json deps = trace_resp["data"].value("control_dependencies", json::array());
    for (auto& dep : deps) {
        std::string source = dep.value("source", "");
        std::string cond = source;
        size_t if_pos = cond.find("if");
        size_t lparen = cond.find('(', if_pos == std::string::npos ? 0 : if_pos);
        size_t rparen = cond.rfind(')');
        if (lparen != std::string::npos && rparen != std::string::npos && rparen > lparen) {
            cond = cond.substr(lparen + 1, rparen - lparen - 1);
        }
        dep["condition_text"] = trim(cond);
        dep["condition"] = parse_expr_ast(cond);
        dep["condition_signals"] = json::array({dep.value("signal", "")});
        dep["confidence"] = dep.value("source", "").empty() ? "low" : "medium";
    }
    trace_resp["action"] = request.value("action", "control.explain");
    trace_resp["summary"] = {{"signal", request.value("args", json::object()).value("signal", "")},
                              {"control_dependency_count", deps.size()}};
    trace_resp["data"] = {{"control_dependencies", deps}};
    return trace_resp;
}

json run_expr_normalize_action(const json& request) {
    const std::string action = request.value("action", "");
    json response = base_response(request, action);
    json args = request.value("args", json::object());
    std::string signal = args.value("signal", "");
    if (!signal.empty()) {
        json trace_req = request;
        trace_req["action"] = "trace.driver";
        trace_req["args"]["signal"] = signal;
        trace_req["args"]["include_trace"] = true;
        trace_req["args"]["include_ast"] = true;
        json trace_resp = run_trace_action(trace_req, "driver");
        if (!trace_resp.value("ok", false)) return trace_resp;
        json assignment = trace_resp["data"].value("assignment", json::object());
        response["session"] = trace_resp["session"];
        response["summary"] = {{"signal", signal}, {"source", "npi_trace_assignment"},
                               {"confidence", trace_resp["data"].value("confidence", "unknown")}};
        response["data"] = {{"expr", assignment.value("rhs", json::object())}, {"assignment", assignment},
            {"rhs_signals", assignment.value("rhs_signals", json::array())},
            {"confidence", trace_resp["data"].value("confidence", "unknown")}};
        return response;
    }
    std::string expr = args.value("expr", "");
    if (expr.empty()) return error_response(request, action, "MISSING_FIELD", "args.expr or args.signal is required");
    response["summary"] = {{"expr", expr}, {"source", "string_fallback"}, {"confidence", "low"}};
    response["data"] = {{"expr", parse_expr_ast(expr)}, {"confidence", "low"},
                        {"confidence_reason", "parsed from raw string without NPI handle"}};
    return response;
}

} // namespace xdebug_design
