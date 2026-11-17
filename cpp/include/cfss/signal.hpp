#pragma once
#include <curl/curl.h>
#include "cfss/http_utils.hpp"
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

namespace cfss {
struct SignalSnapshot {
    std::string signal_id;
    std::string symbol;
    std::string direction_bias;
    double current_price;
    std::string indicator;
    double indicator_value;
    std::string data_provider;
    std::string timestamp_utc;
};

inline std::string format_signal_json(const SignalSnapshot& signal) {
    std::ostringstream out;
    out << std::setprecision(15)
        << "{\"signal_id\":\"" << json_escape(signal.signal_id)
        << "\",\"symbol\":\"" << json_escape(signal.symbol)
        << "\",\"direction_bias\":\"" << json_escape(signal.direction_bias)
        << "\",\"current_price\":" << signal.current_price
        << ",\"indicator\":\"" << json_escape(signal.indicator)
        << "\",\"indicator_value\":" << signal.indicator_value
        << ",\"data_provider\":\"" << json_escape(signal.data_provider)
        << "\",\"timestamp_utc\":\"" << json_escape(signal.timestamp_utc) << "\"}";
    return out.str();
}

inline bool send_telegram_json(const std::string& token, const std::string& chat_id,
                              const std::string& signal_json) {
    CURL* curl = curl_easy_init();
    if (!curl) return false;
    const std::string endpoint = "https://api.telegram.org/bot" + token + "/sendMessage";
    const std::string payload = telegram_payload(chat_id, signal_json);
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
    std::cout << "Telegram HTTP status: " << status << '\n';
    std::cout << "Telegram API response: " << response << '\n';
    return result == CURLE_OK && status == 200 &&
           response.find("\"ok\":true") != std::string::npos;
}
} // namespace cfss