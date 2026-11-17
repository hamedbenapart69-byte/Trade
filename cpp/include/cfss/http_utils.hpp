#pragma once
#include <cstddef>
#include <cstdlib>
#include <string>
#include <string_view>
#include <optional>
#include <cctype>

namespace cfss {
inline std::size_t append_response(char* data, std::size_t size, std::size_t count, void* context) {
    if (size != 0U && count > static_cast<std::size_t>(-1) / size) return 0U;
    const std::size_t bytes = size * count;
    if (!context) return 0U;
    static_cast<std::string*>(context)->append(data, bytes);
    return bytes;
}

// استخراج و اعتبارسنجی یک مقدار عددی از کلید JSON.
inline std::optional<std::string> extract_json_number(std::string_view json, std::string_view key) {
    const std::string needle = "\"" + std::string{key} + "\"";
    const std::size_t key_pos = json.find(needle);
    if (key_pos == std::string_view::npos) return std::nullopt;
    const std::size_t colon = json.find(':', key_pos + needle.size());
    if (colon == std::string_view::npos) return std::nullopt;
    std::size_t begin = colon + 1U;
    while (begin < json.size() && std::isspace(static_cast<unsigned char>(json[begin])) != 0) ++begin;
    const bool quoted = begin < json.size() && json[begin] == '"';
    if (quoted) ++begin;
    std::size_t end = begin;
    while (end < json.size()) {
        const char ch = json[end];
        if (!((ch >= '0' && ch <= '9') || ch == '.' || ch == '-' || ch == '+' || ch == 'e' || ch == 'E')) break;
        ++end;
    }
    if (end == begin || (quoted && (end >= json.size() || json[end] != '"'))) return std::nullopt;
    const std::string value{json.substr(begin, end - begin)};
    char* parsed_end = nullptr;
    const double number = std::strtod(value.c_str(), &parsed_end);
    if (parsed_end == value.c_str() || *parsed_end != '\0' || !(number > 0.0)) return std::nullopt;
    return value;
}

inline std::string json_escape(std::string_view input) {
    constexpr char hex[] = "0123456789abcdef";
    std::string output;
    output.reserve(input.size() + 8U);
    for (const char raw_ch : input) {
        const auto ch = static_cast<unsigned char>(raw_ch);
        switch (ch) {
            case '"': output += "\\""; break;
            case '\\': output += "\\\\"; break;
            case '\b': output += "\\b"; break;
            case '\f': output += "\\f"; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default:
                if (ch < 0x20U) { output += "\\u00"; output += hex[(ch >> 4U) & 0x0fU]; output += hex[ch & 0x0fU]; }
                else output += static_cast<char>(ch);
        }
    }
    return output;
}
inline std::string telegram_payload(std::string_view chat_id, std::string_view message) {
    return "{\"chat_id\":\"" + json_escape(chat_id) + "\",\"text\":\"" + json_escape(message) + "\"}";
}
} // namespace cfss