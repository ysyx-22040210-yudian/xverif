#pragma once

#include <cstddef>
#include <string>

namespace xdebug_core {

// Centralized limit policy for action output truncation.
// Reads max_rows/max_events/max_items from options and provides
// consistent truncation logic across all actions.
//
// Usage:
//   LimitPolicy lp = LimitPolicy::from_options(options, limits, 1000);
//   if (lp.is_truncated(results.size())) { ... }
class LimitPolicy {
public:
    static LimitPolicy from_options(const nlohmann::json& options,
                                    const nlohmann::json& limits,
                                    int default_limit) {
        LimitPolicy lp;
        lp.max_rows_ = default_limit;

        // limits take priority over options for backward compatibility
        auto read_int = [](const nlohmann::json& obj, const char* key) -> int {
            auto it = obj.find(key);
            if (it == obj.end()) return -1;
            if (it->is_number_integer()) return it->get<int>();
            if (it->is_string()) {
                try { return std::stoi(it->get<std::string>()); }
                catch (...) { return -1; }
            }
            return -1;
        };

        int v = read_int(limits, "max_rows");
        if (v < 0) v = read_int(limits, "max_events");
        if (v < 0) v = read_int(limits, "max_items");
        if (v < 0) v = read_int(options, "max_rows");
        if (v < 0) v = read_int(options, "max_events");
        if (v < 0) v = read_int(options, "max_items");

        if (v >= 0) lp.max_rows_ = v;
        return lp;
    }

    int max_rows() const { return max_rows_; }

    bool is_truncated(size_t actual_count) const {
        return max_rows_ >= 0 && actual_count > static_cast<size_t>(max_rows_);
    }

    // Truncate a JSON array to max_rows, returning a new truncated array.
    nlohmann::json truncate_array(const nlohmann::json& arr) const {
        if (!arr.is_array() || max_rows_ < 0) return arr;
        if (arr.size() <= static_cast<size_t>(max_rows_)) return arr;
        nlohmann::json limited = nlohmann::json::array();
        for (int i = 0; i < max_rows_; ++i) limited.push_back(arr[i]);
        return limited;
    }

private:
    int max_rows_ = -1;  // -1 means no limit
};

} // namespace xdebug_core
