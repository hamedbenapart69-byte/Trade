#pragma once

#include <cstddef>
#include <string>
#include <string_view>

namespace cfss {

// پاسخ دریافتی libcurl را در رشتهٔ مقصد جمع می‌کند.
inline std::size_t append_response(char* data, std::size_t size,
                                   std::size_t count, void* context) {
    if (size != 0U && count > static_cast<std::size_t>(-1) / size) {
        return 0U;
    }
    const std::size_t bytes = size * count;
    if (context == nullptr) {
        return 0U;
    }
    static_cast<std::string*>(context)->append(data, bytes);
    return bytes;
}

// رشته را برای قرار گرفتن در مقدار JSON ایمن می‌کند.
inline std::string json_escape(std::string_view input) {
    constexpr char hex[] = "0123456789abcdef";
    std::string output;
    output.reserve(input.size() + 8U);
    for (const unsigned char ch : input) {
        switch (ch) {
            case '"': output += "\\\""; break;
            case '\\': output += "\\\\"; break;
            case '\b': output += "\\b"; break;
            case '\f': output += "\\f"; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default:
                if (ch < 0x20U) {
                    output += "\\u00";
                    output += hex[(ch >> 4U) & 0x0fU];
                    output += hex[ch & 0x0fU];
                } else {
                    output += static_cast<char>(ch);
                }
        }
    }
    return output;
}

inline std::string telegram_payload(std::string_view chat_id,
                                    std::string_view message) {
    return "{\"chat_id\":\"" + json_escape(chat_id) +
           "\",\"text\":\"" + json_escape(message) + "\"}";
}

}  // namespace cfss
