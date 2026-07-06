#include "design_postprocess.h"

#include <algorithm>
#include <fstream>
#include <map>
#include <sstream>

namespace xdebug_design {
namespace detail {

// ═══════════════════════════════════════════════════════════════════════════
// graph building
// ═══════════════════════════════════════════════════════════════════════════

json graph_from_trace(const json& trace, const std::string& root) {
    json nodes = json::array();
    json edges = trace.value("dependency_edges", json::array());
    std::map<std::string, std::string> ids;
    auto add_node = [&](const std::string& signal, const std::string& role) {
        if (signal.empty() || ids.count(signal)) return;
        std::string id = "n" + std::to_string(ids.size());
        ids[signal] = id;
        nodes.push_back({{"id", id}, {"signal", signal}, {"kind", "signal"}, {"role", role}});
    };
    add_node(root, "root");
    for (const auto& e : edges) {
        add_node(e.value("from", ""), "dependency");
        add_node(e.value("to", ""), "dependency");
    }
    json graph_edges = json::array();
    for (auto e : edges) {
        std::string from = e.value("from", "");
        std::string to = e.value("to", "");
        e["from"] = ids.count(from) ? ids[from] : from;
        e["to"] = ids.count(to) ? ids[to] : to;
        e["from_signal"] = from;
        e["to_signal"] = to;
        graph_edges.push_back(e);
    }
    return {{"nodes", nodes}, {"edges", graph_edges}};
}

// ═══════════════════════════════════════════════════════════════════════════
// edge processing
// ═══════════════════════════════════════════════════════════════════════════

std::string confidence_for_edge(const json& edge) {
    std::string confidence = edge.value("confidence", "");
    if (!confidence.empty()) return confidence;
    std::string type = edge.value("type", "");
    std::string resolution = edge.value("resolution", "");
    if (type == "statement_only" || resolution == "statement_only") return "low";
    if (type == "control_dependency") return "medium";
    if (!edge.value("source", "").empty()) return "high";
    return "medium";
}

json evidence_from_edge(const json& edge) {
    return {
        {"type", edge.value("type", "")}, {"file", edge.value("file", "")},
        {"line", edge.value("line", 0)}, {"source", edge.value("source", "")},
        {"role", edge.value("role", "")}, {"confidence", confidence_for_edge(edge)},
        {"resolution", edge.value("resolution", "")}, {"relation", edge.value("relation", "")}
    };
}

json explanation_from_edge(const json& edge,
                           const std::string& root,
                           const std::string& direction,
                           int& skipped_empty_dependency_count) {
    std::string from = edge.value("from", "");
    std::string to = edge.value("to", "");
    std::string type = edge.value("type", "dependency");
    std::string related = direction == "load" ? to : from;
    json related_signals = json::array();
    if (!related.empty()) related_signals.push_back(related);
    if (related.empty() && type != "statement_only") {
        skipped_empty_dependency_count++;
        return nullptr;
    }
    std::string claim;
    if (type == "control_dependency") claim = root + " is controlled by " + related;
    else if (type == "statement_only") claim = root + " has assignment evidence without resolved dependencies";
    else if (direction == "load") claim = root + " can affect " + related;
    else claim = root + " depends on " + related;
    json evidence = json::array({evidence_from_edge(edge)});
    for (const auto& item : edge.value("evidence", json::array())) evidence.push_back(item);
    return {{"claim", claim}, {"evidence", evidence}, {"related_signals", related_signals},
            {"confidence", confidence_for_edge(edge)}};
}

bool edge_type_allowed(const json& args, const json& edge) {
    json types = args.value("dependency_types", json::array());
    if (types.empty()) return true;
    std::string edge_type = edge.value("type", "");
    std::string assignment_type = edge.value("assignment_type", "");
    for (const auto& t : types) {
        if (!t.is_string()) continue;
        std::string want = t.get<std::string>();
        if (edge_type == want || assignment_type == want) return true;
        if (want == "data" && (edge_type == "data_dependency" ||
                               edge_type == "continuous_assignment" ||
                               edge_type == "procedural_assignment")) return true;
        if (want == "control" && edge_type == "control_dependency") return true;
        if (want == "load" && edge_type == "load_dependency") return true;
    }
    return false;
}

std::string edge_dedupe_key(const json& edge) {
    std::ostringstream key;
    key << edge.value("from", "") << '\x1f' << edge.value("to", "") << '\x1f'
        << edge.value("type", "") << '\x1f' << edge.value("assignment_type", "") << '\x1f'
        << edge.value("role", "") << '\x1f' << edge.value("file", "") << '\x1f'
        << edge.value("line", 0) << '\x1f' << edge.value("source", "");
    return key.str();
}

std::string edge_relation_key(const json& edge) {
    std::ostringstream key;
    key << edge.value("from", "") << '\x1f' << edge.value("to", "") << '\x1f'
        << edge.value("type", "") << '\x1f' << edge.value("assignment_type", "");
    return key.str();
}

json aggregate_edges_by_relation(const json& edges, int max_evidence_per_edge, int& aggregated_edge_count) {
    json grouped = json::array();
    std::map<std::string, size_t> group_index;
    std::map<std::string, int> group_counts;
    for (const auto& edge : edges) {
        std::string key = edge_relation_key(edge);
        auto found = group_index.find(key);
        if (found == group_index.end()) {
            json grouped_edge = edge;
            grouped_edge["evidence"] = json::array();
            group_index[key] = grouped.size();
            group_counts[key] = 1;
            grouped.push_back(grouped_edge);
            continue;
        }
        size_t idx = found->second;
        group_counts[key]++;
        grouped[idx]["evidence_count"] = group_counts[key];
        if ((int)grouped[idx]["evidence"].size() < max_evidence_per_edge) {
            grouped[idx]["evidence"].push_back(evidence_from_edge(edge));
        } else {
            grouped[idx]["evidence_truncated"] = true;
            grouped[idx]["omitted_evidence_count"] =
                (group_counts[key] - 1) - (int)grouped[idx]["evidence"].size();
        }
    }
    for (auto& edge : grouped) {
        if (edge.value("evidence_count", 1) <= 1) edge.erase("evidence");
        else if (!edge.value("evidence_truncated", false)) {
            edge.erase("evidence_truncated");
            edge.erase("omitted_evidence_count");
        }
    }
    aggregated_edge_count = (int)edges.size() - (int)grouped.size();
    if (aggregated_edge_count < 0) aggregated_edge_count = 0;
    return grouped;
}

json compact_trace_error_warning(const std::string& query, int depth, const json& trace_resp) {
    json warning = {{"query", query}, {"depth", depth}, {"code", "TRACE_QUERY_FAILED"},
                    {"message", "trace query failed during expansion"}};
    if (trace_resp.contains("error") && trace_resp["error"].is_object()) {
        warning["code"] = trace_resp["error"].value("code", "TRACE_QUERY_FAILED");
        warning["message"] = trace_resp["error"].value("message", "trace query failed during expansion");
    }
    return warning;
}

// ═══════════════════════════════════════════════════════════════════════════
// semantic analysis
// ═══════════════════════════════════════════════════════════════════════════

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

json normalize_assignments_with_conditions(const json& trace_data) {
    json out = json::array();
    json controls = trace_data.value("control_dependencies", json::array());
    for (auto assignment : trace_data.value("assignments", json::array())) {
        json conditions = json::array();
        for (const auto& dep : controls) conditions.push_back(condition_from_control_dep(dep));
        assignment["active_conditions"] = conditions;
        assignment["rhs_signals"] = assignment.value("rhs_signals",
            signal_array_from_ast(assignment.value("rhs", json::object())));
        assignment["assignment_role"] = conditions.empty() ? "default_or_unconditional" : "branch_assignment";
        out.push_back(assignment);
    }
    return out;
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
        if (out["reset"].is_null() && (contains_word_like(sig, "rst") || contains_word_like(sig, "reset")))
            out["reset"] = sig;
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

// ═══════════════════════════════════════════════════════════════════════════
// source analysis
// ═══════════════════════════════════════════════════════════════════════════

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

}  // namespace detail
}  // namespace xdebug_design
