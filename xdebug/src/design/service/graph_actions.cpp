#include "action_support.h"

#include <algorithm>
#include <map>
#include <set>
#include <sstream>
#include <vector>

namespace xdebug_design {

namespace {

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

} // namespace

json trace_expand_like(const json& request, bool explain_only) {
    json response = base_response(request, request.value("action", ""));
    std::string session_id;
    SessionInfo session;
    if (!ensure_target_session(request, response, session_id, session)) return response;
    json args = request.value("args", json::object());
    std::string root = args.value("root_signal", args.value("signal", ""));
    std::string direction = args.value("direction", "driver");
    if (root.empty()) return error_response(request, request.value("action", ""), "MISSING_FIELD", "args.root_signal or args.signal is required");
    const json limits = request.value("limits", json::object());
    int max_depth = std::max(1, limits.value("max_depth", 1));
    int max_nodes = std::max(1, limits.value("max_nodes", 100));
    int max_edges = std::max(1, limits.value("max_edges", limits.value("max_results", 200)));
    int max_evidence_per_edge = std::max(1, limits.value("max_evidence_per_edge", 3));
    json all_edges = json::array();
    json expanded_queries = json::array();
    std::set<std::string> visited;
    std::set<std::string> seen_edges;
    std::vector<std::pair<std::string, int>> queue = {{root, 0}};
    bool truncated = false;
    int reached_depth = 0;
    int raw_edge_count = 0;
    int duplicate_edge_count = 0;
    int failed_query_count = 0;
    std::string first_confidence = "unknown";
    for (size_t qi = 0; qi < queue.size(); ++qi) {
        std::string current = queue[qi].first;
        int depth = queue[qi].second;
        reached_depth = std::max(reached_depth, depth);
        if (visited.count(current)) continue;
        if ((int)visited.size() >= max_nodes) {
            truncated = true;
            break;
        }
        visited.insert(current);
        if (depth >= max_depth) continue;
        json trace_req = request;
        trace_req["action"] = direction == "load" ? "trace.load" : "trace.driver";
        trace_req["target"] = {{"session_id", session_id}};
        trace_req["args"]["signal"] = current;
        json trace_resp = run_trace_action(trace_req, direction == "load" ? "load" : "driver");
        if (!trace_resp.value("ok", false)) {
            failed_query_count++;
            if (depth == 0) {
                response["ok"] = false;
                response["summary"] = {{"root_signal", root}, {"direction", direction}, {"depth", reached_depth},
                    {"node_count", 1}, {"edge_count", 0}, {"raw_edge_count", 0}, {"deduped_edge_count", 0},
                    {"duplicate_edge_count", 0}, {"relation_group_count", 0}, {"aggregated_edge_count", 0},
                    {"failed_query_count", failed_query_count}, {"truncated", false}};
                response["data"] = {{"graph", {{"nodes", json::array({{{"id", "n0"}, {"signal", root},
                    {"kind", "signal"}, {"role", "root"}}})}, {"edges", json::array()}}},
                    {"trace", {{"query", root}, {"mode", direction}, {"dependency_edges", json::array()},
                    {"confidence", "unknown"}, {"truncated", false}}}, {"expanded_queries", json::array()}};
                response["error"] = trace_resp.value("error", json({{"code", "TRACE_QUERY_FAILED"},
                    {"message", "trace query failed during expansion"}, {"recoverable", true}}));
                response["warnings"].push_back(compact_trace_error_warning(current, depth, trace_resp));
                return response;
            }
            response["warnings"].push_back(compact_trace_error_warning(current, depth, trace_resp));
            continue;
        }
        json trace = trace_resp["data"];
        if (first_confidence == "unknown") first_confidence = trace.value("confidence", "unknown");
        json trace_edges = trace.value("dependency_edges", json::array());
        expanded_queries.push_back({{"query", trace.value("query", current)}, {"depth", depth},
            {"edge_count", trace_edges.size()}, {"truncated", trace.value("truncated", false)},
            {"confidence", trace.value("confidence", "unknown")}});
        if (trace.value("truncated", false)) truncated = true;
        for (const auto& e : trace_edges) {
            if (!edge_type_allowed(args, e)) continue;
            if ((int)all_edges.size() >= max_edges) { truncated = true; break; }
            raw_edge_count++;
            if (!seen_edges.insert(edge_dedupe_key(e)).second) { duplicate_edge_count++; continue; }
            all_edges.push_back(e);
            std::string next = direction == "load" ? e.value("to", "") : e.value("from", "");
            if (!next.empty() && !visited.count(next) && (int)queue.size() < max_nodes) queue.push_back({next, depth + 1});
            else if ((int)queue.size() >= max_nodes) truncated = true;
        }
        if ((int)all_edges.size() >= max_edges) { truncated = true; break; }
    }
    int aggregated_edge_count = 0;
    json relation_edges = aggregate_edges_by_relation(all_edges, max_evidence_per_edge, aggregated_edge_count);
    json trace = {{"query", root}, {"mode", direction}, {"dependency_edges", relation_edges},
                  {"confidence", first_confidence}, {"truncated", truncated}};
    json graph = graph_from_trace(trace, root);
    response["summary"] = {{"root_signal", root}, {"direction", direction}, {"depth", reached_depth},
        {"node_count", graph["nodes"].size()}, {"edge_count", graph["edges"].size()},
        {"raw_edge_count", raw_edge_count}, {"deduped_edge_count", all_edges.size()},
        {"duplicate_edge_count", duplicate_edge_count}, {"relation_group_count", relation_edges.size()},
        {"aggregated_edge_count", aggregated_edge_count}, {"failed_query_count", failed_query_count},
        {"truncated", truncated}};
    response["meta"]["truncated"] = truncated;
    if (explain_only) {
        json explanations = json::array();
        int skipped_empty_dependency_count = 0;
        for (const auto& e : trace.value("dependency_edges", json::array())) {
            json explanation = explanation_from_edge(e, root, direction, skipped_empty_dependency_count);
            if (!explanation.is_null()) explanations.push_back(explanation);
        }
        response["summary"]["explanation_count"] = explanations.size();
        response["summary"]["skipped_empty_dependency_count"] = skipped_empty_dependency_count;
        response["data"] = {{"explanations", explanations}, {"trace", trace}, {"expanded_queries", expanded_queries}};
        response["suggested_next_actions"] = json::array({{{"tool", "xdebug"}, {"action", "value.at"},
            {"reason", "verify dependency signal value at the observed waveform time"}, {"args", {{"signal", root}}}}});
    } else {
        response["data"] = {{"graph", graph}, {"trace", trace}, {"expanded_queries", expanded_queries}};
    }
    return response;
}

json trace_path(const json& request) {
    json args = request.value("args", json::object());
    std::string from = args.value("from_signal", "");
    std::string to = args.value("to_signal", "");
    json expand_req = request;
    if (!args.contains("root_signal") && !args.contains("signal") && !to.empty()) expand_req["args"]["root_signal"] = to;
    json response = trace_expand_like(expand_req, false);
    if (!response.value("ok", false)) return response;
    int max_paths = request.value("limits", json::object()).value("max_paths", 10);
    if (max_paths <= 0) max_paths = 10;
    bool found = false;
    json paths = json::array();
    json edges = response["data"]["graph"].value("edges", json::array());
    if (from.empty() || to.empty()) {
        for (const auto& e : edges) {
            if ((from.empty() || e.value("from_signal", "") == from) &&
                (to.empty() || e.value("to_signal", "") == to)) {
                found = true;
                paths.push_back(json::array({e}));
                if ((int)paths.size() >= max_paths) break;
            }
        }
    } else {
        std::vector<json> edge_vec;
        for (const auto& e : edges) edge_vec.push_back(e);
        std::vector<std::pair<std::string, json>> queue = {{from, json::array()}};
        std::set<std::string> visited;
        for (size_t qi = 0; qi < queue.size() && (int)paths.size() < max_paths; ++qi) {
            std::string current = queue[qi].first;
            json path = queue[qi].second;
            if (current == to) { found = true; paths.push_back(path); continue; }
            if (visited.count(current)) continue;
            visited.insert(current);
            for (const auto& e : edge_vec) {
                if (e.value("from_signal", "") != current) continue;
                std::string next = e.value("to_signal", "");
                if (next.empty()) continue;
                json next_path = path;
                next_path.push_back(e);
                queue.push_back({next, next_path});
            }
        }
    }
    if (!found) {
        for (const auto& e : edges) {
            if ((from.empty() || e.value("from_signal", "") == from) &&
                (to.empty() || e.value("to_signal", "") == to)) {
                found = true;
                paths.push_back(json::array({e}));
                break;
            }
        }
    }
    response["summary"]["from_signal"] = from;
    response["summary"]["to_signal"] = to;
    response["summary"]["path_count"] = paths.size();
    response["summary"]["found"] = found;
    response["data"]["paths"] = paths;
    return response;
}

} // namespace xdebug_design
