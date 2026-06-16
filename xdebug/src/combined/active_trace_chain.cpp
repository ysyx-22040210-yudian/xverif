#include "combined/active_trace_chain.h"
#include "api/response.h"
#include "api/text_response_builder.h"
#include "runtime/work_dir.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_hdl.h"
#include "npi_L1.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <set>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

namespace xdebug {

namespace {

// ═══════════════════════════════════════════════════════════════════
// RAII guards (shared with active_trace_service.cpp)
// ═══════════════════════════════════════════════════════════════════

class ScopedStdoutSilence {
public:
    ScopedStdoutSilence() : saved_(-1), sink_(-1) {
        std::fflush(stdout);
        saved_ = dup(STDOUT_FILENO);
        sink_ = open("/dev/null", O_WRONLY);
        if (saved_ >= 0 && sink_ >= 0) dup2(sink_, STDOUT_FILENO);
    }
    ~ScopedStdoutSilence() {
        std::fflush(stdout);
        if (saved_ >= 0) { dup2(saved_, STDOUT_FILENO); close(saved_); }
        if (sink_ >= 0) close(sink_);
    }
private:
    int saved_, sink_;
};

class NpiSessionGuard {
public:
    ~NpiSessionGuard() { if (loaded_) npi_end(); }
    bool init(int argc, char** argv) {
        if (!npi_init(argc, argv)) return false;
        loaded_ = true; return true;
    }
    bool load_design(int argc, char** argv) {
        return loaded_ && npi_load_design(argc, argv) != 0;
    }
private:
    bool loaded_ = false;
};

class FsdbFileGuard {
public:
    explicit FsdbFileGuard(const std::string& p) : h_(npi_fsdb_open(p.c_str())) {}
    ~FsdbFileGuard() { if (h_) npi_fsdb_close(h_); }
    npiFsdbFileHandle get() const { return h_; }
    explicit operator bool() const { return h_ != nullptr; }
private:
    npiFsdbFileHandle h_ = nullptr;
};

class NpiHandleGuard {
public:
    explicit NpiHandleGuard(npiHandle h = nullptr) : h_(h) {}
    ~NpiHandleGuard() { if (h_) npi_release_handle(h_); }
    npiHandle get() const { return h_; }
private:
    npiHandle h_ = nullptr;
};

// ═══════════════════════════════════════════════════════════════════
// NPI helpers
// ═══════════════════════════════════════════════════════════════════

std::string npi_str(int prop, npiHandle h) {
    const char* s = h ? npi_get_str(prop, h) : nullptr;
    return s ? s : "";
}

std::string current_exe() {
    char path[4096] = {};
    ssize_t n = readlink("/proc/self/exe", path, sizeof(path) - 1);
    return n > 0 ? std::string(path, static_cast<size_t>(n)) : "xdebug";
}

std::string hdl_text(npiHandle h) {
    const char* s = h ? npi_ut_get_hdl_info(h, true, false) : nullptr;
    return s ? s : "";
}

// ─── driver text (human-friendly, not raw NPI) ───

std::string driver_text(npiHandle stmt_hdl, const std::string& kind) {
    if (!stmt_hdl) return "(primary input)";
    std::string raw = hdl_text(stmt_hdl);
    // strip "npiXxx, " prefix
    size_t comma = raw.find(", ");
    if (comma != std::string::npos) raw = raw.substr(comma + 2);
    // strip " {/path/file : N}" suffix
    size_t brace = raw.rfind(" {");
    if (brace != std::string::npos) raw = raw.substr(0, brace);
    if (raw.empty()) return "(" + kind + ")";
    return raw;
}

std::string stmt_kind(int type) {
    switch (type) {
    case npiContAssign:   return "cont_assign";
    case npiAssignment:   return "proc_assign";
    case npiForce:        return "force";
    case npiPort:         return "port_boundary";
    case npiIf:           return "if";
    case npiIfElse:       return "if_else";
    case npiCase:         return "case";
    case npiCaseItem:     return "case_item";
    case npiEventControl: return "event_control";
    default:
        if (type == 697) return "modport_port";
        if (type == 608) return "ref_obj";
        return "other";
    }
}

bool parse_time(const std::string& s, double& val, std::string& unit) {
    char* end = nullptr;
    val = std::strtod(s.c_str(), &end);
    if (!end || end == s.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit == "f") unit = "fs"; else if (unit == "p") unit = "ps";
    else if (unit == "n") unit = "ns"; else if (unit == "u") unit = "us";
    else if (unit == "m") unit = "ms";
    return !unit.empty();
}

// ═══════════════════════════════════════════════════════════════════
// FSDB value query (for ±half-period comparison)
// ═══════════════════════════════════════════════════════════════════

std::string fsdb_value_at(npiFsdbFileHandle fsdb,
                           const std::string& sig_name,
                           const std::string& time_str) {
    npiFsdbSigHandle sh = npi_fsdb_sig_by_name(fsdb, sig_name.c_str(), nullptr);
    if (!sh) return "";
    double tv; std::string unit;
    if (!parse_time(time_str, tv, unit)) return "";
    npiFsdbTime ft = 0;
    if (!npi_fsdb_convert_time_in(fsdb, tv, unit.c_str(), ft)) return "";
    std::string raw;
    int rc = npi_fsdb_sig_hdl_value_at(sh, ft, raw, npiFsdbBinStrVal);
    return rc ? raw : "";
}

std::string make_time_str(double val, const std::string& unit) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%.2f%s", val, unit.c_str());
    return buf;
}

// ═══════════════════════════════════════════════════════════════════
// data types
// ═══════════════════════════════════════════════════════════════════

struct Candidate {
    std::string name;
    std::string value_before, value_at;
    bool toggled = false;
};

struct BranchEvidence {
    std::string signal, time, reason;
    std::vector<Candidate> candidates;
};

struct ChainNode {
    int index = 0;
    std::string signal, time, active_time;
    std::string value_str;
    bool value_known = false;
    std::string driver_kind, driver, file;
    int line = 0;
    std::string hop;     // "→" | "⏱" | "■"
    std::string next;
};

struct ChainStats {
    int calls = 0;
    int edgecheck_direct = 0;
    int fallback = 0;
    int temporal_boundaries = 0;
};

struct ChainResult {
    std::vector<ChainNode> chain;
    std::vector<BranchEvidence> branch_evidence;
    std::vector<std::string> limitations;
    std::string termination = "unresolved";
    ChainStats stats;
    bool truncated = false;
};

struct Decision {
    bool stop = false;
    std::string reason;
    std::string next_signal;
    BranchEvidence evidence;
};

// ═══════════════════════════════════════════════════════════════════
// core: decide next hop
// ═══════════════════════════════════════════════════════════════════

Decision decide_next(npiFsdbFileHandle fsdb,
                      const std::string& signal,
                      const std::string& time,
                      const std::string& clk_period,
                      const std::vector<std::string>& data_signals,
                      const std::string& driver_kind,
                      ChainStats& stats) {
    Decision d;

    if (driver_kind == "force") {
        d.stop = true;
        d.reason = "force";
        return d;
    }

    if (data_signals.empty()) {
        d.stop = true;
        d.reason = "primary_input";
        return d;
    }

    if (data_signals.size() == 1) {
        d.next_signal = data_signals[0];
        stats.edgecheck_direct++;
        return d;
    }

    // ≥2 candidates → ±half-period comparison
    stats.fallback++;

    double tv; std::string unit;
    if (!parse_time(time, tv, unit)) {
        d.stop = true; d.reason = "unresolved"; return d;
    }

    double cpv; std::string cpu;
    if (!parse_time(clk_period, cpv, cpu)) {
        d.stop = true; d.reason = "unresolved"; return d;
    }

    double half = cpv / 2.0;
    std::string t_before = make_time_str(tv - half, unit);
    std::string t_after  = make_time_str(tv + half, unit);

    BranchEvidence ev;
    ev.signal = signal; ev.time = time;
    int toggled_count = 0;
    std::string last_toggled;

    for (auto& name : data_signals) {
        Candidate c;
        c.name = name;
        c.value_before = fsdb_value_at(fsdb, name, t_before);
        c.value_at     = fsdb_value_at(fsdb, name, t_after);
        c.toggled = (c.value_before != c.value_at);
        if (c.toggled) { toggled_count++; last_toggled = name; }
        ev.candidates.push_back(c);
    }

    if (toggled_count == 1) {
        d.next_signal = last_toggled;
        return d;
    }

    d.stop = true;
    d.reason = "ambiguous";
    d.evidence = ev;
    d.evidence.reason = std::to_string(toggled_count) + " signals toggled simultaneously";
    return d;
}

// ═══════════════════════════════════════════════════════════════════
// core: build chain
// ═══════════════════════════════════════════════════════════════════

ChainResult build_chain(npiFsdbFileHandle fsdb,
                         const std::string& signal,
                         const std::string& time,
                         const std::string& clk_period,
                         int max_depth, int max_nodes) {
    ChainResult result;

    struct Hop { std::string sig, t; int depth; };
    std::vector<Hop> queue;
    queue.push_back({signal, time, 0});
    std::set<std::string> visited;
    visited.insert(signal);

    trcOption_t opt = trcOptionDefault;
    opt.reportControl = true;

    while (!queue.empty()) {
        Hop cur = queue.front();
        queue.erase(queue.begin());

        if (cur.depth > max_depth || static_cast<int>(result.chain.size()) >= max_nodes) {
            result.truncated = true;
            result.termination = "limit";
            break;
        }

        // ── trace this hop ──
        npiHandle hdl = npi_handle_by_name(cur.sig.c_str(), nullptr);
        if (!hdl) {
            result.termination = "signal_not_found";
            result.limitations.push_back("signal not found: " + cur.sig);
            break;
        }

        actTrcRes_t active = {};
        result.stats.calls++;
        npi_active_trace_driver_by_hdl(hdl, active, cur.t.c_str(), opt);
        npi_release_handle(hdl);

        bool temporal = (active.activeTime != cur.t);
        if (temporal) result.stats.temporal_boundaries++;

        std::string active_time = active.activeTime.empty() ? cur.t : active.activeTime;

        // read value
        std::string raw_val = fsdb_value_at(fsdb, cur.sig, active_time);
        bool known = raw_val.find_first_of("xXzZ") == std::string::npos;
        std::string val_disp = raw_val;
        if (known && !raw_val.empty()) {
            unsigned long long v = 0;
            for (char c : raw_val) { v <<= 1; if (c == '1') v |= 1; }
            std::stringstream ss;
            ss << raw_val.size() << "'h" << std::hex << v;
            val_disp = ss.str();
        }

        // classify statements
        std::string best_kind, best_driver, best_file;
        int best_line = 0;
        std::vector<std::string> all_signals;

        for (auto& stmt : active.drvLoadStmtVec) {
            int type = stmt.useHdl ? npi_get(npiType, stmt.useHdl) : 0;
            std::string kind = stmt_kind(type);

            if (best_kind.empty() ||
                kind == "cont_assign" || kind == "proc_assign" || kind == "force") {
                best_kind = kind;
                best_driver = driver_text(stmt.useHdl, kind);
                best_file = npi_str(npiFile, stmt.useHdl);
                best_line = stmt.useHdl ? npi_get(npiLineNo, stmt.useHdl) : 0;
            }

            for (auto& sh : stmt.sigHdlVec) {
                std::string n = npi_str(npiFullName, sh);
                if (!n.empty())
                    all_signals.push_back(n);
            }
        }

        // dedup signals
        std::sort(all_signals.begin(), all_signals.end());
        all_signals.erase(std::unique(all_signals.begin(), all_signals.end()), all_signals.end());

        // extract data candidates (exclude current signal)
        std::vector<std::string> data_signals;
        for (auto& s : all_signals)
            if (s != cur.sig) data_signals.push_back(s);

        // ── build chain node ──
        ChainNode node;
        node.index = static_cast<int>(result.chain.size());
        node.signal = cur.sig;
        node.time = cur.t;
        node.active_time = active_time;
        node.value_str = val_disp;
        node.value_known = known;
        node.driver_kind = best_kind.empty() ? "unresolved" : best_kind;
        node.driver = best_driver.empty() ? "(no driver)" : best_driver;
        node.file = best_file;
        node.line = best_line;

        // ── decide next ──
        Decision d = decide_next(fsdb, cur.sig, cur.t, clk_period,
                                  data_signals, best_kind, result.stats);

        if (d.stop) {
            result.termination = d.reason;
            node.hop = "■";
            if (!d.evidence.candidates.empty())
                result.branch_evidence.push_back(d.evidence);
            result.chain.push_back(node);
            break;
        }

        node.hop = temporal ? "⏱" : "→";
        node.next = d.next_signal;
        result.chain.push_back(node);

        if (visited.count(d.next_signal)) {
            result.termination = "loop_detected";
            result.limitations.push_back("loop: " + cur.sig + " → " + d.next_signal);
            break;
        }
        visited.insert(d.next_signal);
        queue.push_back({d.next_signal, active_time, cur.depth + 1});
    }

    if (result.termination == "unresolved" && result.chain.empty())
        result.termination = "unresolved";
    return result;
}

// ═══════════════════════════════════════════════════════════════════
// JSON output
// ═══════════════════════════════════════════════════════════════════

Json chain_to_json(const ChainResult& r) {
    Json chain_arr = Json::array();
    for (auto& n : r.chain) {
        Json j;
        j["index"] = n.index;
        j["signal"] = n.signal;
        j["time"] = n.time;
        j["active_time"] = n.active_time;
        j["value"] = n.value_str;
        j["value_known"] = n.value_known;
        j["driver_kind"] = n.driver_kind;
        j["driver"] = n.driver;
        j["file"] = n.file;
        j["line"] = n.line;
        j["hop"] = n.hop;
        j["next"] = n.next;
        chain_arr.push_back(j);
    }

    Json be_arr = Json::array();
    for (auto& be : r.branch_evidence) {
        Json j;
        j["signal"] = be.signal; j["time"] = be.time;
        j["reason"] = be.reason;
        Json cands = Json::array();
        for (auto& c : be.candidates) {
            Json cj;
            cj["name"] = c.name;
            cj["before"] = c.value_before;
            cj["after"] = c.value_at;
            cj["toggled"] = c.toggled;
            cands.push_back(cj);
        }
        j["candidates"] = cands;
        be_arr.push_back(j);
    }

    Json stats;
    stats["calls"] = r.stats.calls;
    stats["edgecheck_direct"] = r.stats.edgecheck_direct;
    stats["fallback"] = r.stats.fallback;
    stats["temporal_boundaries"] = r.stats.temporal_boundaries;

    Json data;
    data["chain"] = chain_arr;
    data["branch_evidence"] = be_arr;
    data["stats"] = stats;
    data["limitations"] = r.limitations;
    data["truncated"] = r.truncated;
    return data;
}

// ═══════════════════════════════════════════════════════════════════
// XOUT output
// ═══════════════════════════════════════════════════════════════════

std::string chain_to_xout(const std::string& signal, const std::string& time,
                           const ChainResult& r) {
    TextResponseBuilder xout("xdebug");

    // header line
    std::string header = signal + " @" + time + " → " + r.termination
                       + "  " + std::to_string(r.chain.size()) + " hops";
    xout.emit_header(header);

    // chain body
    xout.emit_section("chain");
    for (auto& n : r.chain) {
        std::string file_line = n.file;
        if (n.line > 0) file_line += ":" + std::to_string(n.line);
        if (file_line.size() > 45) file_line = "..." + file_line.substr(file_line.size() - 42);

        xout.emit_row({
            std::to_string(n.index) + " " + n.hop,
            n.signal,
            n.active_time,
            n.value_str,
            n.driver,
            file_line
        });
    }

    // stats
    xout.emit_section("stats");
    xout.emit_kv("calls", r.stats.calls);
    xout.emit_kv("edgecheck_direct", r.stats.edgecheck_direct);
    xout.emit_kv("fallback", r.stats.fallback);
    xout.emit_kv("temporal_boundaries", r.stats.temporal_boundaries);
    if (r.truncated) xout.emit_kv("truncated", "true");

    // branch evidence
    if (!r.branch_evidence.empty()) {
        xout.emit_section("branch_evidence");
        for (auto& be : r.branch_evidence) {
            xout.emit_kv("signal", be.signal);
            xout.emit_kv("time", be.time);
            xout.emit_kv("reason", be.reason);
            for (auto& c : be.candidates) {
                std::string toggle = c.toggled ? " ✓" : "  ";
                xout.emit_row({toggle, c.name, c.value_before, "→", c.value_at});
            }
        }
    }

    return xout.str();
}

} // namespace

// ═══════════════════════════════════════════════════════════════════
// public run()
// ═══════════════════════════════════════════════════════════════════

Json ActiveTraceChainService::run(const Json& request, const Json& target) const {
    const std::string action = "trace.active_driver_chain";
    Json args = request.value("args", Json::object());
    std::string daidir = target.value("daidir", "");
    std::string fsdb_path = target.value("fsdb", "");
    std::string signal = args.value("signal", "");
    std::string req_time = args.value("requested_time", "");
    std::string clk_period = args.value("clk_period", "10ns");

    if (daidir.empty() || fsdb_path.empty())
        return make_error(request, action, "RESOURCE_REQUIRED",
                          "requires target.daidir and target.fsdb");
    if (signal.empty() || req_time.empty())
        return make_error(request, action, "MISSING_FIELD",
                          "requires args.signal and args.requested_time");

    // limits
    Json limits_j = args.value("limits", Json::object());
    int max_depth = std::max(1, limits_j.value("max_depth", 20));
    int max_nodes = std::max(1, limits_j.value("max_nodes", 50));

    ScopedRuntimeWorkDir workdir("combined");
    if (!workdir.ok())
        return make_error(request, action, "WORKDIR_FAILED",
                          "failed to enter runtime working directory");

    // NPI init
    std::vector<std::string> npi_args_str = {current_exe(), "-dbdir", daidir, "-ssf", fsdb_path};
    std::vector<char*> npi_argv;
    for (auto& s : npi_args_str) npi_argv.push_back(const_cast<char*>(s.c_str()));
    int npi_argc = static_cast<int>(npi_argv.size());
    char** npi_argv_ptr = npi_argv.data();

    ScopedStdoutSilence silence;
    NpiSessionGuard npi;
    if (!npi.init(npi_argc, npi_argv_ptr))
        return make_error(request, action, "NPI_INIT_FAILED", "npi_init failed");
    if (!npi.load_design(npi_argc, npi_argv_ptr))
        return make_error(request, action, "DESIGN_LOAD_FAILED", "npi_load_design failed");

    FsdbFileGuard fsdb(fsdb_path);
    if (!fsdb)
        return make_error(request, action, "FSDB_OPEN_FAILED", "npi_fsdb_open failed");

    NpiHandleGuard sig_hdl(npi_handle_by_name(signal.c_str(), nullptr));
    if (!sig_hdl.get())
        return make_error(request, action, "SIGNAL_NOT_FOUND", "signal not found: " + signal);

    // build chain
    ChainResult result = build_chain(fsdb.get(), signal, req_time, clk_period,
                                      max_depth, max_nodes);

    // output
    bool use_json = request.value("output", Json::object()).value("format", "xout") == "json";

    if (use_json) {
        Json resp = make_response(request, action);
        resp["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};
        resp["summary"] = {
            {"signal", signal},
            {"start_time", req_time},
            {"chain_length", result.chain.size()},
            {"termination", result.termination},
            {"temporal_boundaries", result.stats.temporal_boundaries}
        };
        resp["data"] = chain_to_json(result);
        resp["meta"]["truncated"] = result.truncated;
        return resp;
    } else {
        std::string xout = chain_to_xout(signal, req_time, result);
        // return as JSON with xout string in a special field, or as raw text
        Json resp = make_response(request, action);
        resp["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};
        resp["summary"] = {
            {"signal", signal},
            {"start_time", req_time},
            {"chain_length", result.chain.size()},
            {"termination", result.termination},
            {"temporal_boundaries", result.stats.temporal_boundaries}
        };
        resp["data"] = chain_to_json(result);
        resp["text"] = xout;
        resp["meta"]["truncated"] = result.truncated;
        return resp;
    }
}

} // namespace xdebug
