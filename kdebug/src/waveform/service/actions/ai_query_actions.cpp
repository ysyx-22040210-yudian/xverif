#include "../action_handler.h"
#include "../action_support.h"
#include "../command_builder.h"
#include "../../protocol/protocol.h"

namespace kdebug_waveform {

namespace {

class AiQueryAction : public WaveformActionHandler {
public:
    explicit AiQueryAction(const char* name) : name_(name) {}
    const char* action_name() const override { return name_; }

    int run(const WaveformActionContext& ctx) const override {
        std::string err;
        Json data;
        std::string cmd = CommandBuilder(CMD_AI_QUERY).arg(ctx.req.dump()).build();

        if (!capture_server_json(ctx.sid, cmd, data, err)) {
            std::string code = err.find("Signal not found") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("Clock signal not found") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("SIGNAL_NOT_FOUND") != std::string::npos ? "SIGNAL_NOT_FOUND" :
                               err.find("CURSOR_NOT_FOUND") != std::string::npos ? "CURSOR_NOT_FOUND" :
                               err.find("TIME_OUT_OF_RANGE") != std::string::npos ? "TIME_OUT_OF_RANGE" :
                               err.find("CLOCK_OFFSET_UNSUPPORTED") != std::string::npos ? "CLOCK_OFFSET_UNSUPPORTED" :
                               err.find("TIME_SPEC_INVALID") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("INVALID_REQUEST") != std::string::npos ? "INVALID_REQUEST" :
                               err.find("MISSING_FIELD") != std::string::npos ? "MISSING_FIELD" :
                               err.find("Invalid time") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("Invalid TimeSpec") != std::string::npos ? "TIME_SPEC_INVALID" :
                               err.find("config not found") != std::string::npos ? "INVALID_REQUEST" :
                               err.find("expression") != std::string::npos ? "EXPR_PARSE_FAILED" :
                               "WAVE_QUERY_FAILED";
            return print_error_and_return(ctx.req, ctx.action, code, err, ctx.elapsed_ms);
        }

        Json out = base_response(ctx.req, ctx.action, true, ctx.elapsed_ms);
        fill_session(out, ctx.info);
        out["data"] = data;

        // Add resolved time range if applicable
        std::string begin_spec, end_spec, range_err;
        bool around_window = false;
        if (build_range_specs(ctx.args, begin_spec, end_spec, around_window, range_err) &&
            (ctx.args.contains("time_range") || ctx.args.contains("begin") || ctx.args.contains("end") || ctx.args.contains("around"))) {
            fill_resolved_range(out, ctx.sid, begin_spec, end_spec, around_window, range_err);
        }

        // Add resolved time point if applicable
        std::string at_spec = string_or(ctx.args, "at", string_or(ctx.args, "time", ""));
        if (!at_spec.empty() && out["data"].is_object() && !out["data"].contains("resolved_time")) {
            Json resolved = resolve_time_spec_json(ctx.sid, at_spec, false, range_err);
            if (!resolved.is_null()) out["data"]["resolved_time"] = resolved;
        }

        // Generic metadata
        if (data.contains("truncated")) out["meta"]["truncated"] = data["truncated"];
        if (data.contains("findings")) out["findings"] = data["findings"];
        if (data.contains("warnings")) out["warnings"] = data["warnings"];

        // Build action-specific summary
        build_summary(out, data);
        print_json(finalize_response(ctx.req, out));
        return 0;
    }

private:
    const char* name_;

    void build_summary(Json& out, const Json& data) const {
        std::string action(name_);

        if (action == "sampled_pulse.inspect") {
            out["summary"] = {{"sample_count", data.value("sample_count", 0)},
                              {"sampled_high_cycles", data.value("sampled_high_cycles", 0)},
                              {"raw_valid_transition_count", data.value("raw_valid_transition_count", 0)},
                              {"payload_transition_count", data.value("payload_transition_count", 0)},
                              {"risk_count", data.value("risk_count", 0)}};
        } else if (action == "window.verify") {
            out["summary"] = {{"all_passed", data.value("all_passed", false)},
                              {"sample_count", data.value("sample_count", 0)},
                              {"failed_samples", data.value("failed_samples", 0)},
                              {"unknown_samples", data.value("unknown_samples", 0)}};
        } else if (action == "handshake.inspect") {
            out["summary"] = {{"transfer_count", data.value("transfer_count", 0)},
                              {"max_stall_cycles", data.value("max_stall_cycles", 0)}};
        } else if (action == "detect_anomaly") {
            out["summary"] = {{"finding_count", data.value("finding_count", 0)}};
        } else if (action == "signal.changes") {
            out["summary"] = {
                {"transition_count", data.value("transition_count", 0)},
                {"returned_change_rows", data.value("returned_change_rows", 0)},
                {"includes_initial_value", data.value("includes_initial_value", false)},
                {"actual_transition_count", data.value("actual_transition_count", 0)},
                {"first_change", data.value("first_change", Json(nullptr))},
                {"last_change", data.value("last_change", Json(nullptr))},
                {"semantic_note", data.value("semantic_note", "")}
            };
        } else if (action == "signal.statistics") {
            out["summary"] = {
                {"sampling_mode", data.value("sampling_mode", "")},
                {"sample_count", data.value("sample_count", 0)},
                {"transition_count", data.value("transition_count", 0)},
                {"high_cycles", data.value("high_cycles", 0)},
                {"low_cycles", data.value("low_cycles", 0)}
            };
        } else if (action == "counter.statistics") {
            out["summary"] = {
                {"sample_count", data.value("sample_count", 0)},
                {"valid_count", data.value("valid_count", 0)},
                {"min_value", data.value("min_value", Json(nullptr))},
                {"max_value", data.value("max_value", Json(nullptr))},
                {"average_value", data.value("average_value", Json(nullptr))}
            };
        } else if (data.contains("transaction_count")) {
            out["summary"] = {{"transaction_count", data["transaction_count"]}};
        } else if (data.contains("sample_count")) {
            out["summary"] = {{"sample_count", data["sample_count"]}};
        } else if (data.contains("transition_count")) {
            out["summary"] = {{"transition_count", data["transition_count"]}};
        } else if (data.contains("status")) {
            out["summary"] = {{"status", data["status"]}, {"known", data.value("known", false)}};
        }
    }
};

} // namespace

// Factory functions for each AI action.
// Cannot use a macro because action names contain dots (e.g. "cursor.set"),
// which would produce invalid C++ identifiers with the ## concatenation operator.

std::unique_ptr<WaveformActionHandler> make_cursor_set_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("cursor.set")); }
std::unique_ptr<WaveformActionHandler> make_cursor_get_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("cursor.get")); }
std::unique_ptr<WaveformActionHandler> make_cursor_list_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("cursor.list")); }
std::unique_ptr<WaveformActionHandler> make_cursor_delete_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("cursor.delete")); }
std::unique_ptr<WaveformActionHandler> make_cursor_use_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("cursor.use")); }
std::unique_ptr<WaveformActionHandler> make_expr_eval_at_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("expr.eval_at")); }
std::unique_ptr<WaveformActionHandler> make_window_verify_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("window.verify")); }
std::unique_ptr<WaveformActionHandler> make_signal_changes_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("signal.changes")); }
std::unique_ptr<WaveformActionHandler> make_signal_stability_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("signal.stability")); }
std::unique_ptr<WaveformActionHandler> make_signal_trend_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("signal.trend")); }
std::unique_ptr<WaveformActionHandler> make_signal_statistics_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("signal.statistics")); }
std::unique_ptr<WaveformActionHandler> make_counter_statistics_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("counter.statistics")); }
std::unique_ptr<WaveformActionHandler> make_sampled_pulse_inspect_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("sampled_pulse.inspect")); }
std::unique_ptr<WaveformActionHandler> make_inspect_signal_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("inspect_signal")); }
std::unique_ptr<WaveformActionHandler> make_detect_anomaly_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("detect_anomaly")); }
std::unique_ptr<WaveformActionHandler> make_handshake_inspect_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("handshake.inspect")); }
std::unique_ptr<WaveformActionHandler> make_axi_channel_stall_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("axi.channel_stall")); }
std::unique_ptr<WaveformActionHandler> make_axi_outstanding_timeline_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("axi.outstanding_timeline")); }
std::unique_ptr<WaveformActionHandler> make_axi_request_response_pair_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("axi.request_response_pair")); }
std::unique_ptr<WaveformActionHandler> make_axi_latency_outlier_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("axi.latency_outlier")); }
std::unique_ptr<WaveformActionHandler> make_apb_transfer_window_action()
{ return std::unique_ptr<WaveformActionHandler>(new AiQueryAction("apb.transfer_window")); }

} // namespace kdebug_waveform
