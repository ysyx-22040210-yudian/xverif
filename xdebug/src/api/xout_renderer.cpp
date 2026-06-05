#include "api/xout_renderer.h"

#include "api/text_response_builder.h"

#include <set>
#include <string>
#include <vector>

namespace xdebug {

namespace {

bool has_scalar(const Json& object, const std::string& key) {
    return object.is_object() && object.contains(key) &&
           (object[key].is_string() || object[key].is_number() || object[key].is_boolean());
}

std::string scalar_text(const Json& object, const std::string& key) {
    if (!has_scalar(object, key)) return std::string();
    return json_to_xout_value(object[key]);
}

void emit_scalar_keys(TextResponseBuilder& out, const Json& object, const std::vector<std::string>& keys) {
    if (!object.is_object()) return;
    for (const auto& key : keys) {
        if (has_scalar(object, key)) out.emit_kv(key, object[key]);
    }
}

void emit_summary(TextResponseBuilder& out, const Json& response) {
    if (!response.contains("summary") || !response["summary"].is_object()) return;
    out.emit_section("summary");
    for (auto it = response["summary"].begin(); it != response["summary"].end(); ++it) {
        if (it.value().is_string() || it.value().is_number() || it.value().is_boolean()) {
            out.emit_kv(it.key(), it.value());
        }
    }
}

void emit_warnings(TextResponseBuilder& out, const Json& response) {
    if (!response.contains("warnings") || !response["warnings"].is_array()) return;
    for (const auto& warning : response["warnings"]) {
        if (warning.is_string()) {
            out.emit_warning("warning", warning.get<std::string>());
        } else if (warning.is_object()) {
            out.emit_warning(scalar_text(warning, "code").empty() ? "warning" : scalar_text(warning, "code"),
                             scalar_text(warning, "message").empty() ? warning.dump() : scalar_text(warning, "message"));
        }
    }
}

void emit_suggestions(TextResponseBuilder& out, const Json& response) {
    if (!response.contains("suggested_next_actions") || !response["suggested_next_actions"].is_array()) return;
    out.emit_section("next");
    for (const auto& item : response["suggested_next_actions"]) {
        if (item.is_string()) {
            out.emit_row({item.get<std::string>()});
        } else if (item.is_object()) {
            std::string action = scalar_text(item, "action");
            std::string reason = scalar_text(item, "reason");
            if (action.empty()) action = item.dump();
            out.emit_row({action, reason});
        }
    }
}

void emit_evidence_object(TextResponseBuilder& out, const Json& value) {
    if (value.is_object()) {
        std::string file = scalar_text(value, "file");
        std::string line = scalar_text(value, "line");
        if (!file.empty()) out.emit_row({line.empty() ? file : file + ":" + line});
    } else if (value.is_array()) {
        for (const auto& item : value) emit_evidence_object(out, item);
    }
}

void render_value_at(TextResponseBuilder& out, const Json& response) {
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, data, {"signal", "time"});
    out.emit_section("summary");
    emit_scalar_keys(out, data, {"value", "known", "width"});
    out.emit_section("data");
    emit_scalar_keys(out, data, {"bin", "hex", "decimal"});
}

void render_value_batch(TextResponseBuilder& out, const Json& response) {
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, response.value("summary", Json::object()), {"time", "signal_count", "x_or_z_count"});
    if (data.contains("time")) out.emit_kv("time", data["time"]);
    out.emit_section("values");
    if (data.contains("values") && data["values"].is_object()) {
        for (auto it = data["values"].begin(); it != data["values"].end(); ++it) {
            out.emit_row({it.key(), json_to_xout_value(it.value())});
        }
    } else if (data.contains("values") && data["values"].is_array()) {
        for (const auto& item : data["values"]) {
            if (item.is_object()) out.emit_row({scalar_text(item, "signal"), scalar_text(item, "value")});
        }
    }
}

void render_trace_driver_like(TextResponseBuilder& out, const Json& response) {
    const Json summary = response.value("summary", Json::object());
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, summary, {"signal", "mode"});
    out.emit_section("summary");
    emit_scalar_keys(out, summary, {"driver_count", "load_count", "result_count", "dependency_count", "confidence", "truncated"});
    const char* list_key = data.contains("loads") ? "loads" : "drivers";
    if (data.contains(list_key) && data[list_key].is_array()) {
        out.emit_section(list_key);
        int index = 0;
        for (const auto& item : data[list_key]) {
            if (!item.is_object()) continue;
            std::string id = std::string(list_key[0] == 'l' ? "l" : "d") + std::to_string(index++);
            std::string loc = scalar_text(item, "file");
            std::string line = scalar_text(item, "line");
            if (!loc.empty() && !line.empty()) loc += ":" + line;
            out.emit_row({id, scalar_text(item, "kind"), loc, scalar_text(item, "confidence")});
        }
        out.emit_section("dependencies");
        std::set<std::string> seen;
        for (const auto& item : data[list_key]) {
            if (!item.is_object()) continue;
            for (const char* dep_key : {"rhs_signals", "condition_signals"}) {
                if (!item.contains(dep_key) || !item[dep_key].is_array()) continue;
                for (const auto& dep : item[dep_key]) {
                    std::string text = json_to_xout_value(dep);
                    if (!text.empty() && seen.insert(text).second) out.emit_row({text});
                }
            }
        }
        out.emit_section("evidence");
        for (const auto& item : data[list_key]) emit_evidence_object(out, item);
    }
}

void render_trace_graph(TextResponseBuilder& out, const Json& response) {
    const Json summary = response.value("summary", Json::object());
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, summary, {"signal", "root_signal", "depth"});
    out.emit_section("summary");
    emit_scalar_keys(out, summary, {"node_count", "edge_count", "nodes", "edges", "truncated"});
    Json graph = data.contains("graph") ? data["graph"] : data;
    if (graph.contains("nodes") && graph["nodes"].is_array()) {
        out.emit_section("nodes");
        int index = 0;
        for (const auto& node : graph["nodes"]) {
            if (node.is_string()) {
                out.emit_row({"n" + std::to_string(index++), node.get<std::string>()});
            } else if (node.is_object()) {
                out.emit_row({"n" + std::to_string(index++), scalar_text(node, "signal"), scalar_text(node, "kind")});
            }
        }
    }
    if (graph.contains("edges") && graph["edges"].is_array()) {
        out.emit_section("edges");
        for (const auto& edge : graph["edges"]) {
            if (!edge.is_object()) continue;
            std::string loc = scalar_text(edge, "file");
            std::string line = scalar_text(edge, "line");
            if (!loc.empty() && !line.empty()) loc += ":" + line;
            out.emit_row({scalar_text(edge, "from"), "->", scalar_text(edge, "to"), scalar_text(edge, "relation"), loc});
        }
    }
    if (data.contains("evidence")) {
        out.emit_section("evidence");
        emit_evidence_object(out, data["evidence"]);
    }
}

void render_signal_changes(TextResponseBuilder& out, const Json& response) {
    const Json summary = response.value("summary", Json::object());
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, data, {"signal"});
    if (data.contains("time_range") && data["time_range"].is_object()) {
        out.emit_kv("window", scalar_text(data["time_range"], "start") + ".." + scalar_text(data["time_range"], "end"));
    }
    out.emit_section("summary");
    emit_scalar_keys(out, summary, {"change_count", "transition_count", "actual_transition_count", "returned_change_rows", "truncated"});
    if (summary.contains("first_change")) out.emit_kv("first_change", summary["first_change"]);
    if (summary.contains("last_change")) out.emit_kv("last_change", summary["last_change"]);
    if (data.contains("changes") && data["changes"].is_array()) {
        out.emit_section("changes");
        for (const auto& item : data["changes"]) {
            if (item.is_object()) out.emit_row({scalar_text(item, "time"), scalar_text(item, "from"), "->", scalar_text(item, "to"), scalar_text(item, "value")});
        }
    }
}

void render_active_driver(TextResponseBuilder& out, const Json& response) {
    const Json summary = response.value("summary", Json::object());
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, summary, {"signal", "requested_time", "active_time"});
    out.emit_section("summary");
    emit_scalar_keys(out, summary, {"classification", "active_driver", "value", "confidence", "truncated"});
    for (const char* key : {"drivers", "control", "evidence"}) {
        if (data.contains(key)) {
            out.emit_section(key);
            if (std::string(key) == "evidence") {
                emit_evidence_object(out, data[key]);
            } else if (data[key].is_array()) {
                for (const auto& item : data[key]) out.emit_row({item.is_object() ? item.dump() : json_to_xout_value(item)});
            } else if (data[key].is_object()) {
                for (auto it = data[key].begin(); it != data[key].end(); ++it) out.emit_row({it.key(), json_to_xout_value(it.value())});
            }
        }
    }
}

void render_event_like(TextResponseBuilder& out, const Json& response) {
    emit_summary(out, response);
    const Json data = response.value("data", Json::object());
    if (data.contains("examples") && data["examples"].is_array()) {
        out.emit_section("examples");
        for (const auto& item : data["examples"]) out.emit_row({item.is_object() ? item.dump() : json_to_xout_value(item)});
    }
    if (data.contains("findings") && data["findings"].is_array()) {
        out.emit_section("findings");
        for (const auto& item : data["findings"]) out.emit_row({item.is_object() ? item.dump() : json_to_xout_value(item)});
    }
}

void render_source_context(TextResponseBuilder& out, const Json& response) {
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, data, {"file", "line", "symbol", "context_kind"});
    out.emit_section("summary");
    emit_scalar_keys(out, response.value("summary", Json::object()), {"file", "line", "symbol", "context_kind", "truncated"});
    if (data.contains("context") && data["context"].is_array()) {
        out.emit_section("data");
        for (const auto& item : data["context"]) {
            if (item.is_object()) out.emit_row({scalar_text(item, "line"), scalar_text(item, "text")});
        }
    }
    out.emit_section("evidence");
    emit_evidence_object(out, data);
}

void render_generic(TextResponseBuilder& out, const Json& response) {
    emit_summary(out, response);
    const Json data = response.value("data", Json::object());
    if (data.is_object()) {
        out.emit_section("data");
        for (auto it = data.begin(); it != data.end(); ++it) {
            if (it.value().is_string() || it.value().is_number() || it.value().is_boolean()) {
                out.emit_kv(it.key(), it.value());
            }
        }
    }
    if (response.contains("findings") && response["findings"].is_array() && !response["findings"].empty()) {
        out.emit_section("findings");
        for (const auto& finding : response["findings"]) out.emit_row({finding.dump()});
    }
}

} // namespace

std::string render_xout_response(const Json& response) {
    const bool ok = response.value("ok", false);
    const std::string action = ok ? response.value("action", std::string("unknown")) : std::string("error");
    TextResponseBuilder out("xdebug");
    out.emit_header(action);
    if (!ok) {
        if (response.contains("action")) out.emit_kv("action", response["action"]);
        if (response.contains("error")) out.emit_error(response["error"]);
        if (response.contains("error") && response["error"].is_object()) {
            const Json& error = response["error"];
            if (error.contains("candidates") && error["candidates"].is_array()) {
                out.emit_section("candidates");
                for (const auto& item : error["candidates"]) out.emit_row({json_to_xout_value(item)});
            }
            if (error.contains("suggested_actions") && error["suggested_actions"].is_array()) {
                out.emit_section("next");
                for (const auto& item : error["suggested_actions"]) out.emit_row({json_to_xout_value(item)});
            }
        }
        return out.str();
    }

    if (action == "value.at") render_value_at(out, response);
    else if (action == "value.batch_at" || action == "list.value_at") render_value_batch(out, response);
    else if (action == "trace.driver" || action == "trace.load" || action == "trace.query") render_trace_driver_like(out, response);
    else if (action == "trace.graph" || action == "trace.expand" || action == "trace.path" || action == "trace.explain") render_trace_graph(out, response);
    else if (action == "signal.changes") render_signal_changes(out, response);
    else if (action == "trace.active_driver") render_active_driver(out, response);
    else if (action == "event.find" || action == "event.export" || action == "axi.query" || action == "axi.analysis" || action == "handshake.inspect") render_event_like(out, response);
    else if (action == "source.context") render_source_context(out, response);
    else render_generic(out, response);

    emit_warnings(out, response);
    emit_suggestions(out, response);
    return out.str();
}

} // namespace xdebug
