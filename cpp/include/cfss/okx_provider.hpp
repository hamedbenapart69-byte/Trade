#pragma once
#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <limits>
#include <iostream>
#include <cstdlib>
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace cfss::okx {
using json = nlohmann::json;

inline std::size_t write_body(char* data, std::size_t size, std::size_t count, void* ctx) {
    if (!ctx || (size != 0U && count > static_cast<std::size_t>(-1) / size)) return 0U;
    const auto bytes = size * count;
    static_cast<std::string*>(ctx)->append(data, bytes);
    return bytes;
}

struct HttpResponse { long status{0}; CURLcode transport{CURLE_FAILED_INIT}; std::string body; };

inline HttpResponse get(const std::string& url, long timeout_seconds = 25L) {
    HttpResponse out;
    CURL* curl = curl_easy_init();
    if (!curl) throw std::runtime_error("curl_init_failed");
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_body);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &out.body);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_seconds);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "CFSS-CXX20/1.0");
    out.transport = curl_easy_perform(curl);
    if (out.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &out.status);
    curl_easy_cleanup(curl);
    return out;
}

inline std::string encode(const std::string& value) {
    CURL* curl = curl_easy_init();
    if (!curl) throw std::runtime_error("curl_url_encoder_init_failed");
    char* raw = curl_easy_escape(curl, value.c_str(), static_cast<int>(value.size()));
    if (!raw) { curl_easy_cleanup(curl); throw std::runtime_error("curl_url_encode_failed"); }
    std::string result{raw};
    curl_free(raw);
    curl_easy_cleanup(curl);
    return result;
}

inline json request(const std::string& path, int attempts = 3) {
    const std::string url = "https://www.okx.com" + path;
    std::string last_error = "provider_request_failed";
    for (int attempt = 0; attempt < attempts; ++attempt) {
        const auto response = get(url);
        if (response.transport == CURLE_OK && response.status == 200) {
            try {
                auto parsed = json::parse(response.body);
                if (parsed.value("code", std::string{}) == "0" && parsed.contains("data") && parsed["data"].is_array())
                    return parsed;
                last_error = "okx_api_error:" + parsed.value("code", std::string{"missing_code"}) + ":" +
                             parsed.value("msg", std::string{});
            } catch (const std::exception& e) { last_error = std::string{"json_parse_failed:"} + e.what(); }
        } else {
            last_error = "http_or_transport_error:" + std::to_string(response.status) + ":" +
                         curl_easy_strerror(response.transport);
        }
        if (attempt + 1 < attempts) std::this_thread::sleep_for(std::chrono::milliseconds(500 * (attempt + 1)));
    }
    throw std::runtime_error(last_error);
}

inline std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
inline std::string utc_iso(std::int64_t epoch_ms) {
    const auto seconds = static_cast<std::time_t>(epoch_ms / 1000);
    std::tm tm{};
#if defined(_WIN32)
    gmtime_s(&tm, &seconds);
#else
    gmtime_r(&seconds, &tm);
#endif
    char buffer[32]{};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return buffer;
}
inline std::optional<double> number(const json& value) {
    if (value.is_number()) {
        const double n = value.get<double>();
        if (std::isfinite(n)) return n;
    }
    if (value.is_string()) {
        try {
            const double n = std::stod(value.get<std::string>());
            if (std::isfinite(n)) return n;
        } catch (...) {}
    }
    return std::nullopt;
}
inline std::int64_t timestamp(const json& value) {
    if (value.is_number_integer()) return value.get<std::int64_t>();
    if (value.is_string()) {
        try { return std::stoll(value.get<std::string>()); } catch (...) {}
    }
    return 0;
}
inline std::string text(const json& obj, const char* key) {
    if (!obj.contains(key) || obj[key].is_null()) return {};
    if (obj[key].is_string()) return obj[key].get<std::string>();
    return obj[key].dump();
}

struct Instrument {
    std::string id, base, quote, settle;
    double contract_size{0.0};
    double turnover{0.0};
};

inline std::vector<Instrument> discover(int target_count) {
    const auto instruments = request("/api/v5/public/instruments?instType=SWAP");
    const auto tickers = request("/api/v5/market/tickers?instType=SWAP");
    std::map<std::string, double> turnover;
    for (const auto& ticker : tickers["data"]) {
        const auto last = number(ticker.value("last", json{}));
        auto volume = number(ticker.value("volCcy24h", json{}));
        if (!volume) volume = number(ticker.value("vol24h", json{}));
        if (last && volume && *last > 0.0 && *volume > 0.0)
            turnover[text(ticker, "instId")] = *last * *volume;
    }

    std::vector<Instrument> eligible;
    std::size_t swap_rows = 0U, live_rows = 0U, usdt_settle_rows = 0U, linear_rows = 0U;
    json btc_diagnostic = nullptr;
    for (const auto& item : instruments["data"]) {
        const auto id = text(item, "instId");
        if (id.size() < 10U || id.substr(id.size() - 10U) != "-USDT-SWAP") continue;
        ++swap_rows;
        if (text(item, "state") != "live") continue;
        ++live_rows;
        if (text(item, "settleCcy") != "USDT") continue;
        ++usdt_settle_rows;
        const auto ct_type = text(item, "ctType");
        if (!ct_type.empty() && ct_type != "linear") continue;
        ++linear_rows;

        const auto first_dash = id.find('-');
        const auto second_dash = first_dash == std::string::npos ? std::string::npos : id.find('-', first_dash + 1U);
        const std::string parsed_base = first_dash == std::string::npos ? std::string{} : id.substr(0U, first_dash);
        const std::string base = text(item, "baseCcy").empty() ? parsed_base : text(item, "baseCcy");
        const std::string quote = text(item, "quoteCcy").empty() ? "USDT" : text(item, "quoteCcy");
        if (base == "BTC") btc_diagnostic = item;
        const auto vol = turnover.find(id);
        const double quote_turnover = vol == turnover.end() ? 0.0 : vol->second;
        const auto ct = number(item.value("ctVal", json{}));
        eligible.push_back({id, base, quote, "USDT", ct.value_or(0.0), quote_turnover});
        (void)second_dash;
    }
    std::cerr << "OKX_UNIVERSE_DIAGNOSTICS total=" << instruments["data"].size()
              << " usdt_swap_suffix=" << swap_rows << " live=" << live_rows
              << " settle_usdt=" << usdt_settle_rows << " linear_or_unspecified=" << linear_rows
              << " eligible=" << eligible.size() << " ticker_turnover=" << turnover.size() << '\n';
    if (btc_diagnostic.is_null()) {
        for (const auto& item : instruments["data"]) {
            if (text(item, "instId") == "BTC-USDT-SWAP") {
                std::cerr << "OKX_BTC_INSTRUMENT_DIAGNOSTIC=" << item.dump() << '\n';
                break;
            }
        }
        throw std::runtime_error("btc_usdt_linear_perpetual_not_found");
    }
    std::sort(eligible.begin(), eligible.end(), [](const Instrument& a, const Instrument& b) {
        if (a.base == "BTC") return true;
        if (b.base == "BTC") return false;
        return a.turnover > b.turnover;
    });
    const auto btc = std::find_if(eligible.begin(), eligible.end(), [](const Instrument& x) {
        return x.base == "BTC";
    });
    std::vector<Instrument> selected;
    selected.push_back(*btc);
    for (const auto& item : eligible) {
        if (selected.size() >= static_cast<std::size_t>(target_count)) break;
        if (item.id != btc->id) selected.push_back(item);
    }
    if (selected.size() != static_cast<std::size_t>(target_count))
        throw std::runtime_error("eligible_instrument_universe_below_requested_count");
    return selected;
}

inline json fetch_candles(const Instrument& instrument, std::int64_t start_ms,
                          std::int64_t end_ms, const std::string& retrieved_at) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 250; ++page) {
        std::string path = "/api/v5/market/history-candles?instId=" + encode(instrument.id) +
                           "&bar=1H&limit=300";
        if (after) path += "&end=" + std::to_string(*after);
        const auto payload = request(path);
        if (payload["data"].empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload["data"]) {
            if (!row.is_array() || row.size() < 9U) continue;
            const auto ts = timestamp(row[0]);
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            const auto open = number(row[1]), high = number(row[2]), low = number(row[3]);
            const auto close = number(row[4]), volume = number(row[5]);
            const bool confirmed = text(json{{"v", row[8]}}, "v") == "1";
            if (ts < start_ms || ts >= end_ms || !confirmed || ts + 3'600'000LL > end_ms ||
                !open || !high || !low || !close || !volume ||
                *open <= 0.0 || *high <= 0.0 || *low <= 0.0 || *close <= 0.0 || *volume < 0.0 ||
                *high < std::max({*open, *low, *close}) || *low > std::min({*open, *high, *close}))
                continue;
            rows[ts] = {{"timestamp_ms", ts}, {"open", *open}, {"high", *high},
                        {"low", *low}, {"close", *close}, {"volume", *volume},
                        {"closed", true}, {"retrieved_at_utc", retrieved_at}};
        }
        if (oldest == std::numeric_limits<std::int64_t>::max() || oldest >= previous_oldest || oldest <= start_ms)
            break;
        previous_oldest = oldest;
        after = oldest;
        std::this_thread::sleep_for(std::chrono::milliseconds(110));
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) { (void)ts; out.push_back(row); }
    return out;
}

inline json fetch_funding(const Instrument& instrument, std::int64_t start_ms, std::int64_t end_ms, const std::string& retrieved_at) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 20; ++page) {
        std::string path = "/api/v5/public/funding-rate-history?instId=" + encode(instrument.id) + "&limit=100";
        if (after) path += "&after=" + std::to_string(*after);
        const auto payload = request(path);
        if (payload["data"].empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload["data"]) {
            const auto ts = timestamp(row.value("fundingTime", json{}));
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            if (ts < start_ms || ts >= end_ms) continue;
            const auto rate = number(row.value("fundingRate", json{}));
            const auto mark = number(row.value("markPx", json{}));
            rows[ts] = {{"timestamp_ms", ts},
                        {"funding_rate", rate ? json(*rate) : json(nullptr)},
                        {"mark_price", mark ? json(*mark) : json(nullptr)},
                        {"retrieved_at_utc", retrieved_at}};
        }
        if (oldest == std::numeric_limits<std::int64_t>::max() || oldest >= previous_oldest || oldest <= start_ms)
            break;
        previous_oldest = oldest;
        after = oldest;
        std::this_thread::sleep_for(std::chrono::milliseconds(120));
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) { (void)ts; out.push_back(row); }
    return out;
}

inline json fetch_open_interest(const Instrument& instrument, std::int64_t start_ms, std::int64_t end_ms, const std::string& retrieved_at) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 12; ++page) {
        std::string path = "/api/v5/rubik/stat/contracts/open-interest-history?instId=" +
                           encode(instrument.id) + "&period=1H&limit=100";
        if (after) path += "&after=" + std::to_string(*after);
        const auto payload = request(path);
        if (payload["data"].empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload["data"]) {
            std::int64_t ts = 0;
            std::optional<double> amount, value;
            if (row.is_object()) {
                ts = timestamp(row.value("ts", row.value("timestamp", json{})));
                amount = number(row.value("oi", row.value("openInterestAmount", row.value("openInterest", json{}))));
                value = number(row.value("oiUsd", row.value("openInterestValue", json{})));
            } else if (row.is_array() && row.size() >= 2U) {
                ts = timestamp(row[0]); amount = number(row[1]);
                if (row.size() >= 3U) value = number(row[2]);
            }
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            if (ts < start_ms || ts >= end_ms) continue;
            rows[ts] = {{"timestamp_ms", ts},
                        {"open_interest", amount ? json(*amount) : json(nullptr)},
                        {"open_interest_value_usd", value ? json(*value) : json(nullptr)},
                        {"retrieved_at_utc", retrieved_at}};
        }
        if (oldest == std::numeric_limits<std::int64_t>::max() || oldest >= previous_oldest || oldest <= start_ms)
            break;
        previous_oldest = oldest;
        after = oldest;
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) { (void)ts; out.push_back(row); }
    return out;
}

inline double coverage_days(const json& rows) {
    if (!rows.is_array() || rows.size() < 2U) return 0.0;
    const auto first = timestamp(rows.front().value("timestamp_ms", json{}));
    const auto last = timestamp(rows.back().value("timestamp_ms", json{}));
    if (first <= 0 || last <= first) return 0.0;
    return static_cast<double>(last - first) / 86'400'000.0;
}
inline std::string availability(const json& rows, const char* field, double minimum_days = 0.0) {
    if (!rows.is_array() || rows.empty()) return "UNAVAILABLE";
    for (const auto& row : rows) if (!row.contains(field) || row[field].is_null()) return "PARTIAL";
    if (coverage_days(rows) < minimum_days) return "PARTIAL";
    return "AVAILABLE";
}

inline json probe_provider_health() {
    const auto checked_at = utc_iso(now_ms());
    struct Probe { const char* id; const char* url; int rank; const char* adapter; };
    const std::vector<Probe> probes{
        {"okx", "https://www.okx.com/api/v5/public/time", 1, "IMPLEMENTED_PRIMARY"},
        {"bybit", "https://api.bybit.com/v5/market/time", 2, "NOT_IMPLEMENTED"},
        {"binance", "https://fapi.binance.com/fapi/v1/ping", 3, "NOT_IMPLEMENTED"},
        {"kucoin", "https://api-futures.kucoin.com/api/v1/timestamp", 4, "NOT_IMPLEMENTED"},
        {"mexc", "https://contract.mexc.com/api/v1/contract/detail", 5, "NOT_IMPLEMENTED"},
        {"bitget", "https://api.bitget.com/api/v2/mix/market/ticker?productType=USDT-FUTURES&symbol=BTCUSDT", 6, "NOT_IMPLEMENTED"},
        {"coingecko", "https://api.coingecko.com/api/v3/ping", 7, "REFERENCE_ONLY"}
    };
    json providers = json::array();
    for (const auto& probe : probes) {
        const auto response = get(probe.url, 12L);
        const bool reachable = response.transport == CURLE_OK && response.status == 200;
        providers.push_back({
            {"provider_id", probe.id}, {"fallback_rank", probe.rank}, {"endpoint", probe.url},
            {"checked_at_utc", checked_at},
            {"connectivity_status", reachable ? "HTTP_REACHABLE" : "UNAVAILABLE"},
            {"http_status", response.status},
            {"transport_status", curl_easy_strerror(response.transport)},
            {"adapter_status", probe.adapter},
            {"fallback_status", std::string{probe.id} == "okx" ? "PRIMARY" : "UNAVAILABLE"},
            {"fallback_equivalence", "NOT_PROVEN"}
        });
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
    }
    return {{"schema_version", "1.0.0"}, {"checked_at_utc", checked_at}, {"providers", providers}};
}

inline json fetch_fear_greed() {
    const auto retrieved_at = utc_iso(now_ms());
    const auto response = get("https://api.alternative.me/fng/?limit=0&format=json", 20L);
    if (response.transport != CURLE_OK || response.status != 200)
        return {{"schema_version", "1.0.0"}, {"status", "UNAVAILABLE"},
                {"retrieved_at_utc", retrieved_at}, {"observations", json::array()},
                {"error", "fear_greed_http_or_transport_unavailable"}};
    try {
        const auto payload = json::parse(response.body);
        if (!payload.contains("data") || !payload["data"].is_array())
            throw std::runtime_error("fear_greed_payload_shape_invalid");
        const auto cutoff = now_ms() - 730LL * 86'400'000LL;
        std::map<std::int64_t, json> ordered;
        for (const auto& row : payload["data"]) {
            const auto raw_ts = text(row, "timestamp");
            const auto raw_value = text(row, "value");
            std::int64_t ts = 0;
            int value = -1;
            try { ts = std::stoll(raw_ts) * 1000LL; value = std::stoi(raw_value); }
            catch (...) { continue; }
            if (ts < cutoff || value < 0 || value > 100) continue;
            ordered[ts] = {{"timestamp_ms", ts}, {"value", value},
                           {"classification", text(row, "value_classification")},
                           {"retrieved_at_utc", retrieved_at}};
        }
        json observations = json::array();
        for (const auto& [ts, item] : ordered) { (void)ts; observations.push_back(item); }
        return {{"schema_version", "1.0.0"},
                {"status", observations.empty() ? "UNAVAILABLE" : "AVAILABLE"},
                {"source_id", "alternative_me_fear_greed"},
                {"source_endpoint", "https://api.alternative.me/fng/?limit=0&format=json"},
                {"retrieved_at_utc", retrieved_at}, {"observations", observations}};
    } catch (const std::exception& e) {
        return {{"schema_version", "1.0.0"}, {"status", "UNAVAILABLE"},
                {"retrieved_at_utc", retrieved_at}, {"observations", json::array()},
                {"error", e.what()}};
    }
}

inline json collect(int symbol_count, int years) {
    if (symbol_count < 1 || symbol_count > 100 || years < 1 || years > 2)
        throw std::invalid_argument("symbols_must_be_1_to_100_and_years_1_to_2");
    const auto acquired_ms = now_ms();
    const auto end_ms = (acquired_ms / 3'600'000LL) * 3'600'000LL;
    const auto start_ms = end_ms - static_cast<std::int64_t>(years * 365.25 * 24.0 * 3'600'000.0);
    const auto acquired_text = utc_iso(acquired_ms);
    const auto selected = discover(symbol_count);
    json instruments = json::array();
    for (const auto& item : selected) {
        json candles = json::array(), funding = json::array(), oi = json::array();
        json errors = json::array();
        try { candles = fetch_candles(item, start_ms, end_ms, acquired_text); }
        catch (const std::exception& e) { errors.push_back(std::string{"ohlcv:"} + e.what()); }
        try { funding = fetch_funding(item, end_ms - 30LL * 86'400'000LL, end_ms, acquired_text); }
        catch (const std::exception& e) { errors.push_back(std::string{"funding:"} + e.what()); }
        try { oi = fetch_open_interest(item, end_ms - 30LL * 86'400'000LL, end_ms, acquired_text); }
        catch (const std::exception& e) { errors.push_back(std::string{"open_interest:"} + e.what()); }
        const auto expected = std::max<std::int64_t>(1, (end_ms - start_ms) / 3'600'000LL);
        const double coverage = 100.0 * static_cast<double>(candles.size()) / static_cast<double>(expected);
        instruments.push_back({
            {"instrument_id", item.id}, {"unified_symbol", item.base + "/USDT:USDT"},
            {"base", item.base}, {"quote", item.quote}, {"settle", item.settle},
            {"contract_type", "linear_perpetual"},
            {"contract_size", item.contract_size > 0.0 ? json(item.contract_size) : json(nullptr)},
            {"provider_id", "okx"}, {"timeframe", "1h"}, {"candles", candles},
            {"provenance", {{"ohlcv_endpoint", "/api/v5/market/history-candles"},
                            {"funding_endpoint", "/api/v5/public/funding-rate-history"},
                            {"open_interest_endpoint", "/api/v5/rubik/stat/contracts/open-interest-history"},
                            {"retrieved_at_utc", acquired_text}}},
            {"funding", funding}, {"open_interest", oi},
            {"availability", {
                {"ohlcv", coverage >= 100.0 ? "AVAILABLE" : (candles.empty() ? "UNAVAILABLE" : "PARTIAL")},
                {"funding", availability(funding, "funding_rate", 29.0)},
                {"open_interest", availability(oi, "open_interest", 29.0)}
            }},
            {"coverage", {
                {"ohlcv_rows", candles.size()}, {"funding_rows", funding.size()},
                {"open_interest_rows", oi.size()}, {"ohlcv_coverage_pct", std::min(100.0, coverage)},
                {"funding_coverage_days", coverage_days(funding)},
                {"open_interest_coverage_days", coverage_days(oi)}
            }},
            {"errors", errors}
        });
        std::this_thread::sleep_for(std::chrono::milliseconds(120));
    }
    const char* commit = std::getenv("GITHUB_SHA");
    return {
        {"schema_version", "1.0.0"},
        {"run_id", "okx-cpp-" + std::to_string(acquired_ms)},
        {"producer", {{"name", "cfss-cpp-l1-collector"}, {"version", "1.0.0"},
                      {"source_commit", commit ? json(commit) : json(nullptr)}}},
        {"acquired_at_utc", acquired_text},
        {"window", {{"timeframe", "1h"}, {"start_ms", start_ms}, {"end_ms", end_ms}}},
        {"provider", {{"primary_provider_id", "okx"}, {"display_name", "OKX public market-data API"},
                      {"fallback_used", false}}},
        {"instruments", instruments}
    };
}
} // namespace cfss::okx
