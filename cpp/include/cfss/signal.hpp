#pragma once
#include <curl/curl.h>
#include "cfss/http_utils.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <stdexcept>

namespace cfss {
struct LongLevels {
    double entry_price{};
    double stop_loss{};
    double take_profit{};
    double risk_reward{};
    bool used_fallback{};
};

// حدضرر از کف پنج کندل بسته‌شده؛ در صورت نامعتبر بودن، ریسک ثابت ۱٪.
inline LongLevels calculate_long_levels(double entry, double lowest_low) {
    if (!std::isfinite(entry) || entry <= 0.0) {
        throw std::invalid_argument("Entry must be finite and positive");
    }
    double stop = lowest_low;
    bool fallback = !std::isfinite(stop) || stop <= 0.0 || stop >= entry;
    if (fallback) stop = entry * 0.99;
    const double risk = entry - stop;
    if (!std::isfinite(risk) || risk <= 0.0) {
        stop = entry * 0.99;
        fallback = true;
    }
    const double valid_risk = entry - stop;
    const double target = entry + 2.0 * valid_risk;
    const double rr = (target - entry) / valid_risk;
    if (!std::isfinite(target) || target <= entry || !std::isfinite(rr) || rr <= 0.0) {
        throw std::runtime_error("Unable to calculate valid LONG levels");
    }
    return {entry, stop, target, rr, fallback};
}

struct ActionableSignal {
    std::string signal_id;
    std::string symbol;
    std::string state;
    std::string direction;
    double entry_price{};
    double stop_loss{};
    double take_profit{};
    double risk_reward{};
    std::string strategy;
    std::string provider;
    std::string timestamp_utc;
    std::string data_quality{"PROXY"};
    std::string timeframe{"15m"};
    std::string hypothesis;
    std::string falsification;
    bool stop_fallback{};
};

inline std::string format_signal_json(const ActionableSignal& signal) {
    std::ostringstream out;
    out << std::setprecision(15)
        << "{\"signal_id\":\"" << json_escape(signal.signal_id)
        << "\",\"symbol\":\"" << json_escape(signal.symbol)
        << "\",\"state\":\"" << json_escape(signal.state)
        << "\",\"direction\":\"" << json_escape(signal.direction)
        << "\",\"entry_price\":" << signal.entry_price
        << ",\"stop_loss\":" << signal.stop_loss
        << ",\"take_profit\":" << signal.take_profit
        << ",\"risk_reward\":" << signal.risk_reward
        << ",\"strategy\":\"" << json_escape(signal.strategy)
        << "\",\"provider\":\"" << json_escape(signal.provider)
        << "\",\"timestamp_utc\":\"" << json_escape(signal.timestamp_utc)
        << "\",\"data_quality\":\"" << json_escape(signal.data_quality)
        << "\",\"timeframe\":\"" << json_escape(signal.timeframe)
        << "\",\"hypothesis\":\"" << json_escape(signal.hypothesis)
        << "\",\"falsification\":\"" << json_escape(signal.falsification)
        << "\",\"stop_fallback_1pct\":" << (signal.stop_fallback ? "true" : "false")
        << ",\"confidence_status\":\"NOT_CALIBRATED\"}";
    return out.str();
}

inline std::string format_signal_markdown(const ActionableSignal& signal) {
    std::ostringstream out;
    out << std::fixed << std::setprecision(2)
        << "*BUY NOW | LONG*\n"
        << "*" << signal.symbol << "*  |  " << signal.timeframe << "\n"
        << "Entry: `" << signal.entry_price << "`\n"
        << "Stop Loss: `" << signal.stop_loss << "`\n"
        << "Take Profit: `" << signal.take_profit << "`\n"
        << "Risk/Reward: *1:" << signal.risk_reward << "*\n"
        << "Strategy: `" << signal.strategy << "`\n"
        << "Provider: " << signal.provider << "  |  Data: *" << signal.data_quality << "*\n"
        << "Confidence: `NOT_CALIBRATED`\n"
        << "Hypothesis: " << signal.hypothesis << "\n"
        << "Invalidation: " << signal.falsification << "\n"
        << "UTC: " << signal.timestamp_utc << "\n"
        << "ID: `" << signal.signal_id << "`";
    if (signal.stop_fallback) out << "\n*Warning: 1% fallback stop used*";
    return out.str();
}

inline bool send_telegram_message(const std::string& token, const std::string& chat_id,
                                  const std::string& message, std::string* response_out = nullptr,
                                  bool log_response = true) {
    CURL* curl = curl_easy_init();
    if (!curl) return false;
    const std::string endpoint = "https://api.telegram.org/bot" + token + "/sendMessage";
    const std::string payload = "{\"chat_id\":\"" + json_escape(chat_id) +
        "\",\"text\":\"" + json_escape(message) + "\",\"parse_mode\":\"Markdown\"}";
    std::string response;
    curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    if (!headers) { curl_easy_cleanup(curl); return false; }
    curl_easy_setopt(curl, CURLOPT_URL, endpoint.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(payload.size()));
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, append_response);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    const CURLcode result = curl_easy_perform(curl);
    long status = 0;
    if (result == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    if (response_out) *response_out = response;
    if (log_response) {
        std::cout << "Telegram HTTP status: " << status << '\n';
        std::cout << "Telegram API response: " << response << '\n';
    }
    return result == CURLE_OK && status == 200 &&
           response.find("\"ok\":true") != std::string::npos;
}
} // namespace cfss
