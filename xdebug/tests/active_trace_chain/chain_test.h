#pragma once

#include <string>
#include <vector>

// ─── Candidate (for branch disambiguation) ──────────────────────────
struct Candidate {
    std::string name;
    std::string role;       // "data" or "control"
    std::string value_before;
    std::string value_at;
    bool toggled = false;
};

// ─── Branch evidence entry ───────────────────────────────────────────
struct BranchEvidence {
    std::string signal;
    std::string time;
    std::vector<Candidate> candidates;
    std::string decision_reason;
};

// ─── One hop in the trace chain ──────────────────────────────────────
struct ChainNode {
    int hop = 0;
    std::string signal;
    std::string requested_time;
    std::string active_time;
    std::string value;
    bool value_known = false;
    std::string driver_kind;     // "cont_assign", "proc_assign", "force",
                                 // "port_boundary", "primary_input", ...
    std::string file;
    int line = 0;
    std::string text;
    std::string hop_type;        // "same_time" or "temporal_boundary"
    std::string next_signal;
    std::string next_time;
};

// ─── Full chain result ───────────────────────────────────────────────
struct ChainResult {
    std::vector<ChainNode> chain;
    std::vector<BranchEvidence> branch_evidence;
    std::vector<std::string> limitations;
    std::string termination;     // "primary_input","assignment","force",
                                 // "ambiguous","limit","loop_detected",
                                 // "signal_not_found","control_only",
                                 // "unresolved"
    int active_trace_call_count = 0;
    int edgecheck_direct_count = 0;   // NPI returned unique candidate
    int fallback_0_5ns_count = 0;     // needed ±0.5ns disambiguation
    int temporal_boundary_stops = 0;  // stopped due to activeTime != T0
    int temporal_boundary_count = 0;
    int total_hops = 0;
    bool truncated = false;
};

// ─── Probe result (edgeCheck comparison) ─────────────────────────────
struct ProbeResult {
    std::string signal;
    std::string time;
    struct ModeResult {
        bool edge_check;
        int statement_count;
        std::vector<std::string> kinds;
        std::vector<std::string> data_signals;
        std::vector<std::string> control_signals;
    };
    ModeResult with_edge_check;
    ModeResult without_edge_check;
    std::vector<Candidate> toggled_check;  // ±0.5ns comparison
};
