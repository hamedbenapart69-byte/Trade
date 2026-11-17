#include <curl/curl.h>
#include "cfss/http_utils.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>

namespace {
struct HttpResult { CURLcode transport{CURLE_FAILED_INIT}; long status_code{0}; std::string response; };
struct Provider { std::string_view name; std::string_view endpoint; std::string_view price_key; };
struct PriceResult { std::string provider; std::string price; };

HttpResult perform_request(std::string_view url) {
    HttpResult result;
    CURL* handle = curl_easy_init();
    if (!handle) { std::cerr << "HTTP client initialization failed\n"; return result; }
    const std::string url_string{url};
    curl_easy_setopt(handle, CURLOPT_URL, url_string.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &result.response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-CPP/0.4");
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
    result.transport = curl_easy_perform(handle);
    if (result.transport == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &result.status_code);
    curl_easy_cleanup(handle);
    return result;
}

void log_failure(const Provider& provider, const HttpResult& response, std::string_view reason) {
    std::cerr << provider.name << " rejected: " << reason << " (HTTP " << response.status_code << ")\n";
    if (response.transport != CURLE_OK) std::cerr << "Transport detail: " << curl_easy_strerror(response.transport) << '\n';
}

std::optional<PriceResult> fetch_price() {
    // همه منابع، قیمت آخرین معاملهٔ قرارداد دائمی خطی BTC/USDT را می‌دهند.
    constexpr std::array<Provider, 3> providers{{
        {"OKX", "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP", "last"},
        {"Bybit", "https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT", "lastPrice"},
        {"Binance", "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT", "price"},
    }};
    for (const Provider& provider : providers) {
        const HttpResult response = perform_request(provider.endpoint);
        if (response.transport != CURLE_OK) { log_failure(provider, response, "network/timeout error"); continue; }
        if (response.status_code != 200) { log_failure(provider, response, "non-200 response"); continue; }
        const auto price = cfss::extract_json_number(response.response, provider.price_key);
        if (!price) { log_failure(provider, response, "missing or invalid JSON price"); continue; }
        std::cout << provider.name << " returned validated perpetual price: " << *price << '\n';
        return PriceResult{std::string{provider.name}, *price};
    }
    return std::nullopt;
}

bool send_telegram_message(const std::string& token, const std::string& chat_id, const std::string& message) {
    CURL* handle = curl_easy_init();
    if (!handle) { std::cerr << "Telegram HTTP client initialization failed\n"; return false; }
    const std::string endpoint = "https://api.telegram.org/bot" + token + "/sendMessage";
    const std::string payload = cfss::telegram_payload(chat_id, message);
    std::string response;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    if (!headers) { curl_easy_cleanup(handle); return false; }
    curl_easy_setopt(handle, CURLOPT_URL, endpoint.c_str());
    curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(handle, CURLOPT_POST, 1L);
    curl_easy_setopt(handle, CURLOPT_POSTFIELDS, payload.c_str());
    curl_easy_setopt(handle, CURLOPT_POSTFIELDSIZE, static_cast<long>(payload.size()));
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
    const CURLcode transport = curl_easy_perform(handle);
    long status = 0;
    if (transport == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &status);
    else std::cerr << "Telegram POST transport failed: " << curl_easy_strerror(transport) << '\n';
    curl_slist_free_all(headers);
    curl_easy_cleanup(handle);
    std::cout << "Telegram HTTP status: " << status << '\n';
    std::cout << "Telegram API response: " << response << '\n';
    return transport == CURLE_OK && status == 200 && response.find("\"ok\":true") != std::string::npos;
}
} // namespace

int main() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) { std::cerr << "libcurl global initialization failed\n"; return EXIT_FAILURE; }
    const auto result = fetch_price();
    if (!result) { std::cerr << "No provider returned an equivalent validated perpetual price; UNAVAILABLE\n"; curl_global_cleanup(); return EXIT_FAILURE; }
    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || token[0] == '\0' || !chat_id || chat_id[0] == '\0') {
        std::cerr << "Telegram delivery NOT_PERFORMED: TELEGRAM_TOKEN/TELEGRAM_CHAT_ID missing\n";
        curl_global_cleanup(); return EXIT_FAILURE;
    }
    const std::string message = "CFSS V18.2: " + result->provider + " Data Fetched Successfully. Price: " + result->price;
    const bool delivered = send_telegram_message(token, chat_id, message);
    curl_global_cleanup();
    if (!delivered) { std::cerr << "Telegram delivery failed; no delivery receipt confirmed\n"; return EXIT_FAILURE; }
    std::cout << "L1 provider=" << result->provider << " L3 Telegram delivery confirmed\n";
    return EXIT_SUCCESS;
}