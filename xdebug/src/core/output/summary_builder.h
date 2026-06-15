#pragma once

#include "json.hpp"

#include <string>

namespace xdebug_core {

// Builder for action response summary objects.
// Provides a consistent way to build summary JSON across actions.
//
// Usage:
//   SummaryBuilder sb;
//   sb.set("signal", signal).set("time", time).set("known", !contains_xz(raw));
//   out["summary"] = sb.build();
class SummaryBuilder {
public:
    SummaryBuilder& set(const std::string& key, const nlohmann::json& value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, const char* value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, const std::string& value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, bool value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, int value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, size_t value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set(const std::string& key, double value) {
        obj_[key] = value;
        return *this;
    }

    SummaryBuilder& set_truncated(bool truncated) {
        obj_["truncated"] = truncated;
        return *this;
    }

    SummaryBuilder& set_verdict(bool all_passed, int failed, int unknown) {
        obj_["verdict"] = (failed == 0 && unknown == 0) ? "pass" : "fail";
        obj_["all_passed"] = (failed == 0 && unknown == 0);
        obj_["failed"] = failed;
        obj_["unknown"] = unknown;
        return *this;
    }

    nlohmann::json build() const { return obj_; }

private:
    nlohmann::json obj_ = nlohmann::json::object();
};

} // namespace xdebug_core
