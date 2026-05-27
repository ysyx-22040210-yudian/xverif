#include "action_support.h"

#include <algorithm>
#include <fstream>

namespace xdebug_design {

namespace {

json condition_from_control_dep(const json& dep) {
    std::string source = dep.value("source", "");
    std::string cond = dep.value("condition_text", "");
    if (cond.empty()) {
        cond = source;
        size_t lparen = cond.find('(');
        size_t rparen = cond.rfind(')');
        if (lparen != std::string::npos && rparen != std::string::npos && rparen > lparen) {
            cond = cond.substr(lparen + 1, rparen - lparen - 1);
        }
    }
    return {{"text", trim(cond)}, {"ast", dep.value("condition", parse_expr_ast(cond))},
            {"signals", dep.value("condition_signals", json::array())},
            {"file", dep.value("file", "")}, {"line", dep.value("line", 0)},
            {"source", source}, {"confidence", dep.value("confidence", "medium")}};
}

json infer_clock_reset_from_assignment(const json& assignment, const json& control_deps) {
    json out = {{"clock", nullptr}, {"reset", nullptr}, {"event_controls", json::array()}};
    std::string file = assignment.value("location", json::object()).value("file", "");
    int line = assignment.value("location", json::object()).value("line", 0);
    if (!file.empty() && line > 0) {
        std::ifstream in(file.c_str());
        std::vector<std::string> lines;
        std::string s;
        while (std::getline(in, s)) lines.push_back(s);
        int begin = std::max(1, line - 40);
        for (int i = line; i >= begin; --i) {
            std::string text = lines[i - 1];
            std::string low = lower_copy(text);
            if (low.find("@") == std::string::npos &&
                low.find("always_ff") == std::string::npos &&
                low.find("always ") == std::string::npos) continue;
            std::string pos = next_token_after(text, "posedge");
            std::string neg = next_token_after(text, "negedge");
            if (!pos.empty()) {
                out["clock"] = pos;
                out["event_controls"].push_back({{"edge", "posedge"}, {"signal", pos}, {"line", i}, {"source", trim(text)}});
            }
            if (!neg.empty()) {
                out["reset"] = neg;
                out["event_controls"].push_back({{"edge", "negedge"}, {"signal", neg}, {"line", i}, {"source", trim(text)}});
            }
            if (!pos.empty() || !neg.empty()) break;
        }
    }
    for (const auto& dep : control_deps) {
        std::string sig = dep.value("signal", "");
        if (out["reset"].is_null() && (contains_word_like(sig, "rst") || contains_word_like(sig, "reset"))) out["reset"] = sig;
    }
    return out;
}

std::string classify_update_rule(const json& assignment, const json& condition, const std::string& target) {
    std::string cond_text = lower_copy(condition.value("text", ""));
    std::string source = lower_copy(assignment.value("source", ""));
    json rhs = assignment.value("rhs", json::object());
    std::string op = expr_op(rhs);
    if (cond_text.find("rst") != std::string::npos || cond_text.find("reset") != std::string::npos ||
        source.find("rst") != std::string::npos || source.find("reset") != std::string::npos) return "reset";
    if ((op == "add" || source.find("+") != std::string::npos) && expr_mentions_signal(rhs, target)) return "increment";
    if ((op == "sub" || source.find("-") != std::string::npos) && expr_mentions_signal(rhs, target)) return "decrement";
    if (expr_mentions_signal(rhs, target) && signal_array_from_ast(rhs).size() == 1) return "hold";
    return "update";
}

json normalize_assignments_with_conditions(const json& trace_data) {
    json out = json::array();
    json controls = trace_data.value("control_dependencies", json::array());
    for (auto assignment : trace_data.value("assignments", json::array())) {
        json conditions = json::array();
        for (const auto& dep : controls) conditions.push_back(condition_from_control_dep(dep));
        assignment["active_conditions"] = conditions;
        assignment["rhs_signals"] = assignment.value("rhs_signals", signal_array_from_ast(assignment.value("rhs", json::object())));
        assignment["assignment_role"] = conditions.empty() ? "default_or_unconditional" : "branch_assignment";
        out.push_back(assignment);
    }
    return out;
}

} // namespace

json run_procedural_assignment_action(const json& request) {
    json trace_req = request;
    trace_req["action"] = "trace.driver";
    json trace_resp = run_trace_action(trace_req, "driver");
    if (!trace_resp.value("ok", false)) return trace_resp;
    json response = base_response(request, request.value("action", ""));
    response["session"] = trace_resp["session"];
    std::string signal = request.value("args", json::object()).value("signal", "");
    json trace_data = trace_resp.value("data", json::object());
    json assignments = normalize_assignments_with_conditions(trace_data);
    json defaults = json::array();
    json branches = json::array();
    for (const auto& a : assignments) {
        if (a.value("assignment_role", "") == "default_or_unconditional") defaults.push_back(a);
        else branches.push_back(a);
    }
    response["summary"] = {{"signal", signal}, {"assignment_count", assignments.size()},
        {"branch_count", branches.size()}, {"default_count", defaults.size()},
        {"confidence", trace_data.value("confidence", "unknown")}};
    response["data"] = {{"procedural_assignment", {{"target", signal},
        {"enclosing_block", assignments.empty() ? json{{"type", "unknown"}} :
            json{{"type", "procedural_or_continuous"}, {"location", assignments[0].value("location", json::object())}}},
        {"assignments", assignments}, {"default_assignments", defaults}, {"branch_assignments", branches},
        {"control_dependencies", trace_data.value("control_dependencies", json::array())},
        {"dependency_edges", trace_data.value("dependency_edges", json::array())},
        {"confidence", trace_data.value("confidence", "unknown")},
        {"confidence_reason", trace_data.value("confidence_reason", "")}}}};
    return response;
}

json run_sequential_update_action(const json& request) {
    json proc_resp = run_procedural_assignment_action(request);
    if (!proc_resp.value("ok", false)) return proc_resp;
    json response = base_response(request, request.value("action", ""));
    response["session"] = proc_resp["session"];
    std::string signal = request.value("args", json::object()).value("signal", "");
    json proc = proc_resp["data"].value("procedural_assignment", json::object());
    json assignments = proc.value("assignments", json::array());
    json controls = proc.value("control_dependencies", json::array());
    json timing = assignments.empty() ? json{{"clock", nullptr}, {"reset", nullptr}, {"event_controls", json::array()}} :
                                      infer_clock_reset_from_assignment(assignments[0], controls);
    json rules = json::array();
    for (const auto& assignment : assignments) {
        json conditions = assignment.value("active_conditions", json::array());
        if (conditions.empty()) conditions.push_back({{"text", ""}, {"ast", json::object()}, {"signals", json::array()}});
        for (const auto& condition : conditions) {
            rules.push_back({{"kind", classify_update_rule(assignment, condition, signal)}, {"condition", condition},
                {"next_value", assignment.value("rhs", json::object())},
                {"next_value_text", assignment.value("rhs", json::object()).value("text", assignment.value("source", ""))},
                {"rhs_signals", assignment.value("rhs_signals", json::array())},
                {"source", assignment.value("source", "")}, {"location", assignment.value("location", json::object())}});
        }
    }
    response["summary"] = {{"signal", signal}, {"rule_count", rules.size()},
        {"clock", timing.value("clock", json(nullptr))}, {"reset", timing.value("reset", json(nullptr))},
        {"confidence", proc.value("confidence", "unknown")}};
    response["data"] = {{"sequential_update", {{"target", signal}, {"clock", timing.value("clock", json(nullptr))},
        {"reset", timing.value("reset", json(nullptr))}, {"event_controls", timing.value("event_controls", json::array())},
        {"rules", rules}, {"confidence", proc.value("confidence", "unknown")},
        {"confidence_reason", proc.value("confidence_reason", "")}}}};
    return response;
}

json run_fsm_explain_action(const json& request) {
    json seq_resp = run_sequential_update_action(request);
    if (!seq_resp.value("ok", false)) return seq_resp;
    json response = base_response(request, request.value("action", ""));
    response["session"] = seq_resp["session"];
    std::string signal = request.value("args", json::object()).value("signal", "");
    json seq = seq_resp["data"].value("sequential_update", json::object());
    json transitions = json::array();
    for (const auto& rule : seq.value("rules", json::array())) {
        std::string kind = rule.value("kind", "");
        if (kind == "reset" || kind == "update") {
            transitions.push_back({{"from", "current"}, {"to", rule.value("next_value_text", "")},
                {"condition", rule.value("condition", json::object())},
                {"kind", kind == "reset" ? "reset_transition" : "transition"},
                {"source", rule.value("source", "")}, {"location", rule.value("location", json::object())}});
        }
    }
    response["summary"] = {{"signal", signal}, {"transition_count", transitions.size()},
                           {"confidence", seq.value("confidence", "unknown")}};
    response["data"] = {{"fsm", {{"state_signal", signal}, {"clock", seq.value("clock", json(nullptr))},
        {"reset", seq.value("reset", json(nullptr))}, {"transitions", transitions},
        {"rules", seq.value("rules", json::array())}, {"confidence", seq.value("confidence", "unknown")},
        {"confidence_reason", seq.value("confidence_reason", "")}}}};
    return response;
}

json run_counter_explain_action(const json& request) {
    json seq_resp = run_sequential_update_action(request);
    if (!seq_resp.value("ok", false)) return seq_resp;
    json response = base_response(request, request.value("action", ""));
    response["session"] = seq_resp["session"];
    std::string signal = request.value("args", json::object()).value("signal", "");
    json seq = seq_resp["data"].value("sequential_update", json::object());
    json counter_rules = json::array();
    bool is_counter_like = false;
    for (const auto& rule : seq.value("rules", json::array())) {
        std::string kind = rule.value("kind", "");
        if (kind == "reset" || kind == "increment" || kind == "decrement" || kind == "hold" || kind == "update") {
            counter_rules.push_back(rule);
        }
        if (kind == "increment" || kind == "decrement") is_counter_like = true;
    }
    std::string confidence = is_counter_like ? seq.value("confidence", "medium") : "medium";
    response["summary"] = {{"signal", signal}, {"counter_like", is_counter_like},
                           {"rule_count", counter_rules.size()}, {"confidence", confidence}};
    response["data"] = {{"counter", {{"signal", signal}, {"clock", seq.value("clock", json(nullptr))},
        {"reset", seq.value("reset", json(nullptr))}, {"rules", counter_rules}, {"counter_like", is_counter_like},
        {"confidence", confidence}, {"confidence_reason", is_counter_like ?
            "increment/decrement rule was identified from next-value expression" :
            "sequential rules were found but no increment/decrement pattern was proven"}}}};
    return response;
}

} // namespace xdebug_design
