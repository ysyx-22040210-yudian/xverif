#include "combined/active_trace_service.h"
#include "api/response.h"
#include "runtime/work_dir.h"

#include "npi.h"
#include "npi_fsdb.h"
#include "npi_hdl.h"
#include "npi_L1.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <set>
#include <string>
#include <unistd.h>
#include <vector>

namespace xdebug {

namespace {

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
        if (saved_ >= 0) {
            dup2(saved_, STDOUT_FILENO);
            close(saved_);
        }
        if (sink_ >= 0) close(sink_);
    }

private:
    int saved_;
    int sink_;
};

std::string npi_string(int property, npiHandle handle) {
    const char* value = handle ? npi_get_str(property, handle) : nullptr;
    return value ? value : "";
}

std::string current_executable() {
    char path[4096] = {};
    ssize_t length = readlink("/proc/self/exe", path, sizeof(path) - 1);
    return length > 0 ? std::string(path, static_cast<size_t>(length)) : std::string("xdebug");
}

std::string handle_info(npiHandle handle) {
    const char* value = handle ? npi_ut_get_hdl_info(handle, true, false) : nullptr;
    return value ? value : "";
}

std::string statement_kind(int type) {
    switch (type) {
    case npiAssignment: return "assignment";
    case npiForce: return "force";
    case npiPort: return "port_boundary";
    case npiIf: return "if";
    case npiIfElse: return "if_else";
    case npiCase: return "case";
    case npiCaseItem: return "case_item";
    case npiEventControl: return "event_control";
    case npiRelease: return "release_candidate";
    default: return "other";
    }
}

bool is_control_kind(const std::string& kind) {
    return kind == "if" || kind == "if_else" ||
           kind == "case" || kind == "case_item";
}

bool parse_time(const std::string& text, double& value, std::string& unit) {
    char* end = nullptr;
    value = std::strtod(text.c_str(), &end);
    if (!end || end == text.c_str()) return false;
    while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
    unit = end;
    if (unit == "f") unit = "fs";
    else if (unit == "p") unit = "ps";
    else if (unit == "n") unit = "ns";
    else if (unit == "u") unit = "us";
    else if (unit == "m") unit = "ms";
    return !unit.empty();
}

Json value_map(npiFsdbFileHandle fsdb,
               const std::vector<std::string>& signals,
               const std::string& time_text,
               Json& limitations) {
    Json values = Json::object();
    double numeric_time = 0.0;
    std::string unit;
    npiFsdbTime time = 0;
    if (!parse_time(time_text, numeric_time, unit) ||
        !npi_fsdb_convert_time_in(fsdb, numeric_time, unit.c_str(), time)) {
        limitations.push_back("无法将时间 " + time_text + " 转换为 FSDB 时间");
        return values;
    }
    for (const auto& signal : signals) {
        npiFsdbSigHandle handle = npi_fsdb_sig_by_name(fsdb, signal.c_str(), nullptr);
        std::string raw;
        int rc = handle ? npi_fsdb_sig_hdl_value_at(handle, time, raw, npiFsdbBinStrVal) : 0;
        if (!handle || !rc) {
            values[signal] = nullptr;
            continue;
        }
        bool known = raw.find_first_of("xXzZ") == std::string::npos;
        values[signal] = {{"value", raw}, {"known", known}};
    }
    return values;
}

Json statement_json(const drvLoadStmt_s& statement, std::vector<std::string>& signals) {
    int type = statement.useHdl ? npi_get(npiType, statement.useHdl) : 0;
    Json out = {
        {"kind", statement_kind(type)},
        {"npi_type", type},
        {"file", npi_string(npiFile, statement.useHdl)},
        {"line", statement.useHdl ? npi_get(npiLineNo, statement.useHdl) : 0},
        {"text", handle_info(statement.useHdl)},
        {"signals", Json::array()}
    };
    std::set<std::string> already(signals.begin(), signals.end());
    for (const auto& handle : statement.sigHdlVec) {
        std::string name = npi_string(npiFullName, handle);
        if (name.empty()) name = npi_string(npiName, handle);
        if (name.empty()) continue;
        out["signals"].push_back(name);
        if (already.insert(name).second) signals.push_back(name);
    }
    return out;
}

Json parity_json(npiHandle signal,
                 const std::string& requested_time,
                 const trcOption_t& options,
                 const Json& baseline_statements) {
    Json result = {{"pvc_time", ""}, {"candidates", Json::array()}};
    const char* pvc = npi_get_pvc_time(signal, requested_time.c_str());
    if (!pvc) return result;
    result["pvc_time"] = pvc;
    drvLoadStmtVec_t candidates;
    npi_trace_driver_by_hdl2(signal, candidates, true, nullptr, options);
    for (const auto& candidate : candidates) {
        std::vector<std::string> ignored;
        Json item = statement_json(candidate, ignored);
        int rc = npi_check_active_handle(candidate.useHdl, pvc);
        item["active_check_rc"] = rc;
        item["classification"] = rc == 1 ? "active" : rc == 0 ? "inactive" : "unknown";
        result["candidates"].push_back(item);
    }
    result["baseline_statement_count"] = baseline_statements.size();
    return result;
}

} // namespace

Json ActiveTraceService::run(const Json& request, const Json& target) const {
    const std::string action = "trace.active_driver";
    const Json args = request.value("args", Json::object());
    const std::string daidir = target.value("daidir", std::string());
    const std::string fsdb_path = target.value("fsdb", std::string());
    const std::string signal_name = args.value("signal", std::string());
    const std::string requested_time = args.value("requested_time", std::string());
    if (daidir.empty() || fsdb_path.empty()) {
        return make_error(request, action, "RESOURCE_REQUIRED",
                          "trace.active_driver requires target.daidir and target.fsdb");
    }
    if (signal_name.empty() || requested_time.empty()) {
        return make_error(request, action, "MISSING_FIELD",
                          "args.signal and args.requested_time are required");
    }
    ScopedRuntimeWorkDir workdir("combined");
    if (!workdir.ok()) {
        return make_error(request, action, "WORKDIR_FAILED",
                          "failed to enter runtime working directory: " + workdir.path());
    }

    std::vector<std::string> npi_arg_strings = {
        current_executable(), "-dbdir", daidir, "-ssf", fsdb_path
    };
    std::vector<char*> npi_argv;
    for (auto& value : npi_arg_strings) npi_argv.push_back(const_cast<char*>(value.c_str()));
    int npi_argc = static_cast<int>(npi_argv.size());
    char** npi_argp = npi_argv.data();
    ScopedStdoutSilence silence;
    if (!npi_init(npi_argc, npi_argp)) {
        return make_error(request, action, "NPI_INIT_FAILED", "npi_init failed for combined session");
    }
    if (!npi_load_design(npi_argc, npi_argp)) {
        npi_end();
        return make_error(request, action, "DESIGN_LOAD_FAILED", "failed to load daidir with waveform binding");
    }
    npiFsdbFileHandle fsdb = npi_fsdb_open(fsdb_path.c_str());
    if (!fsdb) {
        npi_end();
        return make_error(request, action, "FSDB_OPEN_FAILED", "failed to open fsdb for value queries");
    }
    npiHandle signal = npi_handle_by_name(signal_name.c_str(), nullptr);
    if (!signal) {
        npi_fsdb_close(fsdb);
        npi_end();
        return make_error(request, action, "SIGNAL_NOT_FOUND", "exact design signal was not found: " + signal_name);
    }

    trcOption_t options = trcOptionDefault;
    options.reportControl = args.value("include_control", true);
    actTrcRes_t active = {};
    int active_count =
        npi_active_trace_driver_by_hdl(signal, active, requested_time.c_str(), options);

    Json statements = Json::array();
    Json controls = Json::array();
    Json path = Json::array();
    Json events = Json::array();
    Json driver = nullptr;
    std::vector<std::string> signals;
    signals.push_back(signal_name);
    for (const auto& statement : active.drvLoadStmtVec) {
        Json item = statement_json(statement, signals);
        const std::string kind = item.value("kind", std::string());
        statements.push_back(item);
        if ((kind == "assignment" || kind == "force") && driver.is_null()) driver = item;
        else if (kind == "port_boundary") path.push_back(item);
        else if (is_control_kind(kind)) controls.push_back(item);
        else if (kind == "event_control") events.push_back(item);
    }

    Json limitations = Json::array();
    std::string status = "unresolved";
    if (!driver.is_null()) status = "resolved";
    else if (!controls.empty()) {
        status = "control_only";
        limitations.push_back("已确认控制上下文和结果，但 NPI active 证据未确认具体赋值语句");
    } else if (active_count == 0) {
        limitations.push_back("active trace 未返回动态驱动证据");
    }
    if (!driver.is_null() && driver.value("kind", std::string()) == "force") {
        limitations.push_back("force 依据 statement 类型识别，未使用 actTrcRes_t.isForce");
    }

    Json response = make_response(request, action);
    response["session"] = {{"mode", "combined"}, {"daidir", daidir}, {"fsdb", fsdb_path}};
    response["summary"] = {
        {"signal", signal_name},
        {"requested_time", requested_time},
        {"active_time", active.activeTime},
        {"driver_status", status},
        {"statement_count", statements.size()}
    };
    response["data"] = {
        {"signal", signal_name},
        {"requested_time", requested_time},
        {"active_time", active.activeTime},
        {"driver_status", status},
        {"driver", driver},
        {"path", path},
        {"controls", controls},
        {"events", events},
        {"statements", statements},
        {"limitations", limitations}
    };
    response["data"]["active_values"] =
        active.activeTime.empty() ? Json::object() : value_map(fsdb, signals, active.activeTime, limitations);
    response["data"]["requested_values"] = value_map(fsdb, signals, requested_time, limitations);
    response["data"]["limitations"] = limitations;
    if (args.value("include_parity", false)) {
        response["data"]["parity"] = parity_json(signal, requested_time, options, statements);
    }

    npi_release_handle(signal);
    npi_fsdb_close(fsdb);
    npi_end();
    return response;
}

} // namespace xdebug
