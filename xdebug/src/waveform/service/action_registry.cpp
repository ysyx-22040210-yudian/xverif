#include "action_registry.h"

namespace xdebug_waveform {

// value_query_actions.cpp
std::unique_ptr<WaveformActionHandler> make_value_at_action();
std::unique_ptr<WaveformActionHandler> make_value_batch_at_action();
std::unique_ptr<WaveformActionHandler> make_scope_list_action();

// list_actions.cpp
std::unique_ptr<WaveformActionHandler> make_list_create_action();
std::unique_ptr<WaveformActionHandler> make_list_add_action();
std::unique_ptr<WaveformActionHandler> make_list_delete_action();
std::unique_ptr<WaveformActionHandler> make_list_show_action();
std::unique_ptr<WaveformActionHandler> make_list_value_at_action();
std::unique_ptr<WaveformActionHandler> make_list_validate_action();
std::unique_ptr<WaveformActionHandler> make_list_diff_action();

// rc_generate_action.cpp
std::unique_ptr<WaveformActionHandler> make_rc_generate_action();

// verify_conditions_action.cpp
std::unique_ptr<WaveformActionHandler> make_verify_conditions_action();

// ai_query_actions.cpp
std::unique_ptr<WaveformActionHandler> make_cursor_set_action();
std::unique_ptr<WaveformActionHandler> make_cursor_get_action();
std::unique_ptr<WaveformActionHandler> make_cursor_list_action();
std::unique_ptr<WaveformActionHandler> make_cursor_delete_action();
std::unique_ptr<WaveformActionHandler> make_cursor_use_action();
std::unique_ptr<WaveformActionHandler> make_expr_eval_at_action();
std::unique_ptr<WaveformActionHandler> make_window_verify_action();
std::unique_ptr<WaveformActionHandler> make_signal_changes_action();
std::unique_ptr<WaveformActionHandler> make_signal_stability_action();
std::unique_ptr<WaveformActionHandler> make_signal_trend_action();
std::unique_ptr<WaveformActionHandler> make_signal_statistics_action();
std::unique_ptr<WaveformActionHandler> make_sampled_pulse_inspect_action();
std::unique_ptr<WaveformActionHandler> make_inspect_signal_action();
std::unique_ptr<WaveformActionHandler> make_detect_anomaly_action();
std::unique_ptr<WaveformActionHandler> make_handshake_inspect_action();
std::unique_ptr<WaveformActionHandler> make_axi_channel_stall_action();
std::unique_ptr<WaveformActionHandler> make_axi_outstanding_timeline_action();
std::unique_ptr<WaveformActionHandler> make_axi_request_response_pair_action();
std::unique_ptr<WaveformActionHandler> make_axi_latency_outlier_action();
std::unique_ptr<WaveformActionHandler> make_apb_transfer_window_action();

void WaveformActionRegistry::add(std::unique_ptr<WaveformActionHandler> handler) {
    if (!handler) return;
    handlers_[handler->action_name()] = std::move(handler);
}

const WaveformActionHandler* WaveformActionRegistry::find(const std::string& action) const {
    auto it = handlers_.find(action);
    if (it == handlers_.end()) return nullptr;
    return it->second.get();
}

const WaveformActionRegistry& default_waveform_action_registry() {
    static WaveformActionRegistry* registry = []() {
        WaveformActionRegistry* r = new WaveformActionRegistry();

        // value query actions
        r->add(make_value_at_action());
        r->add(make_value_batch_at_action());
        r->add(make_scope_list_action());

        // list actions
        r->add(make_list_create_action());
        r->add(make_list_add_action());
        r->add(make_list_delete_action());
        r->add(make_list_show_action());
        r->add(make_list_value_at_action());
        r->add(make_list_validate_action());
        r->add(make_list_diff_action());

        // rc.generate
        r->add(make_rc_generate_action());

        // verify.conditions
        r->add(make_verify_conditions_action());

        // AI query actions (server_ai_action)
        r->add(make_cursor_set_action());
        r->add(make_cursor_get_action());
        r->add(make_cursor_list_action());
        r->add(make_cursor_delete_action());
        r->add(make_cursor_use_action());
        r->add(make_expr_eval_at_action());
        r->add(make_window_verify_action());
        r->add(make_signal_changes_action());
        r->add(make_signal_stability_action());
        r->add(make_signal_trend_action());
        r->add(make_signal_statistics_action());
        r->add(make_sampled_pulse_inspect_action());
        r->add(make_inspect_signal_action());
        r->add(make_detect_anomaly_action());
        r->add(make_handshake_inspect_action());
        r->add(make_axi_channel_stall_action());
        r->add(make_axi_outstanding_timeline_action());
        r->add(make_axi_request_response_pair_action());
        r->add(make_axi_latency_outlier_action());
        r->add(make_apb_transfer_window_action());

        return r;
    }();
    return *registry;
}

} // namespace xdebug_waveform
