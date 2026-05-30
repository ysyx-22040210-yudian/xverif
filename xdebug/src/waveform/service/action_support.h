#pragma once

#include "../apb/apb_config.h"
#include "../axi/axi_config.h"
#include "../event/event_config.h"
#include "../session/session_manager.h"
#include "json.hpp"

#include <istream>
#include <string>

namespace xdebug_waveform {

using Json = nlohmann::ordered_json;

extern const char* kApiVersion;

std::string read_stream(std::istream& is);
bool read_file(const std::string& path, std::string& out);
std::string trim(std::string s);
std::string compact_expr_ws(const std::string& expr);
bool contains_xz(const std::string& value);
std::string normalize_numeric(std::string value);
Json make_value_object(const std::string& raw);
Json make_value_map(const Json& raw_map);
Json simplify_event_value_objects(Json events);
Json aggregate_events(const Json& events, const Json& aggregate_args, int limit);
Json base_response(const Json& req, const std::string& action, bool ok, long long elapsed_ms);
Json error_response(const Json& req, const std::string& action, const std::string& code,
                    const std::string& message, bool recoverable, long long elapsed_ms);
std::string response_verbosity(const Json& req, bool* valid = nullptr);
bool compact_mode(const Json& req);
int max_items_arg(const Json& args, const Json& limits, int def);
int max_examples_arg(const Json& args, const Json& limits, int def);
Json finalize_response(const Json& req, const Json& full);
void print_json(const Json& j);
bool get_string(const Json& obj, const char* key, std::string& out);
std::string string_or(const Json& obj, const char* key, const std::string& def);
int int_or(const Json& obj, const char* key, int def);
bool bool_or(const Json& obj, const char* key, bool def);
std::string create_session_quiet(SessionManager& manager, const std::string& fsdb,
                                 const std::string& name, const SessionTransportOptions& transport);
bool resolve_session(const Json& target, bool allow_auto_open, std::string& session_id,
                     SessionInfo& info, std::string& error);
void fill_session(Json& out, const SessionInfo& info);
bool capture_server_json(const std::string& session_id, const std::string& cmd, Json& data, std::string& error);
bool capture_server_text(const std::string& session_id, const std::string& cmd, std::string& payload, std::string& error);
Json session_info_json(const SessionInfo& s);

bool parse_apb_config(const Json& j, ApbConfig& c, std::string& err);
Json apb_config_json(const ApbConfig& c);
bool parse_axi_config(const Json& j, AxiConfig& c, std::string& err);
Json axi_config_json(const AxiConfig& c);
bool parse_event_config(const Json& j, EventConfig& c, std::string& err);
Json event_config_json(const EventConfig& c);
bool load_config_json_arg(const Json& args, Json& config, std::string& err);
char fmt_char(const Json& args);
std::string arg_text(const Json& v);
bool query_value(const std::string& session_id, const std::string& signal, const std::string& time,
                 char fmt, std::string& raw, std::string& err);
Json resolve_time_spec_json(const std::string& session_id, const std::string& spec,
                            bool allow_max, std::string& err);
bool build_range_specs(const Json& args, std::string& begin, std::string& end,
                       bool& around_window, std::string& err);
void fill_resolved_range(Json& out, const std::string& sid, const std::string& begin,
                         const std::string& end, bool around_window, std::string& err);

enum class Tri { False, True, Unknown };
Tri evaluate_expression(const std::string& expr, const Json& values, bool& ok);
const char* tri_text(Tri v);

void print_actions();
void print_schema();
bool action_known(const std::string& action);
bool server_ai_action(const std::string& action);
int print_error_and_return(const Json& req, const std::string& action,
                           const std::string& code, const std::string& msg, long long elapsed_ms);
int run_query(const Json& req, long long elapsed_ms);

} // namespace xdebug_waveform
