#pragma once

#include "api/json_types.h"

#include <initializer_list>
#include <sstream>
#include <string>

namespace xdebug {

class TextResponseBuilder {
public:
    explicit TextResponseBuilder(std::string tool);

    void emit_header(const std::string& action);
    void emit_section(const std::string& name);
    void emit_kv(const std::string& key, const Json& value);
    void emit_kv(const std::string& key, const std::string& value);
    void emit_kv(const std::string& key, const char* value);
    void emit_kv(const std::string& key, bool value);
    void emit_kv(const std::string& key, int value);
    void emit_kv(const std::string& key, long long value);
    void emit_row(std::initializer_list<std::string> columns);
    void emit_warning(const std::string& code, const std::string& message);
    void emit_error(const Json& error);
    std::string str() const;

private:
    std::string tool_;
    std::ostringstream out_;
    std::string pending_section_;
    bool wrote_header_ = false;
    bool wrote_content_ = false;
    bool in_section_ = false;

    void ensure_section();
    void write_line(const std::string& text);
};

std::string sanitize_xout_key(const std::string& key);
std::string sanitize_xout_value(const std::string& value);
std::string json_to_xout_value(const Json& value);

} // namespace xdebug
