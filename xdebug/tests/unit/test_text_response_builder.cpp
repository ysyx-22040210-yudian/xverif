#include "api/text_response_builder.h"
#include "api/xout_renderer.h"

#include <cassert>
#include <string>

using namespace xdebug;

int main() {
    TextResponseBuilder out("xdebug");
    out.emit_header("trace.driver");
    out.emit_section("summary");
    out.emit_kv("signal", "top.u.valid");
    out.emit_kv("known", true);
    out.emit_kv("count", 2);
    out.emit_kv("empty", Json::array());
    out.emit_section("rows");
    out.emit_row({"n0", "top.u.valid", "reg with spaces"});
    out.emit_warning("W", "line1\nline2");
    std::string text = out.str();
    assert(text.find("@xdebug.trace.driver.v1") == 0);
    assert(text.find("summary:\n  signal: top.u.valid\n  known: true\n  count: 2") != std::string::npos);
    assert(text.find("rows:\n  n0 top.u.valid reg with spaces") != std::string::npos);
    assert(text.find("W line1\\nline2") != std::string::npos);
    assert(text.find("empty") == std::string::npos);

    Json response = {
        {"api_version", "xdebug.v1"},
        {"ok", true},
        {"action", "value.at"},
        {"data", {
            {"signal", "top.clk"},
            {"time", "10ns"},
            {"value", "1"},
            {"known", true}
        }}
    };
    text = render_xout_response(response);
    assert(text.find("@xdebug.value.at.v1") == 0);
    assert(text.find("target:\n  signal: top.clk\n  time: 10ns") != std::string::npos);
    assert(text.find("summary:\n  value: 1\n  known: true") != std::string::npos);

    Json error = {
        {"ok", false},
        {"action", "trace.driver"},
        {"error", {
            {"code", "SIGNAL_NOT_FOUND"},
            {"message", "missing\nsignal"},
            {"recoverable", true}
        }}
    };
    text = render_xout_response(error);
    assert(text.find("@xdebug.error.v1") == 0);
    assert(text.find("action: trace.driver") != std::string::npos);
    assert(text.find("code: SIGNAL_NOT_FOUND") != std::string::npos);
    assert(text.find("message: missing\\nsignal") != std::string::npos);
    return 0;
}
