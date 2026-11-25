#pragma once

#include <algorithm>
#include <chrono>
#include <ctime>
#include <limits>
#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include <curl/curl.h>
#include <nlohmann/json.hpp>

namespace cfss::kucoin {

using json = nlohmann::json;
constexpr std::int64_t kHourMs = 3'600'000LL;
constexpr std::int64_t kDayMs = 86'400'000LL;

struct HttpResponse {
    CURLcode transport{CURLE_FAILED_INIT};
    long status{0};
    std::string body;
};

inline std::size_t write_body(char* data, std::size_t size, std::size_t count, void* user_data) {
    const auto bytes = size * count;
    static_cast<std::string*>(user_data)->append(data, bytes);
    return bytes;
}

inline HttpResponse get(const std::string& url, long timeout_seconds = 25L) {
    HttpResponse response;
    CURL* handle = curl_easy_init();
    if (!handle) return response;
    curl_easy_setopt(handle, CURLOPT_URL, url.c_str());
    curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, write_body);
    curl_easy_setopt(handle, CURLOPT_WRITEDATA, &response.body);
    curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(handle, CURLOPT_TIMEOUT, timeout_seconds);
    curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(handle, CURLOPT_ACCEPT_ENCODING, "");
    curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-V21-public-market-data/1.0");
    response.transport = curl_easy_perform(handle);
    curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &response.status);
    curl_easy_cleanup(handle);
    return response;
}

inline std::string string_value(const json& value) {
    if (value.is_string()) return value.get<std::string>();
    if (value.is_number()) return value.dump();
    return {};
}

inline double number_value(const json& value) {
    try {
        if (value.is_number()) return value.get<double>();
        if (value.is_string()) return std::stod(value.get<std::string>());
    } catch (...) {}
    return std::numeric_limits<double>::quiet_NaN();
}

inline std::int64_t integer_value(const json& value) {
    try {
        if (value.is_number_integer()) return value.get<std::int64_t>();
        if (value.is_number()) return static_cast<std::int64_t>(value.get<double>());
        if (value.is_string()) return std::stoll(value.get<std::string>());
    } catch (...) {}
    return 0;
}

inline std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

inline std::string utc_iso(std::int64_t timestamp_ms) {
    const std::time_t seconds = static_cast<std::time_t>(timestamp_ms / 1000LL);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &seconds);
#else
    gmtime_r(&seconds, &tm);
#endif
    char buffer[32]{};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%S", &tm);
    return std::string(buffer) + "Z";
}

inline json request_data(const std::string& url, long timeout_seconds = 25L) {
    std::string last_error = "kucoin_request_failed";
    for (int attempt = 0; attempt < 3; ++attempt) {
        try {
            const auto response = get(url, timeout_seconds);
            if (response.transport != CURLE_OK || response.status != 200) {
                last_error = "kucoin_http_or_transport_error status=" +
                    std::to_string(response.status) + " transport=" +
                    curl_easy_strerror(response.transport);
                if (attempt < 2)
                    std::this_thread::sleep_for(std::chrono::milliseconds(250 * (attempt + 1)));
                continue;
            }
            const auto payload = json::parse(response.body);
            if (!payload.is_object() || string_value(payload.value("code", json{})) != "200000" ||
                !payload.contains("data")) {
                last_error = "kucoin_api_payload_invalid code=" +
                    string_value(payload.value("code", json{}));
                if (attempt < 2)
                    std::this_thread::sleep_for(std::chrono::milliseconds(250 * (attempt + 1)));
                continue;
            }
            return payload.at("data");
        } catch (const std::exception& e) {
            last_error = e.what();
            if (attempt < 2)
                std::this_thread::sleep_for(std::chrono::milliseconds(250 * (attempt + 1)));
        }
    }
    throw std::runtime_error(last_error);
}

struct Contract {
    std::string symbol;
    std::string base;
    std::string base_currency;
    std::string quote{"USDT"};
    std::string settle{"USDT"};
    double multiplier{0.0};
    double tick_size{0.0};
    double lot_size{0.0};
    double min_size{0.0};
    double turnover_24h_usd{0.0};
    std::int64_t listing_time_ms{0};
};

struct Bundle {
    Contract contract;
    json candles{json::array()};
    json funding{json::array()};
    json open_interest{json::array()};
    json errors{json::array()};
};

inline std::string canonical_base(const std::string& base_currency) {
    return base_currency == "XBT" ? "BTC" : base_currency;
}

inline std::optional<Contract> parse_contract(const json& row) {
    if (!row.is_object()) return std::nullopt;
    const auto symbol = string_value(row.value("symbol", json{}));
    const auto base_currency = string_value(row.value("baseCurrency", json{}));
    const auto quote = string_value(row.value("quoteCurrency", json{}));
    const auto settle = string_value(row.value("settleCurrency", json{}));
    const auto status = string_value(row.value("status", json{}));
    const bool inverse = row.value("isInverse", true);
    const bool expired = row.contains("expireDate") && !row.at("expireDate").is_null();
    const double multiplier = number_value(row.value("multiplier", json{}));
    const double tick_size = number_value(row.value("tickSize", json{}));
    const double lot_size = number_value(row.value("lotSize", json{}));
    const double turnover = number_value(row.value("turnoverOf24h", json{}));
    const auto listing_time = integer_value(row.value("firstOpenDate", json{}));
    if (symbol.empty() || base_currency.empty() || quote != "USDT" || settle != "USDT" ||
        status != "Open" || inverse || expired || !std::isfinite(multiplier) ||
        multiplier <= 0.0 || !std::isfinite(tick_size) || tick_size <= 0.0 ||
        !std::isfinite(lot_size) || lot_size <= 0.0 ||
        !std::isfinite(turnover) || turnover <= 0.0 || listing_time <= 0) {
        return std::nullopt;
    }
    Contract contract;
    contract.symbol = symbol;
    contract.base_currency = base_currency;
    contract.base = canonical_base(base_currency);
    contract.quote = quote;
    contract.settle = settle;
    contract.multiplier = multiplier;
    contract.tick_size = tick_size;
    contract.lot_size = lot_size;
    contract.min_size = lot_size;
    if (row.contains("minOrderQty")) {
        const auto minimum = number_value(row.at("minOrderQty"));
        if (std::isfinite(minimum) && minimum > 0.0) contract.min_size = minimum;
    }
    contract.turnover_24h_usd = turnover;
    contract.listing_time_ms = listing_time;
    return contract;
}

inline std::vector<Contract> parse_active_contracts(const json& data) {
    std::vector<Contract> contracts;
    if (data.is_array()) {
        for (const auto& row : data) {
            const auto contract = parse_contract(row);
            if (contract) contracts.push_back(*contract);
        }
    } else if (data.is_object()) {
        const auto contract = parse_contract(data);
        if (contract) contracts.push_back(*contract);
    } else {
        throw std::runtime_error("kucoin_active_contracts_shape_invalid");
    }
    return contracts;
}

inline std::vector<Contract> fetch_active_contracts() {
    const auto data = request_data("https://api-futures.kucoin.com/api/v1/contracts/active");
    return parse_active_contracts(data);
}

inline std::optional<Contract> find_contract(const std::vector<Contract>& contracts,
                                             const std::string& canonical_symbol) {
    const auto wanted = canonical_symbol == "BTC" ? "XBT" : canonical_symbol;
    const Contract* best = nullptr;
    for (const auto& contract : contracts) {
        if (contract.base_currency != wanted) continue;
        if (!best || contract.turnover_24h_usd > best->turnover_24h_usd) best = &contract;
    }
    if (!best) return std::nullopt;
    return *best;
}

inline std::optional<Contract> find_contract(const std::string& canonical_symbol) {
    const auto contracts = fetch_active_contracts();
    return find_contract(contracts, canonical_symbol);
}

inline json parse_candle_rows(const json& rows, const Contract& contract,
                              std::int64_t start_ms, std::int64_t end_ms,
                              const std::string& retrieved_at) {
    if (!rows.is_array()) throw std::runtime_error("kucoin_kline_rows_not_array");
    std::map<std::int64_t, json> ordered;
    for (const auto& row : rows) {
        if (!row.is_array() || row.size() < 7U) continue;
        const auto ts = integer_value(row[0]);
        const double open = number_value(row[1]);
        const double high = number_value(row[2]);
        const double low = number_value(row[3]);
        const double close = number_value(row[4]);
        const double volume_contracts = number_value(row[5]);
        const double turnover_quote = number_value(row[6]);
        if (ts < start_ms || ts >= end_ms || ts + kHourMs > end_ms ||
            !std::isfinite(open) || !std::isfinite(high) || !std::isfinite(low) ||
            !std::isfinite(close) || !std::isfinite(volume_contracts) ||
            !std::isfinite(turnover_quote) || open <= 0.0 || high <= 0.0 ||
            low <= 0.0 || close <= 0.0 || volume_contracts < 0.0 || turnover_quote < 0.0) {
            continue;
        }
        ordered[ts] = {
            {"timestamp_ms", ts}, {"open", open}, {"high", high}, {"low", low},
            {"close", close}, {"volume", volume_contracts}, {"closed", true},
            {"retrieved_at_utc", retrieved_at}, {"volume_unit", "contracts"},
            {"volume_base", volume_contracts * contract.multiplier},
            {"volume_base_currency", contract.base}, {"volume_quote", turnover_quote},
            {"volume_quote_currency", "USDT"}, {"price_currency", "USDT"}
        };
    }
    json result = json::array();
    for (const auto& [ts, candle] : ordered) {
        (void)ts;
        result.push_back(candle);
    }
    return result;
}

inline json fetch_candles(const Contract& contract, std::int64_t start_ms,
                          std::int64_t end_ms) {
    if (start_ms <= 0 || end_ms <= start_ms) throw std::invalid_argument("kucoin_candle_window_invalid");
    constexpr std::int64_t page_span_ms = 500LL * kHourMs;
    const auto retrieved_at = utc_iso(now_ms());
    std::map<std::int64_t, json> merged;
    for (std::int64_t cursor = start_ms; cursor < end_ms; cursor += page_span_ms) {
        const auto page_end = std::min(end_ms, cursor + page_span_ms);
        const auto url = "https://api-futures.kucoin.com/api/v1/kline/query?symbol=" +
            contract.symbol + "&granularity=60&from=" + std::to_string(cursor) +
            "&to=" + std::to_string(page_end);
        const auto rows = request_data(url);
        const auto parsed = parse_candle_rows(rows, contract, cursor, page_end, retrieved_at);
        for (const auto& row : parsed) merged[row.at("timestamp_ms").get<std::int64_t>()] = row;
        if (cursor + page_span_ms < end_ms)
            std::this_thread::sleep_for(std::chrono::milliseconds(150));
    }
    json result = json::array();
    for (const auto& [ts, row] : merged) {
        (void)ts;
        result.push_back(row);
    }
    return result;
}

inline json parse_funding_rows(const json& rows, std::int64_t start_ms,
                               std::int64_t end_ms, const std::string& retrieved_at) {
    if (!rows.is_array()) throw std::runtime_error("kucoin_funding_rows_not_array");
    std::map<std::int64_t, json> ordered;
    for (const auto& row : rows) {
        if (!row.is_object()) continue;
        const auto ts = integer_value(row.value("timepoint", json{}));
        const double rate = number_value(row.value("fundingRate", json{}));
        if (ts < start_ms || ts >= end_ms || !std::isfinite(rate)) continue;
        ordered[ts] = {
            {"timestamp_ms", ts}, {"funding_rate", rate}, {"mark_price", nullptr},
            {"retrieved_at_utc", retrieved_at}, {"funding_rate_unit", "fraction"},
            {"mark_price_currency", "USDT"}
        };
    }
    json result = json::array();
    for (const auto& [ts, row] : ordered) {
        (void)ts;
        result.push_back(row);
    }
    return result;
}

inline json fetch_funding(const Contract& contract, std::int64_t start_ms,
                          std::int64_t end_ms) {
    const auto url = "https://api-futures.kucoin.com/api/v1/contract/funding-rates?symbol=" +
        contract.symbol + "&from=" + std::to_string(start_ms) + "&to=" + std::to_string(end_ms);
    const auto rows = request_data(url);
    return parse_funding_rows(rows, start_ms, end_ms, utc_iso(now_ms()));
}

inline json parse_open_interest_rows(const json& rows, const Contract& contract,
                                     std::int64_t start_ms, std::int64_t end_ms,
                                     const std::string& retrieved_at) {
    if (!rows.is_array()) throw std::runtime_error("kucoin_open_interest_rows_not_array");
    std::map<std::int64_t, json> ordered;
    for (const auto& row : rows) {
        if (!row.is_object()) continue;
        const auto ts = integer_value(row.value("ts", json{}));
        const double contracts = number_value(row.value("openInterest", json{}));
        if (ts < start_ms || ts >= end_ms || !std::isfinite(contracts) || contracts <= 0.0) continue;
        ordered[ts] = {
            {"timestamp_ms", ts}, {"open_interest", contracts},
            {"open_interest_value_usd", nullptr}, {"retrieved_at_utc", retrieved_at},
            {"open_interest_unit", "contracts"},
            {"open_interest_base", contracts * contract.multiplier},
            {"open_interest_base_currency", contract.base},
            {"open_interest_value_currency", "USD"}
        };
    }
    json result = json::array();
    for (const auto& [ts, row] : ordered) {
        (void)ts;
        result.push_back(row);
    }
    return result;
}

inline json fetch_open_interest(const Contract& contract, std::int64_t start_ms,
                                std::int64_t end_ms) {
    const auto url = "https://api.kucoin.com/api/ua/v2/market/open-interest?symbol=" +
        contract.symbol + "&interval=1hour&startAt=" + std::to_string(start_ms) +
        "&endAt=" + std::to_string(end_ms) + "&pageSize=500";
    const auto rows = request_data(url);
    return parse_open_interest_rows(rows, contract, start_ms, end_ms, utc_iso(now_ms()));
}

inline Bundle fetch_bundle(const Contract& contract, std::int64_t candle_start_ms,
                           std::int64_t end_ms, std::int64_t funding_start_ms,
                           std::int64_t oi_start_ms) {
    Bundle bundle;
    bundle.contract = contract;
    try {
        bundle.candles = fetch_candles(contract, candle_start_ms, end_ms);
        if (bundle.candles.empty()) bundle.errors.push_back("ohlcv:kucoin_returned_no_closed_candles");
    } catch (const std::exception& e) {
        bundle.errors.push_back(std::string{"ohlcv:"} + e.what());
    }
    try {
        bundle.funding = fetch_funding(contract, funding_start_ms, end_ms);
        if (bundle.funding.empty()) bundle.errors.push_back("funding:kucoin_returned_no_rows");
    } catch (const std::exception& e) {
        bundle.errors.push_back(std::string{"funding:"} + e.what());
    }
    try {
        bundle.open_interest = fetch_open_interest(contract, oi_start_ms, end_ms);
        if (bundle.open_interest.empty()) bundle.errors.push_back("open_interest:kucoin_returned_no_rows");
    } catch (const std::exception& e) {
        bundle.errors.push_back(std::string{"open_interest:"} + e.what());
    }
    return bundle;
}

inline Bundle fetch_bundle(const std::string& canonical_symbol,
                           std::int64_t candle_start_ms, std::int64_t end_ms,
                           std::int64_t funding_start_ms, std::int64_t oi_start_ms) {
    const auto contract = find_contract(canonical_symbol);
    if (!contract) throw std::runtime_error("kucoin_usdt_linear_perpetual_not_found base=" + canonical_symbol);
    return fetch_bundle(*contract, candle_start_ms, end_ms, funding_start_ms, oi_start_ms);
}

inline json live_probe(const std::string& canonical_symbol = "BTC") {
    const auto end_ms = (now_ms() / kHourMs) * kHourMs;
    const auto bundle = fetch_bundle(canonical_symbol, end_ms - 7LL * kDayMs, end_ms,
                                     end_ms - 30LL * kDayMs, end_ms - 7LL * kDayMs);
    const auto oi_days = bundle.open_interest.size() >= 2U
        ? static_cast<double>(bundle.open_interest.back().at("timestamp_ms").get<std::int64_t>() -
                              bundle.open_interest.front().at("timestamp_ms").get<std::int64_t>()) /
              static_cast<double>(kDayMs)
        : 0.0;
    const bool pass = !bundle.candles.empty() && !bundle.funding.empty() &&
                      !bundle.open_interest.empty();
    return {
        {"status", pass ? "PASS" : "FAIL"},
        {"symbol", bundle.contract.symbol},
        {"ohlcv_rows", bundle.candles.size()},
        {"funding_rows", bundle.funding.size()},
        {"open_interest_rows", bundle.open_interest.size()},
        {"open_interest_coverage_days", oi_days},
        {"open_interest_hourly_retention_days", 7},
        {"equivalence", "PARTIAL"},
        {"limitation", "KuCoin hourly open-interest history is limited to 7 days; the 30-day OI requirement remains PARTIAL."},
        {"errors", bundle.errors}
    };
}

} // namespace cfss::kucoin
