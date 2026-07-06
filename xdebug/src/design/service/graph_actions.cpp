#include "action_support.h"
#include "design_postprocess.h"

#include <algorithm>
#include <map>
#include <set>
#include <sstream>
#include <vector>

namespace xdebug_design {

// Functions formerly here now live in design/service/design_postprocess.cpp
// (xdebug_design::detail namespace).  Re-exported via using for source compat.
namespace {
using detail::graph_from_trace;
using detail::confidence_for_edge;
using detail::evidence_from_edge;
using detail::explanation_from_edge;
using detail::edge_type_allowed;
using detail::edge_dedupe_key;
using detail::edge_relation_key;
using detail::aggregate_edges_by_relation;
using detail::compact_trace_error_warning;
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
        trace_req["args"]["include_trace"] = true;
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
    if (compact_mode(request) && !include_arg(request, "include_debug")) {
        response["summary"] = {{"root_signal", root}, {"direction", direction},
            {"node_count", graph["nodes"].size()}, {"edge_count", graph["edges"].size()},
            {"truncated", truncated}};
    }
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
        response["data"] = {{"explanations", explanations}};
        if (!compact_mode(request) || include_arg(request, "include_trace")) response["data"]["trace"] = trace;
        if (!compact_mode(request) || include_arg(request, "include_expanded_queries")) response["data"]["expanded_queries"] = expanded_queries;
        response["suggested_next_actions"] = json::array({{{"tool", "xdebug"}, {"action", "value.at"},
            {"reason", "verify dependency signal value at the observed waveform time"}, {"args", {{"signal", root}}}}});
    } else {
        response["data"] = {{"graph", graph}};
        if (!compact_mode(request) || include_arg(request, "include_trace")) response["data"]["trace"] = trace;
        if (!compact_mode(request) || include_arg(request, "include_expanded_queries")) response["data"]["expanded_queries"] = expanded_queries;
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
    if (compact_mode(request) && !include_arg(request, "include_graph")) {
        response["data"] = {{"found", found}, {"paths", paths}};
    } else {
        response["data"]["paths"] = paths;
        response["data"]["found"] = found;
    }
    return response;
}

} // namespace xdebug_design
