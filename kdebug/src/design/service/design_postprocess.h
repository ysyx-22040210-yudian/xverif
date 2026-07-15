#pragma once

// Pure JSON transformation functions extracted from design/service/*.cpp.
// No I/O and no backend handles. Safe to call from service handlers.
//
// All functions use nlohmann::json (kdebug_design::json).

#include "action_support.h"

#include <set>
#include <string>
#include <vector>

namespace kdebug_design {
namespace detail {

// ── graph building ─────────────────────────────────────────────────────

json graph_from_trace(const json& trace, const std::string& root);

// ── edge processing ─────────────────────────────────────────────────────

std::string confidence_for_edge(const json& edge);
json evidence_from_edge(const json& edge);
json explanation_from_edge(const json& edge,
                           const std::string& root,
                           const std::string& direction,
                           int& skipped_empty_dependency_count);
bool edge_type_allowed(const json& args, const json& edge);
std::string edge_dedupe_key(const json& edge);
std::string edge_relation_key(const json& edge);
json aggregate_edges_by_relation(const json& edges,
                                 int max_evidence_per_edge,
                                 int& aggregated_edge_count);
json compact_trace_error_warning(const std::string& query, int depth,
                                 const json& trace_resp);

// ── semantic analysis ───────────────────────────────────────────────────

json condition_from_control_dep(const json& dep);
json normalize_assignments_with_conditions(const json& trace_data);
json infer_clock_reset_from_assignment(const json& assignment,
                                       const json& control_deps);
std::string classify_update_rule(const json& assignment,
                                 const json& condition,
                                 const std::string& target);

// ── source analysis ─────────────────────────────────────────────────────

json infer_enclosing_block(const std::vector<std::string>& lines, int line);

}  // namespace detail
}  // namespace kdebug_design
