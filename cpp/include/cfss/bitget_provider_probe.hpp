#pragma once

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace cfss::bitget {
using json = nlohmann::json;

constexpr std::int64_t kHourMs = 3'600'000LL;
constexpr std::int64_t kDayMs = 86'400'000LL;
constexpr std::int64_t kTwoYearsMs = 730LL * kDayMs;
constexpr std::int64_t kThirtyDaysMs = 30LL * kDayMs;

struct HttpResponse {
    long status{0};
    CURLcode transport{CURLE_FAILED_INIT};
    std::string body;
};

inline std::size_t write_body(char* data, std::size_t size, std::size_t count, void* context) {
    if (!context || (size != 0U && count > static_cast<std::size_t>(-1) / size)) return 0U;
    const std::size_t bytes = size * count;
    static_cast<std::string*>(context)->append(data, bytes);
    return bytes;
}

inline HttpResponse get(const std::string& url, long timeout_seconds = 25L) {
    HttpResponse out;
    CURL* curl = curl_easy_init();
    if (!curl) throw std::runtime_error("bitget_curl_init_failed");
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &out.body);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_seconds);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "CFSS-CXX20-Bitget-ResearchProbe/1.0");
    out.transport = curl_easy_perform(curl);
    if (out.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &out.status);
    curl_easy_cleanup(curl);
    return out;
}

inline bool retryable(const HttpResponse& response) {
    return response.transport != CURLE_OK || response.status == 408L ||
        response.status == 429L || (response.status >= 500L && response.status <= 599L);
}

inline json request_json(const std::string& path, int attempts = 3) {
    const std::string url = "https://api.bitget.com" + path;
    std::string last_error = "bitget_request_failed";
    for (int attempt = 0; attempt < attempts; ++attempt) {
        const auto response = get(url);
        if (response.transport == CURLE_OK && response.status == 200L) {
            json payload;
            try {
                payload = json::parse(response.body);
            } catch (const std::exception& error) {
                throw std::runtime_error(std::string{"bitget_json_parse_failed:"} + error.what());
            }
            if (payload.value("code", std::string{}) == "00000" && payload.contains("data"))
                return payload;
            last_error = "bitget_api_error:" + payload.value("code", std::string{"MISSING_CODE"}) +
                ":" + payload.value("msg", std::string{});
        } else {
            last_error = "bitget_http_or_transport_error:" + std::to_string(response.status) +
                ":" + curl_easy_strerror(response.transport);
        }
        if (!retryable(response) || attempt + 1 >= attempts) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(500 * (1 << attempt)));
    }
    throw std::runtime_error(last_error);
}

inline std::optional<double> number(const json& value) {
    if (value.is_number()) {
        const double parsed = value.get<double>();
        if (std::isfinite(parsed)) return parsed;
        return std::nullopt;
    }
    if (value.is_string()) {
        try {
            const auto raw = value.get<std::string>();
            std::size_t used = 0U;
            const double parsed = std::stod(raw, &used);
            if (used == raw.size() && std::isfinite(parsed)) return parsed;
        } catch (...) {}
    }
    return std::nullopt;
}

inline std::int64_t timestamp(const json& value) {
    if (value.is_number_integer()) return value.get<std::int64_t>();
    if (value.is_string()) {
        try {
            std::size_t used = 0U;
            const auto raw = value.get<std::string>();
            const auto parsed = std::stoll(raw, &used);
            if (used == raw.size()) return parsed;
        } catch (...) {}
    }
    return 0;
}

inline std::string text(const json& object, const char* key) {
    if (!object.is_object() || !object.contains(key) || object.at(key).is_null()) return {};
    if (object.at(key).is_string()) return object.at(key).get<std::string>();
    return object.at(key).dump();
}

inline bool valid_symbol(const std::string& symbol) {
    return !symbol.empty() && symbol.size() <= 24U &&
        std::all_of(symbol.begin(), symbol.end(), [](unsigned char value) {
            return (value >= 'A' && value <= 'Z') || (value >= '0' && value <= '9');
        });
}

inline json find_instrument(const json& payload, const std::string& symbol) {
    if (!payload.is_object() || !payload.contains("data")) return json{};
    const auto& rows = payload.at("data");
    if (!rows.is_array()) return json{};
    for (const auto& row : rows) {
        if (text(row, "symbol") == symbol) return row;
    }
    return json{};
}

inline bool valid_crypto_usdt_perpetual(const json& instrument, const std::string& symbol) {
    if (!instrument.is_object()) return false;
    const auto instrument_symbol = text(instrument, "symbol");
    const auto category = text(instrument, "category");
    const auto base = text(instrument, "baseCoin");
    const auto quote = text(instrument, "quoteCoin");
    const auto instrument_type = text(instrument, "instrumentType");
    const auto status = text(instrument, "status");
    const auto futures_type = text(instrument, "type");
    const auto launch_time = timestamp(instrument.value("launchTime", json{}));
    // Bitget may return launchTime=0 for perpetual contracts. This is not proof
    // of a recent listing; the caller must then require a complete 730-day OHLCV
    // window rather than infer the listing date.
    return instrument_symbol == symbol && category == "USDT-FUTURES" &&
        quote == "USDT" && !base.empty() && instrument_type == "crypto" &&
        status == "online" && futures_type == "perpetual" && launch_time >= 0 &&
        (instrument.value("settleCoin", std::string{"USDT"}) == "USDT");
}

// دادهٔ کندل Bitget در V3 بر حسب دارایی پایه و گردش مظنه ارائه می‌شود.
// این تابع هرگز حجم BASE_COIN را به‌اشتباه CONTRACTS نام‌گذاری نمی‌کند.
inline json normalize_candles(const json& rows, const std::string& base,
                              std::int64_t now_ms) {
    if (!rows.is_array()) throw std::invalid_argument("bitget_candle_rows_not_array");
    std::map<std::int64_t, json> unique;
    for (const auto& row : rows) {
        if (!row.is_array() || row.size() < 7U) continue;
        const auto ts = timestamp(row[0]);
        const auto open = number(row[1]);
        const auto high = number(row[2]);
        const auto low = number(row[3]);
        const auto close = number(row[4]);
        const auto volume_base = number(row[5]);
        const auto volume_quote = number(row[6]);
        if (ts <= 0 || ts % kHourMs != 0 || ts + kHourMs > now_ms ||
            !open || !high || !low || !close || !volume_base || !volume_quote ||
            *open <= 0.0 || *high <= 0.0 || *low <= 0.0 || *close <= 0.0 ||
            *volume_base < 0.0 || *volume_quote < 0.0 ||
            *high < std::max({*open, *low, *close}) ||
            *low > std::min({*open, *high, *close})) continue;
        unique[ts] = {
            {"timestamp_ms", ts}, {"open", *open}, {"high", *high},
            {"low", *low}, {"close", *close},
            {"volume", *volume_base}, {"volume_unit", "BASE_COIN"},
            {"volume_base", *volume_base}, {"volume_base_currency", base},
            {"volume_quote", *volume_quote}, {"volume_quote_currency", "USDT"},
            {"closed", true}
        };
    }
    json output = json::array();
    for (const auto& [ts, candle] : unique) {
        (void)ts;
        output.push_back(candle);
    }
    return output;
}

inline json normalize_funding(const json& rows, std::int64_t cutoff_ms,
                              std::int64_t now_ms) {
    if (!rows.is_array()) throw std::invalid_argument("bitget_funding_rows_not_array");
    std::map<std::int64_t, json> unique;
    for (const auto& row : rows) {
        const auto ts = timestamp(row.value("fundingRateTimestamp", json{}));
        const auto rate = number(row.value("fundingRate", json{}));
        if (ts <= 0 || ts < cutoff_ms || ts > now_ms || !rate) continue;
        unique[ts] = {{"timestamp_ms", ts}, {"funding_rate", *rate},
                      {"funding_rate_unit", "fraction"},
                      {"provider_id", "bitget"}};
    }
    json output = json::array();
    for (const auto& [ts, item] : unique) {
        (void)ts;
        output.push_back(item);
    }
    return output;
}

inline json normalize_open_interest(const json& rows, std::int64_t cutoff_ms,
                                    std::int64_t now_ms) {
    if (!rows.is_array()) throw std::invalid_argument("bitget_oi_rows_not_array");
    std::map<std::int64_t, json> unique;
    for (const auto& row : rows) {
        const auto ts = timestamp(row.value("timestamp", json{}));
        const auto amount_base = number(row.value("openInterest", json{}));
        const auto value_quote = number(row.value("openInterestValue", json{}));
        if (ts <= 0 || ts < cutoff_ms || ts > now_ms ||
            !amount_base || !value_quote || *amount_base <= 0.0 || *value_quote <= 0.0) continue;
        unique[ts] = {
            {"timestamp_ms", ts}, {"open_interest_base", *amount_base},
            {"open_interest_base_unit", "BASE_COIN"},
            {"open_interest_value_quote", *value_quote},
            {"open_interest_value_unit", "USDT"}, {"provider_id", "bitget"}
        };
    }
    json output = json::array();
    for (const auto& [ts, item] : unique) {
        (void)ts;
        output.push_back(item);
    }
    return output;
}

struct Coverage {
    std::size_t count{0U};
    std::int64_t first_ms{0};
    std::int64_t last_ms{0};
    double days{0.0};
    std::size_t missing_intervals{0U};
};

inline Coverage coverage(const json& rows, const char* timestamp_key,
                         std::int64_t interval_ms) {
    Coverage out;
    if (!rows.is_array() || rows.empty() || interval_ms <= 0) return out;
    std::vector<std::int64_t> times;
    times.reserve(rows.size());
    for (const auto& row : rows) {
        if (!row.is_object()) continue;
        const auto ts = timestamp(row.value(timestamp_key, json{}));
        if (ts > 0) times.push_back(ts);
    }
    if (times.empty()) return out;
    std::sort(times.begin(), times.end());
    times.erase(std::unique(times.begin(), times.end()), times.end());
    out.count = times.size();
    out.first_ms = times.front();
    out.last_ms = times.back();
    out.days = static_cast<double>(out.last_ms - out.first_ms) /
        static_cast<double>(kDayMs);
    for (std::size_t i = 1U; i < times.size(); ++i) {
        const auto delta = times[i] - times[i - 1U];
        if (delta > interval_ms) {
            const auto missing = (delta - 1LL) / interval_ms;
            out.missing_intervals += static_cast<std::size_t>(missing);
        }
    }
    return out;
}

inline json fetch_instrument(const std::string& symbol) {
    const auto payload = request_json("/api/v3/market/instruments?category=USDT-FUTURES&symbol=" + symbol);
    return find_instrument(payload, symbol);
}

inline json fetch_ticker(const std::string& symbol) {
    const auto payload = request_json("/api/v3/market/tickers?category=USDT-FUTURES&symbol=" + symbol);
    if (!payload.contains("data") || !payload.at("data").is_array())
        throw std::runtime_error("bitget_ticker_payload_shape_invalid");
    for (const auto& row : payload.at("data")) {
        if (text(row, "symbol") == symbol) return row;
    }
    throw std::runtime_error("bitget_ticker_symbol_missing");
}

inline json fetch_ohlcv_two_years(const std::string& symbol, const std::string& base,
                                  std::int64_t start_ms, std::int64_t end_ms) {
    if (!valid_symbol(symbol) || start_ms <= 0 || end_ms <= start_ms)
        throw std::invalid_argument("bitget_ohlcv_request_invalid");
    constexpr std::int64_t kChunkHours = 100LL;
    const std::int64_t chunk_ms = kChunkHours * kHourMs;
    std::map<std::int64_t, json> rows;
    std::int64_t cursor = end_ms;
    std::size_t pages = 0U;
    while (cursor > start_ms) {
        const auto chunk_start = std::max(start_ms, cursor - chunk_ms);
        const auto request_start = chunk_start > 0 ? chunk_start - 1LL : chunk_start;
        const std::string path = "/api/v3/market/history-candles?category=USDT-FUTURES&symbol=" +
            symbol + "&interval=1H&startTime=" + std::to_string(request_start) +
            "&endTime=" + std::to_string(cursor) + "&limit=100";
        const auto payload = request_json(path);
        if (!payload.at("data").is_array())
            throw std::runtime_error("bitget_history_candles_shape_invalid");
        const auto normalized = normalize_candles(payload.at("data"), base, end_ms + kHourMs);
        for (const auto& candle : normalized) {
            const auto ts = candle.at("timestamp_ms").get<std::int64_t>();
            if (ts >= chunk_start && ts < cursor) rows[ts] = candle;
        }
        cursor = chunk_start;
        ++pages;
        if (pages > 200U) throw std::runtime_error("bitget_history_candles_page_guard_exceeded");
        std::this_thread::sleep_for(std::chrono::milliseconds(60));
    }
    json output = json::array();
    for (const auto& [ts, candle] : rows) {
        (void)ts;
        output.push_back(candle);
    }
    return output;
}

inline json fetch_funding_last_30d(const std::string& symbol,
                                   std::int64_t cutoff_ms, std::int64_t now_ms) {
    if (!valid_symbol(symbol)) throw std::invalid_argument("bitget_funding_symbol_invalid");
    std::map<std::int64_t, json> rows;
    for (int page = 1; page <= 100; ++page) {
        const std::string path = "/api/v3/market/history-fund-rate?category=USDT-FUTURES&symbol=" +
            symbol + "&limit=100&cursor=" + std::to_string(page);
        const auto payload = request_json(path);
        if (!payload.at("data").is_object() ||
            !payload.at("data").contains("resultList") ||
            !payload.at("data").at("resultList").is_array())
            throw std::runtime_error("bitget_funding_history_shape_invalid");
        const auto& items = payload.at("data").at("resultList");
        if (items.empty()) break;
        bool older_than_cutoff = false;
        for (const auto& row : items) {
            const auto ts = timestamp(row.value("fundingRateTimestamp", json{}));
            const auto rate = number(row.value("fundingRate", json{}));
            if (ts > 0 && ts < cutoff_ms) older_than_cutoff = true;
            if (ts <= 0 || ts < cutoff_ms || ts > now_ms || !rate) continue;
            rows[ts] = {{"timestamp_ms", ts}, {"funding_rate", *rate},
                        {"funding_rate_unit", "fraction"}, {"provider_id", "bitget"}};
        }
        if (older_than_cutoff || items.size() < 100U) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(75));
    }
    json output = json::array();
    for (const auto& [ts, item] : rows) {
        (void)ts;
        output.push_back(item);
    }
    return output;
}

inline json fetch_open_interest_last_30d(const std::string& symbol,
                                         std::int64_t cutoff_ms, std::int64_t now_ms) {
    if (!valid_symbol(symbol)) throw std::invalid_argument("bitget_oi_symbol_invalid");
    const std::string path = "/api/v3/market/open-interest-history?symbol=" +
        symbol + "&period=1h";
    const auto payload = request_json(path);
    if (!payload.at("data").is_object() || !payload.at("data").contains("list") ||
        !payload.at("data").at("list").is_array())
        throw std::runtime_error("bitget_oi_history_shape_invalid");
    return normalize_open_interest(payload.at("data").at("list"), cutoff_ms, now_ms);
}

inline std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

inline json probe_symbol(const std::string& symbol, std::int64_t as_of_ms) {
    if (!valid_symbol(symbol)) throw std::invalid_argument("bitget_probe_symbol_invalid");
    json result{
        {"symbol", symbol}, {"provider_id", "bitget"}, {"category", "USDT-FUTURES"},
        {"as_of_ms", as_of_ms}, {"status", "UNAVAILABLE"}, {"eligible", false}
    };
    try {
        const auto instrument = fetch_instrument(symbol);
        result["instrument"] = instrument;
        result["instrument_valid"] = valid_crypto_usdt_perpetual(instrument, symbol);
        if (!result["instrument_valid"].get<bool>())
            throw std::runtime_error("instrument_not_online_crypto_usdt_perpetual");
        const auto base = text(instrument, "baseCoin");
        const auto launch_ms = timestamp(instrument.value("launchTime", json{}));
        const bool listing_time_verified = launch_ms > 0 && launch_ms <= as_of_ms;
        const auto start_ms = listing_time_verified
            ? std::max(as_of_ms - kTwoYearsMs, launch_ms)
            : as_of_ms - kTwoYearsMs;
        const auto ticker = fetch_ticker(symbol);
        result["ticker"] = {
            {"last_price", number(ticker.value("lastPrice", json{})).value_or(0.0)},
            {"turnover_24h_usdt", number(ticker.value("turnover24h", json{})).value_or(0.0)},
            {"funding_rate", number(ticker.value("fundingRate", json{})).value_or(0.0)},
            {"open_interest", number(ticker.value("openInterest", json{})).value_or(0.0)},
            {"timestamp_ms", timestamp(ticker.value("ts", json{}))}
        };

        const auto candles = fetch_ohlcv_two_years(symbol, base, start_ms, as_of_ms);
        const auto funding = fetch_funding_last_30d(symbol, as_of_ms - kThirtyDaysMs, as_of_ms);
        const auto oi = fetch_open_interest_last_30d(symbol, as_of_ms - kThirtyDaysMs, as_of_ms);
        const auto candle_coverage = coverage(candles, "timestamp_ms", kHourMs);
        const auto funding_coverage = coverage(funding, "timestamp_ms", 1LL);
        const auto oi_coverage = coverage(oi, "timestamp_ms", kHourMs);
        const auto listing_days = static_cast<double>(as_of_ms - start_ms) /
            static_cast<double>(kDayMs);
        const auto fund_interval = number(instrument.value("fundInterval", json{})).value_or(0.0);
        const double funding_interval_days = fund_interval > 0.0 ? fund_interval / 24.0 : 0.0;
        const bool candle_ok = candle_coverage.days + (1.0 / 24.0) >= listing_days &&
            candle_coverage.missing_intervals == 0U;
        const bool funding_ok = funding_coverage.days + funding_interval_days >= 30.0;
        const bool oi_ok = oi_coverage.days + (1.0 / 24.0) >= 30.0 &&
            oi_coverage.missing_intervals == 0U;
        const double turnover = result["ticker"].value("turnover_24h_usdt", 0.0);
        const bool liquidity_ok = std::isfinite(turnover) && turnover > 10'000'000.0;
        const bool eligible = candle_ok && funding_ok && oi_ok && liquidity_ok;

        result["coverage"] = {
            {"listing_history_days_required", listing_days},
            {"listing_time_ms", listing_time_verified ? json(launch_ms) : json(nullptr)},
            {"listing_time_status", listing_time_verified ? "VERIFIED" : "UNAVAILABLE_REQUIRES_FULL_730D"},
            {"ohlcv_1h", {{"records", candle_coverage.count}, {"days", candle_coverage.days},
                          {"missing_intervals", candle_coverage.missing_intervals},
                          {"first_ms", candle_coverage.first_ms}, {"last_ms", candle_coverage.last_ms},
                          {"required", "TWO_YEARS_OR_FULL_LISTING_HISTORY"}, {"status", candle_ok ? "AVAILABLE" : "PARTIAL"}}},
            {"funding", {{"records", funding_coverage.count}, {"days", funding_coverage.days},
                         {"funding_interval_hours", fund_interval}, {"required_days", 30},
                         {"first_ms", funding_coverage.first_ms}, {"last_ms", funding_coverage.last_ms},
                         {"status", funding_ok ? "AVAILABLE" : "PARTIAL"}}},
            {"open_interest_1h", {{"records", oi_coverage.count}, {"days", oi_coverage.days},
                                  {"missing_intervals", oi_coverage.missing_intervals}, {"required_days", 30},
                                  {"first_ms", oi_coverage.first_ms}, {"last_ms", oi_coverage.last_ms},
                                  {"status", oi_ok ? "AVAILABLE" : "PARTIAL"}}}
        };
        result["volume_semantics"] = {
            {"ohlcv_volume_unit", "BASE_COIN"},
            {"oi_unit", "BASE_COIN"},
            {"oi_value_unit", "USDT"},
            {"cross_venue_unit_conversion", "NOT_APPLIED"}
        };
        result["liquidity_gate"] = {
            {"threshold_usdt", 10'000'000.0}, {"observed_turnover_24h_usdt", turnover},
            {"status", liquidity_ok ? "PASS" : "FAIL"}
        };
        result["eligible"] = eligible;
        result["status"] = eligible ? "PASS" : "DEGRADED";
        result["note"] = "Research-only public-data probe; no account endpoint, trading key or order endpoint is used.";
    } catch (const std::exception& error) {
        result["status"] = "UNAVAILABLE";
        result["error"] = error.what();
    }
    return result;
}

inline json probe(const std::vector<std::string>& symbols) {
    const auto as_of = now_ms();
    json output{
        {"schema_version", "1.0.0"}, {"artifact_type", "cfss_bitget_provider_probe_v1"},
        {"provider_id", "bitget"}, {"api_version", "V3"},
        {"as_of_ms", as_of}, {"status", "PASS"}, {"symbols", json::array()}
    };
    for (const auto& symbol : symbols) {
        const auto report = probe_symbol(symbol, as_of);
        output["symbols"].push_back(report);
        if (!report.value("eligible", false)) output["status"] = "DEGRADED";
    }
    output["eligible_symbols"] = std::count_if(
        output["symbols"].begin(), output["symbols"].end(),
        [](const json& item) { return item.value("eligible", false); });
    output["requested_symbols"] = symbols.size();
    output["production_adapter_status"] = "NOT_IMPLEMENTED";
    output["production_fallback_status"] = "UNAVAILABLE_UNTIL_EQUIVALENCE_VALIDATION_AND_OWNER_REVIEW";
    return output;
}
} // namespace cfss::bitget
