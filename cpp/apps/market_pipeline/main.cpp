#include <curl/curl.h>
#include "cfss/http_utils.hpp"
#include "cfss/signal.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace {
struct HttpResult { CURLcode transport{CURLE_FAILED_INIT}; long status_code{0}; std::string response; };
struct Provider { std::string_view name; std::string_view endpoint; std::string_view row_marker; };
struct Candle { long long timestamp_ms; double close; };

HttpResult get(std::string_view url) {
    HttpResult result;
    CURL* curl = curl_easy_init();
    if (!curl) return result;
    const std::string url_text{url};
    curl_easy_setopt(curl, CURLOPT_URL, url_text.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, cfss::append_response);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &result.response);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 25L);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "CFSS-CPP/0.5");
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    result.transport = curl_easy_perform(curl);
    if (result.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &result.status_code);
    curl_easy_cleanup(curl);
    return result;
}

std::string trim_json_value(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n\"");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n\"");
    return value.substr(first, last - first + 1U);
}

std::vector<std::string> split_json_row(std::string_view row) {
    std::vector<std::string> fields;
    bool in_string = false;
    bool escaped = false;
    std::size_t start = 0;
    for (std::size_t i = 0; i < row.size(); ++i) {
        const char ch = row[i];
        if (in_string && escaped) { escaped = false; continue; }
        if (in_string && ch == '\\') { escaped = true; continue; }
        if (ch == '"') { in_string = !in_string; continue; }
        if (ch == ',' && !in_string) {
            fields.emplace_back(trim_json_value(std::string{row.substr(start, i - start)}));
            start = i + 1U;
        }
    }
    if (start <= row.size()) fields.emplace_back(trim_json_value(std::string{row.substr(start)}));
    return fields;
}

std::vector<Candle> parse_candles(std::string_view json, std::string_view marker) {
    std::vector<Candle> candles;
    const std::size_t marker_pos = json.find(marker);
    if (marker_pos == std::string_view::npos) return candles;
    const std::size_t outer = json.find('[', marker_pos + marker.size());
    if (outer == std::string_view::npos) return candles;

    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    std::size_t row_start = std::string_view::npos;
    for (std::size_t i = outer; i < json.size(); ++i) {
        const char ch = json[i];
        if (in_string && escaped) { escaped = false; continue; }
        if (in_string && ch == '\\') { escaped = true; continue; }
        if (ch == '"') { in_string = !in_string; continue; }
        if (in_string) continue;
        if (ch == '[') {
            ++depth;
            if (depth == 2) row_start = i + 1U;
        } else if (ch == ']') {
            if (depth == 2 && row_start != std::string_view::npos) {
                const auto fields = split_json_row(json.substr(row_start, i - row_start));
                if (fields.size() >= 5U) {
                    try {
                        const long long ts = std::stoll(fields[0]);
                        const double close = std::stod(fields[4]);
                        if (ts > 0 && std::isfinite(close) && close > 0.0) candles.push_back({ts, close});
                    } catch (...) {
                        // ردیف خراب حذف می‌شود؛ پذیرش دادهٔ ناقص ممنوع است.
                    }
                }
                row_start = std::string_view::npos;
            }
            --depth;
            if (depth == 0) break;
        }
    }
    std::sort(candles.begin(), candles.end(), [](const Candle& a, const Candle& b) {
        return a.timestamp_ms < b.timestamp_ms;
    });
    candles.erase(std::unique(candles.begin(), candles.end(), [](const Candle& a, const Candle& b) {
        return a.timestamp_ms == b.timestamp_ms;
    }), candles.end());
    if (candles.size() > 50U) candles.erase(candles.begin(), candles.end() - 50);
    return candles;
}

std::optional<std::pair<std::vector<double>, std::string>> fetch_ohlcv() {
    constexpr std::array<Provider, 2> providers{{
        {"OKX", "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=15m&limit=50", "\"data\""},
        {"Bybit", "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=15&limit=50", "\"list\""}
    }};
    for (const auto& provider : providers) {
        const HttpResult response = get(provider.endpoint);
        if (response.transport != CURLE_OK || response.status_code != 200) {
            std::cerr << provider.name << " candle fetch failed; HTTP=" << response.status_code
                      << " transport=" << curl_easy_strerror(response.transport) << '\n';
            continue;
        }
        auto candles = parse_candles(response.response, provider.row_marker);
        if (candles.size() != 50U) {
            std::cerr << provider.name << " rejected: expected 50 valid unique candles, got "
                      << candles.size() << '\n';
            continue;
        }
        std::vector<double> closes;
        closes.reserve(candles.size());
        for (const auto& candle : candles) closes.push_back(candle.close);
        std::cout << "Validated 50 x 15m candles from " << provider.name << '\n';
        return std::make_pair(std::move(closes), std::string{provider.name});
    }
    return std::nullopt;
}

double calculate_sma20(const std::vector<double>& closes) {
    if (closes.size() < 20U) throw std::invalid_argument("SMA20 requires at least 20 closes");
    long double sum = 0.0L;
    for (auto it = closes.end() - 20; it != closes.end(); ++it) sum += static_cast<long double>(*it);
    return static_cast<double>(sum / 20.0L);
}

std::string utc_now_iso() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &time);
#else
    gmtime_r(&time, &utc);
#endif
    std::ostringstream out;
    out << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return out.str();
}
} // namespace

int main() {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return EXIT_FAILURE;
    const auto fetched = fetch_ohlcv();
    if (!fetched) {
        std::cerr << "OHLCV unavailable from OKX and Bybit; MARKET_DATA_DEGRADED\n";
        curl_global_cleanup();
        return EXIT_FAILURE;
    }
    const auto& closes = fetched->first;
    const double current_close = closes.back();
    const double sma20 = calculate_sma20(closes);
    const std::string bias = current_close > sma20 ? "BULLISH" :
                             current_close < sma20 ? "BEARISH" : "NEUTRAL";
    const auto epoch = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    const cfss::SignalSnapshot signal{
        "SIG-BTC-" + std::to_string(epoch), "BTC-USDT-SWAP", bias,
        current_close, "SMA_20", sma20, fetched->second, utc_now_iso()
    };
    const std::string signal_json = cfss::format_signal_json(signal);
    std::cout << "SIGNAL_JSON=" << signal_json << '\n';

    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || !chat_id || token[0] == '\0' || chat_id[0] == '\0') {
        std::cerr << "Telegram secrets unavailable; signal not delivered\n";
        curl_global_cleanup();
        return EXIT_FAILURE;
    }
    const bool delivered = cfss::send_telegram_json(token, chat_id, signal_json);
    curl_global_cleanup();
    if (!delivered) return EXIT_FAILURE;
    std::cout << "Telegram signal JSON delivered and acknowledged\n";
    return EXIT_SUCCESS;
}
