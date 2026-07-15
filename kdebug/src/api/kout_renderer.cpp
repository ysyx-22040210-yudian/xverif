#include "api/kout_renderer.h"

#include "api/text_response_builder.h"

#include <set>
#include <string>
#include <vector>

namespace kdebug {

namespace {

bool has_scalar(const Json& object, const std::string& key) {
    return object.is_object() && object.contains(key) &&
           kdebug::is_kout_scalar_json(object[key]);
}

bool should_emit_scalar_key(const std::string& key, const Json& value) {
    if (key == "known" && value.is_boolean() && value.get<bool>()) return false;
    return kdebug::is_kout_scalar_json(value);
}

std::string scalar_text(const Json& object, const std::string& key) {
    if (!has_scalar(object, key)) return std::string();
    return json_to_kout_value(object[key]);
}

void emit_scalar_keys(TextResponseBuilder& out, const Json& object,
                      const std::vector<std::string>& keys) {
    if (!object.is_object()) return;
    for (const auto& key : keys) {
        if (has_scalar(object, key) && should_emit_scalar_key(key, object[key]))
            out.emit_kv(key, object[key]);
    }
}

void emit_summary(TextResponseBuilder& out, const Json& response) {
    if (!response.contains("summary") || !response["summary"].is_object()) return;
    out.emit_section("summary");
    for (auto it = response["summary"].begin(); it != response["summary"].end(); ++it) {
        if (should_emit_scalar_key(it.key(), it.value())) {
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
            out.emit_warning(
                scalar_text(warning, "code").empty() ? "warning" : scalar_text(warning, "code"),
                scalar_text(warning, "message").empty() ? warning.dump() : scalar_text(warning, "message"));
        }
    }
}

void emit_suggestions(TextResponseBuilder& out, const Json& response) {
    if (!response.contains("suggested_next_actions") ||
        !response["suggested_next_actions"].is_array()) return;
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

// ── Recursive tree rendering (used by generic fallback) ───────────

void render_data_value(TextResponseBuilder& out, const std::string& key,
                       const Json& val) {
    if (kdebug::is_kout_scalar_json(val)) {
        out.emit_kv(key, val);
    } else if (val.is_array() && val.empty()) {
        out.emit_kv(key, "[empty]");
    } else if (val.is_array() && val.size() > 0 &&
               kdebug::is_kout_scalar_json(val[0])) {
        out.emit_section(key);
        int n = std::min(20, (int)val.size());
        for (int i = 0; i < n; ++i) out.emit_row({json_to_kout_value(val[i])});
        if ((int)val.size() > n)
            out.emit_kv("(+ " + std::to_string(val.size() - n) + " more)", "");
    } else if (val.is_array() && val.size() > 0 && val[0].is_object()) {
        int count = (int)val.size();
        out.emit_section(key);

        // Collect common scalar keys from first few items
        std::vector<std::string> keys;
        std::set<std::string> seen;
        for (int i = 0; i < std::min(5, count); ++i) {
            for (auto ki = val[i].begin(); ki != val[i].end(); ++ki) {
                if (should_emit_scalar_key(ki.key(), ki.value()) &&
                    seen.insert(ki.key()).second) {
                    keys.push_back(ki.key());
                }
            }
        }

        out.emit_row(keys);
        int n = std::min(20, count);
        for (int i = 0; i < n; ++i) {
            std::vector<std::string> row;
            for (const auto& k : keys)
                row.push_back(json_to_kout_value(val[i].value(k, Json())));
            out.emit_row(row);
        }
        if (count > n)
            out.emit_kv("(+ " + std::to_string(count - n) + " more)", "");
    } else if (val.is_object()) {
        out.emit_section(key);
        for (auto it = val.begin(); it != val.end(); ++it)
            render_data_value(out, it.key(), it.value());
    }
}

// ── Specialized renderers (kept for custom formatting) ────────────

void render_value_at(TextResponseBuilder& out, const Json& response) {
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, data, {"signal", "time"});
    out.emit_section("summary");
    emit_scalar_keys(out, data, {"status", "value"});
    out.emit_section("data");
    emit_scalar_keys(out, data, {"bin", "hex", "decimal"});
}

void render_value_batch(TextResponseBuilder& out, const Json& response) {
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, response.value("summary", Json::object()),
                     {"time", "signal_count", "x_or_z_count"});
    if (data.contains("time")) out.emit_kv("time", data["time"]);
    out.emit_section("values");
    if (data.contains("values") && data["values"].is_object()) {
        for (auto it = data["values"].begin(); it != data["values"].end(); ++it)
            out.emit_row({it.key(), json_to_kout_value(it.value())});
    } else if (data.contains("values") && data["values"].is_array()) {
        for (const auto& item : data["values"]) {
            if (item.is_object())
                out.emit_row({scalar_text(item, "signal"), scalar_text(item, "value")});
        }
    }
}

void render_signal_changes(TextResponseBuilder& out, const Json& response) {
    const Json summary = response.value("summary", Json::object());
    const Json data = response.value("data", Json::object());
    out.emit_section("target");
    emit_scalar_keys(out, data, {"signal"});
    if (data.contains("begin") && data.contains("end"))
        out.emit_kv("window", scalar_text(data, "begin") + ".." + scalar_text(data, "end"));
    out.emit_section("summary");
    emit_scalar_keys(out, summary,
        {"change_count", "transition_count", "actual_transition_count",
         "returned_change_rows", "truncated"});
    if (summary.contains("first_change")) out.emit_kv("first_change", summary["first_change"]);
    if (summary.contains("last_change")) out.emit_kv("last_change", summary["last_change"]);
    if (data.contains("changes") && data["changes"].is_array()) {
        out.emit_section("changes");
        for (const auto& item : data["changes"]) {
            if (item.is_object())
                out.emit_row({scalar_text(item, "time"), scalar_text(item, "from"),
                              "->", scalar_text(item, "to"), scalar_text(item, "value")});
        }
    }
}

void render_active_driver(TextResponseBuilder& out, const Json& response) {
    // First render default summary + generic data tree
    emit_summary(out, response);
    const Json data = response.value("data", Json::object());

    // Emit scalar data fields
    if (data.is_object()) {
        out.emit_section("data");
        for (auto it = data.begin(); it != data.end(); ++it) {
            if (should_emit_scalar_key(it.key(), it.value()))
                out.emit_kv(it.key(), it.value());
        }
    }

    // Then add the custom 5-section driver detail
    out.emit_section("target");
    emit_scalar_keys(out, response.value("summary", Json::object()),
                     {"signal", "requested_time", "active_time"});

    for (const char* key : {"driver", "path", "statements", "controls", "events"}) {
        if (!data.contains(key)) continue;
        out.emit_section(key);
        if (data[key].is_array()) {
            for (const auto& item : data[key])
                out.emit_row({json_to_kout_value(item)});
        } else if (data[key].is_object()) {
            for (auto it = data[key].begin(); it != data[key].end(); ++it)
                out.emit_row({it.key(), json_to_kout_value(it.value())});
        }
    }
    if (data.contains("limitations") && data["limitations"].is_array() &&
        !data["limitations"].empty()) {
        out.emit_section("limitations");
        for (const auto& l : data["limitations"])
            out.emit_row({l.get<std::string>()});
    }
}

// ── Generic renderer (enhanced with recursive tree) ──────────────

void render_generic(TextResponseBuilder& out, const Json& response) {
    emit_summary(out, response);
    const Json data = response.value("data", Json::object());
    if (data.is_object() && !data.empty()) {
        out.emit_section("data");
        for (auto it = data.begin(); it != data.end(); ++it)
            render_data_value(out, it.key(), it.value());
    }
    if (response.contains("findings") && response["findings"].is_array() &&
        !response["findings"].empty()) {
        render_data_value(out, "findings", response["findings"]);
    }
}

} // namespace

std::string render_kout_response(const Json& response) {
    const bool ok = response.value("ok", false);
    const std::string action =
        ok ? response.value("action", std::string("unknown")) : std::string("error");
    TextResponseBuilder out("kdebug");
    out.emit_header(action);

    if (!ok) {
        if (response.contains("action")) out.emit_kv("action", response["action"]);
        if (response.contains("error")) out.emit_error(response["error"]);
        if (response.contains("error") && response["error"].is_object()) {
            const Json& error = response["error"];
            if (error.contains("candidates") && error["candidates"].is_array()) {
                out.emit_section("candidates");
                for (const auto& item : error["candidates"])
                    out.emit_row({json_to_kout_value(item)});
            }
            if (error.contains("suggested_actions") && error["suggested_actions"].is_array()) {
                out.emit_section("next");
                for (const auto& item : error["suggested_actions"])
                    out.emit_row({json_to_kout_value(item)});
            }
        }
        return out.str();
    }

    // Prefer handler-generated KOUT text (from engine server response).
    if (response.contains("text") && response["text"].is_string()) {
        out.emit_raw(response["text"].get<std::string>());
    }
    // Only keep specialized renderers that truly need custom formatting.
    else if (action == "value.at")
        render_value_at(out, response);
    else if (action == "value.batch_at" || action == "list.value_at")
        render_value_batch(out, response);
    else if (action == "signal.changes")
        render_signal_changes(out, response);
    else if (action == "trace.active_driver" || action == "trace.active_driver_chain")
        render_active_driver(out, response);
    else
        render_generic(out, response);

    emit_warnings(out, response);
    emit_suggestions(out, response);
    return out.str();
}

} // namespace kdebug
