#include "../action_handler.h"
#include "../action_support.h"
#include "../command_builder.h"
#include "../rc_generator.h"
#include "../../protocol/protocol.h"

#include <algorithm>
#include <cstdlib>

namespace kdebug_waveform {

namespace {

std::string strip_signal_select(const std::string& signal) {
    size_t bracket = signal.find('[');
    if (bracket == std::string::npos) return signal;
    return signal.substr(0, bracket);
}

bool signal_check_ok(const std::string& sid, const std::string& signal, std::string& err) {
    std::string payload;
    return capture_server_text(sid, CommandBuilder(CMD_SIGNAL_CHECK).arg(signal).build(), payload, err);
}

Json make_rc_validation_error(const WaveformActionContext& ctx, const std::string& code,
                              const std::string& message, const Json& summary, const Json& validation) {
    Json out = error_response(ctx.req, ctx.action, code, message, true, ctx.elapsed_ms);
    fill_session(out, ctx.info);
    out["summary"] = summary;
    out["data"]["validation"] = validation;
    return out;
}

class RcGenerateAction : public WaveformActionHandler {
public:
    const char* action_name() const override { return "rc.generate"; }

    int run(const WaveformActionContext& ctx) const override {
        std::string config_path = string_or(ctx.args, "config_path", string_or(ctx.args, "json_path", ""));
        std::string rc_path = string_or(ctx.args, "rc_path", string_or(ctx.args, "output_path", ""));

        if (config_path.empty())
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD", "rc.generate requires args.config_path", ctx.elapsed_ms);
        if (rc_path.empty())
            return print_error_and_return(ctx.req, ctx.action, "MISSING_FIELD", "rc.generate requires args.rc_path", ctx.elapsed_ms);

        std::string config_text;
        if (!read_file(config_path, config_text))
            return print_error_and_return(ctx.req, ctx.action, "RC_CONFIG_INVALID", "cannot read config_path: " + config_path, ctx.elapsed_ms);

        Json config_doc;
        try {
            config_doc = Json::parse(config_text);
        } catch (const std::exception& ex) {
            return print_error_and_return(ctx.req, ctx.action, "RC_CONFIG_INVALID",
                std::string("config_path is not valid JSON: ") + ex.what(), ctx.elapsed_ms);
        }

        RcConfig config;
        std::string parse_err;
        if (!parse_rc_config_json(config_doc, config, parse_err))
            return print_error_and_return(ctx.req, ctx.action, "RC_CONFIG_INVALID", parse_err, ctx.elapsed_ms);

        Json counts = rc_config_counts(config);
        Json summary = {
            {"config_path", config_path},
            {"rc_path", rc_path},
            {"group_count", counts.value("group_count", 0)},
            {"signal_count", counts.value("signal_count", 0)},
            {"expr_signal_count", counts.value("expr_signal_count", 0)},
            {"marker_count", counts.value("marker_count", 0)},
            {"written", false},
            {"valid", true}
        };

        Json validation;
        validation["signals"] = Json::array();
        validation["times"] = Json::array();

        int missing_signal_count = 0;
        for (const auto& ref : collect_rc_signal_refs(config)) {
            std::string check_err;
            bool found = signal_check_ok(ctx.sid, ref.input_path, check_err);
            std::string checked_path = ref.input_path;
            bool checked_base_signal = false;
            if (!found) {
                std::string base = strip_signal_select(ref.input_path);
                if (base != ref.input_path) {
                    std::string base_err;
                    if (signal_check_ok(ctx.sid, base, base_err)) {
                        found = true;
                        checked_path = base;
                        checked_base_signal = true;
                        check_err.clear();
                    } else if (check_err.empty()) {
                        check_err = base_err;
                    }
                }
            }
            Json item = {
                {"kind", ref.kind},
                {"owner", ref.owner},
                {"input_path", ref.input_path},
                {"rc_path", ref.rc_path},
                {"exists", found},
                {"checked_path", checked_path}
            };
            if (checked_base_signal) item["checked_base_signal"] = true;
            if (!found) {
                item["error"] = check_err;
                missing_signal_count++;
            }
            validation["signals"].push_back(item);
        }

        int invalid_time_count = 0;
        for (const auto& ref : collect_rc_time_refs(config)) {
            std::string time_err;
            Json resolved = resolve_time_spec_json(ctx.sid, ref.spec, ref.allow_max, time_err);
            bool ok = !resolved.is_null();
            Json item = {
                {"kind", ref.kind},
                {"owner", ref.owner},
                {"spec", ref.spec},
                {"valid", ok}
            };
            if (ok) item["resolved_time"] = resolved;
            else {
                item["error"] = time_err;
                invalid_time_count++;
            }
            validation["times"].push_back(item);
        }

        bool valid = missing_signal_count == 0 && invalid_time_count == 0;
        summary["valid"] = valid;
        summary["missing_signal_count"] = missing_signal_count;
        summary["invalid_time_count"] = invalid_time_count;

        bool allow_invalid = bool_or(ctx.args, "allow_invalid", false);
        if (!valid && !allow_invalid) {
            Json out = make_rc_validation_error(ctx, "RC_VALIDATION_FAILED",
                "rc config validation failed; rc file was not written", summary, validation);
            print_json(finalize_response(ctx.req, out));
            return 1;
        }

        std::string rc_text = render_signal_rc(config);
        std::string write_err;
        if (!write_text_file_creating_dirs(rc_path, rc_text, write_err))
            return print_error_and_return(ctx.req, ctx.action, "RC_WRITE_FAILED", write_err, ctx.elapsed_ms);

        Json out = base_response(ctx.req, ctx.action, true, ctx.elapsed_ms);
        fill_session(out, ctx.info);
        summary["written"] = true;
        out["summary"] = summary;
        out["data"]["config_path"] = config_path;
        out["data"]["rc_path"] = rc_path;
        out["data"]["validation"] = validation;
        if (bool_or(ctx.args, "include_preview", false))
            out["data"]["rc_preview"] = rc_preview_lines(rc_text, int_or(ctx.args, "max_preview_lines", 40));
        if (!valid) {
            out["warnings"].push_back({{"code", "RC_VALIDATION_FAILED"},
                {"message", "rc file was written because allow_invalid is true"},
                {"missing_signal_count", missing_signal_count},
                {"invalid_time_count", invalid_time_count}});
        }
        print_json(finalize_response(ctx.req, out));
        return 0;
    }
};

} // namespace

std::unique_ptr<WaveformActionHandler> make_rc_generate_action() {
    return std::unique_ptr<WaveformActionHandler>(new RcGenerateAction());
}

} // namespace kdebug_waveform
