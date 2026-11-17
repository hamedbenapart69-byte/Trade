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
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace {
struct HttpResult { CURLcode transport{CURLE_FAILED_INIT}; long status_code{0}; std::string response; };
struct Provider { std::string_view name; std::string_view endpoint; std::string_view row_marker; bool okx_confirm_field; };
struct Candle { long long timestamp_ms; double low; double close; };
struct MarketData { std::vector<Candle> candles; std::string provider; };

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
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "CFSS-CPP/0.6");
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    result.transport = curl_easy_perform(curl);
    if (result.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &result.status_code);
    curl_easy_cleanup(curl);
    return result;
}

std::string trim_json_value(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n\\\"");
    if (first == std::string::npos) return {};
    const auto last = value.find_last_not_of(" \t\r\n\\\"");
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

std::vector<Candle> parse_candles(std::string_view json, std::string_view marker,
                                  bool require_okx_confirmation) {
    std::vector<Candle> candles;
    const std::size_t marker_pos = json.find(marker);
    if (marker_pos == std::string_view::npos) return candles;
    const std::size_t outer = json.find('[', marker_pos + marker.size());
    if (outer == std::string_view::npos) return candles;

    const auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
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
                        const double low = std::stod(fields[3]);
                        const double close = std::stod(fields[4]);
                        const bool confirmed = !require_okx_confirmation ||
                            (fields.size() > 8U && fields[8] == "1");
                        const bool candle_closed = ts + 900000LL <= now_ms;
                        if (ts > 0 && candle_closed && confirmed &&
                            std::isfinite(low) && low > 0.0 &&
                            std::isfinite(close) && close > 0.0) {
                            candles.push_back({ts, low, close});
                        }
                    } catch (...) {
                        // ردیف خراب حذف می‌شود؛ دادهٔ ناقص پذیرفته نمی‌شود.
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

std::optional<MarketData> fetch_ohlcv() {
    constexpr std::array<Provider, 2> providers{{
        {"OKX", "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT-SWAP&bar=15m&limit=51", "\"data\"", true},
        {"Bybit", "https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=15&limit=51", "\"list\"", false}
    }};
    for (const auto& provider : providers) {
        const HttpResult response = get(provider.endpoint);
        if (response.transport != CURLE_OK || response.status_code != 200) {
            std::cerr << provider.name << " candle fetch failed; HTTP=" << response.status_code
                      << " transport=" << curl_easy_strerror(response.transport) << '\n';
            continue;
        }
        auto candles = parse_candles(response.response, provider.row_marker, provider.okx_confirm_field);
        if (candles.size() != 50U) {
            std::cerr << provider.name << " rejected: expected 50 valid, closed, unique candles, got "
                      << candles.size() << '\n';
            continue;
        }
        std::cout << "Validated 50 closed 15m OHLCV candles from " << provider.name << '\n';
        return MarketData{std::move(candles), std::string{provider.name}};
    }
    return std::nullopt;
}

double calculate_sma20(const std::vector<Candle>& candles) {
    if (candles.size() < 20U) throw std::invalid_argument("SMA20 requires at least 20 closes");
    long double sum = 0.0L;
    for (auto it = candles.end() - 20; it != candles.end(); ++it) sum += static_cast<long double>(it->close);
    return static_cast<double>(sum / 20.0L);
}

double lowest_low_last_five(const std::vector<Candle>& candles) {
    if (candles.size() < 5U) throw std::invalid_argument("Five closed candles are required for stop-loss");
    double lowest = candles.back().low;
    for (auto it = candles.end() - 5; it != candles.end(); ++it) lowest = std::min(lowest, it->low);
    return lowest;
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

    const auto& candles = fetched->candles;
    std::vector<double> closes;
    closes.reserve(candles.size());
    for (const auto& candle : candles) closes.push_back(candle.close);
    const double current_close = closes.back();
    const double sma20 = calculate_sma20(candles);
    const std::string bias = current_close > sma20 ? "BULLISH" :
                             current_close < sma20 ? "BEARISH" : "NEUTRAL";
    std::cout << "SMA20=" << std::setprecision(15) << sma20 << " CLOSE=" << current_close
              << " BIAS=" << bias << '\n';

    if (bias != "BULLISH") {
        std::cout << "NO_QUALIFIED_SETUP: LRT SMA20 proxy requires BULLISH bias; no actionable LONG sent.\n";
        curl_global_cleanup();
        return EXIT_SUCCESS;
    }

    const double lowest_low = lowest_low_last_five(candles);
    const cfss::LongLevels levels = cfss::calculate_long_levels(current_close, lowest_low);
    const auto epoch = std::chrono::duration_cast<std::chrono::seconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    const std::string timestamp = utc_now_iso();
    const cfss::ActionableSignal signal{
        "SIG-BTC-LONG-" + std::to_string(epoch), "BTC-USDT-SWAP", "BUY_NOW", "LONG",
        levels.entry_price, levels.stop_loss, levels.take_profit, levels.risk_reward,
        "LRT_SMA20_PROXY", fetched->provider, timestamp, "PROXY", "15m",
        "15m close is above SMA20; basic LRT proxy LONG candidate.",
        "A subsequent 15m close at or below SMA20 invalidates the bias; stop-loss is the price-risk boundary.",
        levels.used_fallback
    };
    const std::string signal_json = cfss::format_signal_json(signal);
    const std::string telegram_markdown = cfss::format_signal_markdown(signal);
    std::cout << "SIGNAL_JSON=" << signal_json << '\n';
    std::cout << "TELEGRAM_MARKDOWN_BEGIN\n" << telegram_markdown << "\nTELEGRAM_MARKDOWN_END\n";

    const char* token = std::getenv("TELEGRAM_TOKEN");
    const char* chat_id = std::getenv("TELEGRAM_CHAT_ID");
    if (!token || !chat_id || token[0] == '\0' || chat_id[0] == '\0') {
        std::cerr << "Telegram secrets unavailable; signal not delivered\n";
        curl_global_cleanup();
        return EXIT_FAILURE;
    }
    const bool delivered = cfss::send_telegram_message(token, chat_id, telegram_markdown);
    curl_global_cleanup();
    return delivered ? EXIT_SUCCESS : EXIT_FAILURE;
}
