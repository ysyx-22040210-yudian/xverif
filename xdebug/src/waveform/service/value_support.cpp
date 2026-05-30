#include "action_support.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <vector>

namespace xdebug_waveform {

std::string compact_expr_ws(const std::string& expr) {
    std::string out;
    out.reserve(expr.size());
    for (char c : expr) {
        if (!std::isspace(static_cast<unsigned char>(c))) out.push_back(c);
    }
    return out;
}

bool contains_xz(const std::string& value) {
    std::string v = trim(value);
    size_t start = 0;
    if (v.size() >= 2 && v[0] == '0' && (v[1] == 'x' || v[1] == 'X')) {
        start = 2;
    } else if (v.size() >= 2 && v[0] == '\'' &&
               (v[1] == 'h' || v[1] == 'H' || v[1] == 'b' || v[1] == 'B' ||
                v[1] == 'd' || v[1] == 'D')) {
        start = 2;
    }
    for (size_t i = start; i < v.size(); ++i) {
        char c = v[i];
        if (c == 'x' || c == 'X' || c == 'z' || c == 'Z') return true;
    }
    return false;
}

std::string normalize_numeric(std::string value) {
    value = trim(value);
    if (value.size() >= 2 && value[0] == '\'' && (value[1] == 'h' || value[1] == 'H')) {
        value = "0x" + value.substr(2);
    } else if (value.size() >= 2 && value[0] == '\'' && (value[1] == 'b' || value[1] == 'B')) {
        value = "0b" + value.substr(2);
    } else if (value.size() >= 2 && value[0] == '\'' && (value[1] == 'd' || value[1] == 'D')) {
        value = value.substr(2);
    }
    if (value.size() > 2 && value[0] == '0' && (value[1] == 'x' || value[1] == 'X')) {
        value = value.substr(2);
    } else if (value.size() > 2 && value[0] == '0' && (value[1] == 'b' || value[1] == 'B')) {
        unsigned long long n = strtoull(value.substr(2).c_str(), nullptr, 2);
        char buf[64];
        snprintf(buf, sizeof(buf), "%llx", n);
        value = buf;
    } else {
        bool decimal = !value.empty();
        for (char c : value) {
            if (!std::isdigit(static_cast<unsigned char>(c))) {
                decimal = false;
                break;
            }
        }
        if (decimal) {
            unsigned long long n = strtoull(value.c_str(), nullptr, 10);
            char buf[64];
            snprintf(buf, sizeof(buf), "%llx", n);
            value = buf;
        }
    }
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    size_t first = value.find_first_not_of('0');
    if (first == std::string::npos) return "0";
    return value.substr(first);
}

Json make_value_object(const std::string& raw) {
    Json v;
    std::string text = trim(raw);
    v["value"] = text;
    v["known"] = !contains_xz(text);
    return v;
}

Json make_value_map(const Json& raw_map) {
    Json out = Json::object();
    if (!raw_map.is_object()) return out;
    for (auto it = raw_map.begin(); it != raw_map.end(); ++it) {
        if (it.value().is_string()) out[it.key()] = make_value_object(it.value().get<std::string>());
        else out[it.key()] = it.value();
    }
    return out;
}

Json simplify_event_value_objects(Json events) {
    if (!events.is_array()) return events;
    for (auto& ev : events) {
        if (!ev.is_object()) continue;
        if (ev.contains("signals")) ev["signals"] = make_value_map(ev["signals"]);
        if (ev.contains("fields")) ev["fields"] = make_value_map(ev["fields"]);
    }
    return events;
}

namespace {

std::string event_group_value(const Json& ev, const std::string& key) {
    auto get = [&](const char* section) -> std::string {
        if (!ev.contains(section) || !ev[section].is_object()) return std::string();
        auto it = ev[section].find(key);
        if (it == ev[section].end()) return std::string();
        if (it->is_string()) return it->get<std::string>();
        if (it->is_object() && it->contains("value") && (*it)["value"].is_string()) return (*it)["value"].get<std::string>();
        return std::string();
    };
    std::string v = get("fields");
    if (v.empty()) v = get("signals");
    if (v.empty() || v == "?" || contains_xz(v)) return "unknown";
    return v;
}

} // namespace

Json aggregate_events(const Json& events, const Json& aggregate_args, int limit) {
    bool want_count = aggregate_args.value("count", true);
    Json group_by_json = aggregate_args.value("group_by", Json::array());
    std::vector<std::string> group_by;
    if (group_by_json.is_array()) {
        for (const auto& item : group_by_json) if (item.is_string()) group_by.push_back(item.get<std::string>());
    }

    Json out = Json::object();
    size_t event_count = events.is_array() ? events.size() : 0;
    if (want_count) out["count"] = event_count;
    out["limited"] = limit > 0 && event_count >= static_cast<size_t>(limit);

    if (!group_by.empty() && events.is_array()) {
        struct GroupState {
            Json key;
            int count = 0;
            std::string first_time;
            std::string last_time;
        };
        std::map<std::string, GroupState> groups;
        for (const auto& ev : events) {
            Json key_obj = Json::object();
            for (const auto& key : group_by) key_obj[key] = event_group_value(ev, key);
            std::string group_id = key_obj.dump();
            GroupState& st = groups[group_id];
            if (st.count == 0) {
                st.key = key_obj;
                st.first_time = ev.value("time", std::string());
            }
            st.count++;
            st.last_time = ev.value("time", std::string());
        }
        Json arr = Json::array();
        for (const auto& kv : groups) {
            arr.push_back({{"key", kv.second.key},
                           {"count", kv.second.count},
                           {"first_time", kv.second.first_time},
                           {"last_time", kv.second.last_time}});
        }
        out["groups"] = arr;
        out["group_count"] = arr.size();
    }
    return out;
}

} // namespace xdebug_waveform
