#include "logging/action_log.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <unistd.h>

using xdebug_core::Json;

static std::string read_file(const std::string& path) {
    std::ifstream in(path.c_str());
    std::ostringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

static Json read_last_json_line(const std::string& path) {
    std::ifstream in(path.c_str());
    std::string line;
    std::string last;
    while (std::getline(in, line)) {
        if (!line.empty()) last = line;
    }
    assert(!last.empty());
    return Json::parse(last);
}

int main() {
    std::string home = "/tmp/xdebug_action_log_test_" + std::to_string(getpid());
    setenv("HOME", home.c_str(), 1);

    Json request = {
        {"api_version", "xdebug.v1"},
        {"action", "trace.driver"},
        {"target", {{"session_id", "case_a"}, {"daidir", "/tmp/foo.daidir"}}},
        {"args", {{"signal", "top.u.ready"}, {"include_trace", true}}},
        {"output", {{"verbosity", "compact"}}}
    };
    Json response = {
        {"ok", false},
        {"action", "trace.driver"},
        {"summary", {{"signal", "top.u.ready"}}},
        {"data", {{"trace", Json::array({1, 2, 3})}, {"small", true}}},
        {"error", {{"code", "SIGNAL_NOT_FOUND"}, {"message", "missing"}}},
        {"meta", {{"truncated", false}}}
    };

    Json sanitized = xdebug_core::sanitize_for_log(response);
    assert(sanitized["data"]["trace"] == "<omitted:large-field>");
    assert(sanitized.value("log_truncated", false));

    xdebug_core::update_public_session_manifest("case_a", "design", "/tmp/foo.daidir", "");
    std::string manifest_path = xdebug_core::public_session_dir("case_a") + "/session.json";
    Json manifest = Json::parse(read_file(manifest_path));
    assert(manifest["session_id"] == "case_a");
    assert(manifest["mode"] == "design");
    assert(manifest["daidir"] == "/tmp/foo.daidir");

    xdebug_core::log_action_event("public", "xdebug", "case_a", "trace.driver", "end", false, 12,
                                  {{"request", xdebug_core::request_summary_for_log(request)},
                                   {"response", xdebug_core::response_summary_for_log(response)},
                                   {"request_compact", xdebug_core::sanitize_for_log(request)},
                                   {"response_compact", xdebug_core::sanitize_for_log(response)}});
    Json event = read_last_json_line(xdebug_core::public_action_log_path("case_a"));
    assert(event["layer"] == "public");
    assert(event["component"] == "xdebug");
    assert(event["session_id"] == "case_a");
    assert(event["action"] == "trace.driver");
    assert(event["phase"] == "end");
    assert(event["ok"] == false);
    assert(event["elapsed_ms"] == 12);

    xdebug_core::log_lifecycle_event("waveform", "case_a", "npi_fsdb_open.failed", false,
                                     {{"fsdb", "/tmp/a.fsdb"}});
    Json lifecycle_event = read_last_json_line(xdebug_core::component_log_path("waveform", "case_a", "lifecycle"));
    assert(lifecycle_event["component"] == "waveform");
    assert(lifecycle_event["phase"] == "npi_fsdb_open.failed");

    return 0;
}
