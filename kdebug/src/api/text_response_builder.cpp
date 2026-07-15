#include "api/text_response_builder.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>

namespace kdebug {

namespace {

constexpr size_t kMaxValueLength = 4096;

bool is_empty_json(const Json& value) {
    return value.is_null() ||
           (value.is_array() && value.empty()) ||
           (value.is_object() && value.empty());
}

std::string trim_copy(const std::string& input) {
    size_t begin = 0;
    while (begin < input.size() &&
           std::isspace(static_cast<unsigned char>(input[begin]))) {
        ++begin;
    }
    size_t end = input.size();
    while (end > begin &&
           std::isspace(static_cast<unsigned char>(input[end - 1]))) {
        --end;
    }
    return input.substr(begin, end - begin);
}

std::string lower_no_underscores(std::string text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        if (c == '_' || std::isspace(static_cast<unsigned char>(c))) continue;
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains_xz_text(const std::string& text) {
    std::string s = trim_copy(text);
    size_t start = 0;
    if (s.size() >= 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        start = 2;
    } else if (s.size() >= 2 && s[0] == '\'' &&
               (s[1] == 'h' || s[1] == 'H' || s[1] == 'b' || s[1] == 'B' ||
                s[1] == 'd' || s[1] == 'D')) {
        start = 2;
    }
    return s.find_first_of("xXzZ", start) != std::string::npos;
}

bool is_value_object(const Json& value) {
    if (!value.is_object() || !value.contains("value")) return false;
    const Json& raw = value["value"];
    if (!(raw.is_string() || raw.is_number() || raw.is_boolean() || raw.is_null())) return false;
    return value.contains("known") || value.contains("bits") || value.contains("width");
}

std::string strip_value_prefix(const std::string& text, char& base) {
    std::string s = trim_copy(text);
    base = 0;
    size_t tick = s.find('\'');
    if (tick != std::string::npos && tick + 1 < s.size()) {
        base = static_cast<char>(std::tolower(static_cast<unsigned char>(s[tick + 1])));
        return s.substr(tick + 2);
    }
    if (s.size() > 2 && s[0] == '0' && (s[1] == 'x' || s[1] == 'X')) {
        base = 'h';
        return s.substr(2);
    }
    if (s.size() > 2 && s[0] == '0' && (s[1] == 'b' || s[1] == 'B')) {
        base = 'b';
        return s.substr(2);
    }
    base = 'h';
    return s;
}

std::string bits_to_hex(std::string bits) {
    bits = lower_no_underscores(bits);
    if (bits.empty()) return "0";
    size_t pad = (4 - bits.size() % 4) % 4;
    bits.insert(bits.begin(), pad, '0');
    static const char* hex = "0123456789abcdef";
    std::string out;
    for (size_t i = 0; i < bits.size(); i += 4) {
        bool unknown = false;
        int v = 0;
        for (size_t j = 0; j < 4; ++j) {
            char c = bits[i + j];
            if (c != '0' && c != '1') unknown = true;
            v = (v << 1) | (c == '1' ? 1 : 0);
        }
        out.push_back(unknown ? 'x' : hex[v]);
    }
    return out.empty() ? "0" : out;
}

std::string bin_to_hex(std::string bits) {
    return bits_to_hex(std::move(bits));
}

std::string dec_to_hex(const std::string& text) {
    std::string clean = lower_no_underscores(text);
    if (clean.empty() || contains_xz_text(clean)) return clean;
    char* end = nullptr;
    unsigned long long v = std::strtoull(clean.c_str(), &end, 10);
    if (!end || *end != '\0') return clean;
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%llx", v);
    return buf;
}

std::string value_json_text(const Json& value) {
    if (value.is_null()) return "";
    if (value.is_string()) return value.get<std::string>();
    if (value.is_boolean()) return value.get<bool>() ? "1" : "0";
    if (value.is_number_integer()) return std::to_string(value.get<long long>());
    if (value.is_number_unsigned()) return std::to_string(value.get<unsigned long long>());
    if (value.is_number_float()) return value.dump();
    return value.dump();
}

std::string compact_value_object(const Json& value) {
    std::string raw = trim_copy(value_json_text(value.value("value", Json())));
    std::string bits = value.value("bits", std::string());
    int width = value.value("width", 0);
    const bool known = value.value("known", !contains_xz_text(raw) && !contains_xz_text(bits));

    std::string hex_text;
    int inferred_width = width;
    if (!bits.empty()) {
        std::string clean_bits = lower_no_underscores(bits);
        if (inferred_width <= 0) inferred_width = static_cast<int>(clean_bits.size());
        hex_text = bits_to_hex(clean_bits);
    } else {
        char base = 0;
        std::string body = strip_value_prefix(raw, base);
        body = lower_no_underscores(body);
        if (base == 'b') {
            if (inferred_width <= 0) inferred_width = static_cast<int>(body.size());
            hex_text = bin_to_hex(body);
            bits = body;
        } else if (base == 'd') {
            hex_text = dec_to_hex(body);
        } else {
            hex_text = body.empty() ? "0" : body;
        }
    }

    if (hex_text.empty()) hex_text = "0";
    std::string out = inferred_width > 0
        ? std::to_string(inferred_width) + "'h" + hex_text
        : "'h" + hex_text;

    if (!known || contains_xz_text(raw) || contains_xz_text(bits) || contains_xz_text(hex_text)) {
        out += " known=false";
        if (!bits.empty()) out += " bits=" + lower_no_underscores(bits);
        if (inferred_width > 0) out += " width=" + std::to_string(inferred_width);
    }
    return out;
}

bool is_field_map(const Json& value) {
    if (!value.is_object() || value.empty() || is_value_object(value)) return false;
    for (auto it = value.begin(); it != value.end(); ++it) {
        if (!is_value_object(it.value())) return false;
    }
    return true;
}

std::string compact_field_map(const Json& value) {
    std::string out;
    if (!value.is_object()) return out;
    for (auto it = value.begin(); it != value.end(); ++it) {
        std::string cell = sanitize_kout_key(it.key()) + "=" + compact_value_object(it.value());
        if (!out.empty()) out.push_back(' ');
        out += cell;
    }
    return out;
}

std::string collapse_row_column(const std::string& input) {
    std::string out;
    bool in_space = false;
    for (char ch : input) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (std::isspace(uch)) {
            if (!in_space && !out.empty()) out.push_back(' ');
            in_space = true;
        } else {
            out.push_back(ch);
            in_space = false;
        }
    }
    if (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

} // namespace

TextResponseBuilder::TextResponseBuilder(std::string tool) : tool_(std::move(tool)) {}

void TextResponseBuilder::emit_header(const std::string& action) {
    if (wrote_header_) return;
    out_ << "@" << tool_ << "." << action << ".v1\n";
    wrote_header_ = true;
}

void TextResponseBuilder::emit_section(const std::string& name) {
    pending_section_ = sanitize_kout_key(name);
}

void TextResponseBuilder::emit_kv(const std::string& key, const Json& value) {
    if (is_empty_json(value)) return;
    const std::string text = json_to_kout_value(value);
    if (text.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    write_line(std::string(nested ? "  " : "") + sanitize_kout_key(key) + ": " + text);
}

void TextResponseBuilder::emit_kv(const std::string& key, const std::string& value) {
    if (value.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    write_line(std::string(nested ? "  " : "") + sanitize_kout_key(key) + ": " + sanitize_kout_value(value));
}

void TextResponseBuilder::emit_kv(const std::string& key, const char* value) {
    if (value == nullptr) return;
    emit_kv(key, std::string(value));
}

void TextResponseBuilder::emit_kv(const std::string& key, bool value) {
    emit_kv(key, std::string(value ? "true" : "false"));
}

void TextResponseBuilder::emit_kv(const std::string& key, int value) {
    emit_kv(key, std::to_string(value));
}

void TextResponseBuilder::emit_kv(const std::string& key, long long value) {
    emit_kv(key, std::to_string(value));
}

void TextResponseBuilder::emit_row(std::initializer_list<std::string> columns) {
    emit_row(std::vector<std::string>(columns.begin(), columns.end()));
}

void TextResponseBuilder::emit_row(const std::vector<std::string>& columns) {
    std::string row;
    for (const auto& col : columns) {
        std::string text = collapse_row_column(sanitize_kout_value(col));
        if (text.empty()) continue;
        if (!row.empty()) row.push_back(' ');
        row += text;
    }
    if (row.empty()) return;
    const bool nested = in_section_ || !pending_section_.empty();
    ensure_section();
    write_line(std::string(nested ? "  " : "") + row);
}

void TextResponseBuilder::emit_warning(const std::string& code, const std::string& message) {
    emit_section("warnings");
    emit_row({code, message});
}

void TextResponseBuilder::emit_raw(const std::string& text) {
    wrote_content_ = true;
    out_ << text;
}

void TextResponseBuilder::emit_error(const Json& error) {
    if (!error.is_object()) return;
    if (error.contains("code")) emit_kv("code", error["code"]);
    if (error.contains("message")) emit_kv("message", error["message"]);
    if (error.contains("recoverable")) emit_kv("recoverable", error["recoverable"]);
}

std::string TextResponseBuilder::str() const {
    std::string text = out_.str();
    while (!text.empty() && text.back() == '\n') text.pop_back();
    text.push_back('\n');
    return text;
}

void TextResponseBuilder::ensure_section() {
    if (pending_section_.empty()) return;
    if (wrote_content_) out_ << "\n";
    out_ << pending_section_ << ":\n";
    wrote_content_ = true;
    pending_section_.clear();
    in_section_ = true;
}

void TextResponseBuilder::write_line(const std::string& text) {
    if (!wrote_content_ && pending_section_.empty()) {
        if (wrote_header_) out_ << "\n";
        wrote_content_ = true;
        in_section_ = false;
    }
    out_ << text << "\n";
}

std::string sanitize_kout_key(const std::string& key) {
    std::string out;
    for (char ch : key) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (std::isalnum(uch) || ch == '_' || ch == '-' || ch == '.') {
            out.push_back(ch);
        } else {
            out.push_back('_');
        }
    }
    return out.empty() ? "field" : out;
}

std::string sanitize_kout_value(const std::string& value) {
    std::string out;
    out.reserve(std::min(value.size(), kMaxValueLength));
    for (char ch : value) {
        if (ch == '\n') {
            out += "\\n";
        } else if (ch == '\r') {
            out += "\\r";
        } else if (ch == '\t') {
            out.push_back(' ');
        } else {
            out.push_back(ch);
        }
        if (out.size() >= kMaxValueLength) {
            out += "...";
            break;
        }
    }
    return out;
}

std::string json_to_kout_value(const Json& value) {
    if (value.is_null()) return std::string();
    if (is_value_object(value)) return sanitize_kout_value(compact_value_object(value));
    if (is_field_map(value)) return sanitize_kout_value(compact_field_map(value));
    if (value.is_string()) return sanitize_kout_value(value.get<std::string>());
    if (value.is_boolean()) return value.get<bool>() ? "true" : "false";
    if (value.is_number_integer()) return std::to_string(value.get<long long>());
    if (value.is_number_unsigned()) return std::to_string(value.get<unsigned long long>());
    if (value.is_number_float()) return sanitize_kout_value(value.dump());
    return sanitize_kout_value(value.dump());
}

bool is_kout_scalar_json(const Json& value) {
    return value.is_string() || value.is_number() || value.is_boolean() ||
           is_value_object(value) || is_field_map(value);
}

bool is_kout_field_map_json(const Json& value) {
    return is_field_map(value);
}

} // namespace kdebug
