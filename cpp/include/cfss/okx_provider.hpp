#pragma once
#include "cfss/hash.hpp"
#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <limits>
#include <iostream>
#include <cstdlib>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <utility>

namespace cfss::okx {
using json = nlohmann::json;

inline std::atomic<std::uint64_t>& http_request_attempts() { static std::atomic<std::uint64_t> value{0}; return value; }
inline std::atomic<std::uint64_t>& http_failed_attempts() { static std::atomic<std::uint64_t> value{0}; return value; }
inline std::atomic<std::uint64_t>& http_retry_attempts() { static std::atomic<std::uint64_t> value{0}; return value; }
inline std::atomic<std::uint64_t>& exhausted_requests() { static std::atomic<std::uint64_t> value{0}; return value; }
inline json request_metrics() {
    return {{"http_request_attempts", http_request_attempts().load()},
            {"http_failed_attempts", http_failed_attempts().load()},
            {"http_retry_attempts", http_retry_attempts().load()},
            {"exhausted_requests", exhausted_requests().load()}};
}

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
    http_request_attempts().fetch_add(1U);
    out.transport = curl_easy_perform(curl);
    if (out.transport == CURLE_OK) curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &out.status);
    if (out.transport != CURLE_OK || out.status < 200 || out.status >= 400)
        http_failed_attempts().fetch_add(1U);
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
        if (attempt > 0) http_retry_attempts().fetch_add(1U);
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
    exhausted_requests().fetch_add(1U);
    throw std::runtime_error(last_error);
}

inline std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

inline std::string uppercase_symbol(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
        [](unsigned char ch) { return static_cast<char>(std::toupper(ch)); });
    return value;
}

inline bool valid_crypto_symbol(const std::string& symbol) {
    return !symbol.empty() && symbol.size() <= 20U &&
        std::all_of(symbol.begin(), symbol.end(), [](unsigned char ch) {
            return (ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9');
        });
}

inline bool is_known_non_crypto_underlying(const std::string& raw_symbol) {
    static const std::set<std::string> blocked{
        "SOXL", "SNDK", "NVDA", "ANTHROPIC", "XAU", "XAG", "GOLD", "SILVER",
        "TSLA", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "GOOG", "NFLX",
        "MSTR", "COIN", "SPY", "QQQ", "USO", "UNG", "TLT", "GDX", "SMH",
        "NVDL", "NVDX", "TSLL", "TSLT", "AAPU", "AMZU", "MSFU", "METU",
        "PLTR", "AMD", "INTC", "AVGO", "ORCL", "CRM", "CRWD", "SMCI", "ARM",
        "BABA", "PDD", "JD", "NIO", "XOM", "CVX", "BAC", "JPM", "GS", "WFC",
        "DIS", "UBER", "ABNB", "PYPL", "HOOD", "VIX", "DXY", "WTI", "BRENT"
    };
    return blocked.contains(uppercase_symbol(raw_symbol));
}

struct CryptoUniverse {
    std::set<std::string> symbols;
    json artifact;
};

inline CryptoUniverse load_crypto_universe(const std::optional<json>& cached = std::nullopt) {
    const auto retrieved_at = now_ms();
    try {
        const auto response = get("https://api.coinpaprika.com/v1/coins", 30L);
        if (response.transport != CURLE_OK || response.status != 200)
            throw std::runtime_error("coinpaprika_http_or_transport_unavailable");
        const auto payload = json::parse(response.body);
        if (!payload.is_array()) throw std::runtime_error("coinpaprika_coin_list_shape_invalid");
        std::set<std::string> symbols;
        for (const auto& row : payload) {
            if (!row.is_object() || !row.value("is_active", false)) continue;
            const auto symbol = uppercase_symbol(row.value("symbol", std::string{}));
            const auto type = row.value("type", std::string{});
            if (valid_crypto_symbol(symbol) && (type == "coin" || type == "token"))
                symbols.insert(symbol);
        }
        if (symbols.size() < 500U || !symbols.contains("BTC"))
            throw std::runtime_error("coinpaprika_coin_list_coverage_insufficient");
        json symbol_array = json::array();
        std::string hash_material;
        for (const auto& symbol : symbols) {
            symbol_array.push_back(symbol);
            hash_material += symbol + "\n";
        }
        json artifact{
            {"schema_version", "1.0.0"}, {"artifact_type", "cfss_crypto_universe_v1"},
            {"status", "VERIFIED"}, {"provider_id", "coinpaprika"},
            {"source_endpoint", "https://api.coinpaprika.com/v1/coins"},
            {"attribution", "CoinPaprika"}, {"freshness_status", "LIVE"},
            {"fetched_at_ms", retrieved_at}, {"retrieved_at_ms", retrieved_at},
            {"symbol_count", symbols.size()}, {"symbols_sha256", cfss::sha256_hex(hash_material)},
            {"symbols", symbol_array}
        };
        return {std::move(symbols), std::move(artifact)};
    } catch (const std::exception&) {
        if (!cached || !cached->is_object() ||
            cached->value("artifact_type", std::string{}) != "cfss_crypto_universe_v1" ||
            cached->value("status", std::string{}) != "VERIFIED" ||
            cached->value("provider_id", std::string{}) != "coinpaprika" ||
            cached->value("source_endpoint", std::string{}) != "https://api.coinpaprika.com/v1/coins" ||
            cached->value("attribution", std::string{}) != "CoinPaprika" ||
            !cached->contains("symbols") || !cached->at("symbols").is_array())
            throw std::runtime_error("crypto_universe_live_reference_failed_and_no_valid_cache");
        const auto fetched_at = cached->value("fetched_at_ms", std::int64_t{0});
        if (fetched_at <= 0 || retrieved_at < fetched_at ||
            retrieved_at - fetched_at > 7LL * 86'400'000LL)
            throw std::runtime_error("crypto_universe_cache_stale");
        std::set<std::string> symbols;
        for (const auto& value : cached->at("symbols")) {
            if (!value.is_string())
                throw std::runtime_error("crypto_universe_cache_symbol_type_invalid");
            const auto symbol = uppercase_symbol(value.get<std::string>());
            if (!valid_crypto_symbol(symbol))
                throw std::runtime_error("crypto_universe_cache_symbol_format_invalid");
            symbols.insert(symbol);
        }
        if (symbols.size() < 500U || !symbols.contains("BTC") ||
            cached->value("symbol_count", std::size_t{0}) != symbols.size())
            throw std::runtime_error("crypto_universe_cache_coverage_insufficient");
        std::string hash_material;
        for (const auto& symbol : symbols) hash_material += symbol + "\n";
        if (cached->value("symbols_sha256", std::string{}) != cfss::sha256_hex(hash_material))
            throw std::runtime_error("crypto_universe_cache_hash_mismatch");
        auto artifact = *cached;
        artifact["freshness_status"] = "CACHED";
        artifact["retrieved_at_ms"] = retrieved_at;
        return {std::move(symbols), std::move(artifact)};
    }
}

inline bool is_verified_crypto_underlying(const std::string& raw_symbol,
                                          const std::set<std::string>& crypto_symbols) {
    const auto symbol = uppercase_symbol(raw_symbol);
    return !symbol.empty() && crypto_symbols.contains(symbol) &&
           !is_known_non_crypto_underlying(symbol);
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
    double contract_multiplier{0.0};
    double tick_size{0.0};
    double lot_size{0.0};
    double min_size{0.0};
    double turnover{0.0};
    std::int64_t listing_time_ms{0};
    std::string contract_value_currency;
};

inline std::optional<double> quote_turnover_usd(const json& ticker) {
    const auto last = number(ticker.value("last", json{}));
    const auto base_volume = number(ticker.value("volCcy24h", json{}));
    if (!last || !base_volume || *last <= 0.0 || *base_volume <= 0.0) return std::nullopt;
    return *last * *base_volume;
}
inline bool passes_liquidity(double quote_turnover_usd, double threshold_usd = 10000000.0) {
    return std::isfinite(quote_turnover_usd) && quote_turnover_usd > threshold_usd;
}
inline bool valid_linear_usdt_contract(const json& item, const std::string& base) {
    const auto ct_type = text(item, "ctType");
    const auto positive = [&](const char* key) {
        const auto value = number(item.value(key, json{}));
        return value && *value > 0.0;
    };
    return text(item, "state") == "live" && text(item, "settleCcy") == "USDT" &&
           (ct_type.empty() || ct_type == "linear") && text(item, "ctValCcy") == base &&
           positive("ctVal") && positive("ctMult") && positive("tickSz") &&
           positive("lotSz") && positive("minSz") && timestamp(item.value("listTime", json{})) > 0;
}
inline std::vector<Instrument> select_instruments(
    int target_count, std::vector<Instrument> eligible,
    const std::vector<Instrument>& all_valid_crypto,
    const std::set<std::string>& required_symbols = {}) {
    if (target_count < 1 || target_count > 100)
        throw std::invalid_argument("target_count_invalid");
    std::sort(eligible.begin(), eligible.end(), [](const Instrument& a, const Instrument& b) {
        const bool a_btc = a.base == "BTC";
        const bool b_btc = b.base == "BTC";
        if (a_btc != b_btc) return a_btc;
        return a.turnover > b.turnover;
    });
    const auto btc = std::find_if(eligible.begin(), eligible.end(),
        [](const Instrument& item) { return item.base == "BTC"; });
    if (btc == eligible.end())
        throw std::runtime_error("btc_contract_does_not_pass_liquidity_or_metadata_gates");
    const auto requested_total = static_cast<std::size_t>(target_count) + 1U;
    const auto selection_limit = std::min(requested_total, eligible.size());
    std::vector<Instrument> selected{*btc};
    for (const auto& item : eligible) {
        if (selected.size() >= selection_limit) break;
        if (item.id != btc->id) selected.push_back(item);
    }
    for (const auto& required_base : required_symbols) {
        const auto found = std::find_if(all_valid_crypto.begin(), all_valid_crypto.end(),
            [&](const Instrument& item) { return item.base == required_base; });
        if (found == all_valid_crypto.end()) continue;
        const bool already_selected = std::any_of(selected.begin(), selected.end(),
            [&](const Instrument& item) { return item.id == found->id; });
        if (!already_selected) selected.push_back(*found);
    }
    if (selected.size() < selection_limit)
        throw std::runtime_error("instrument_universe_selection_inconsistent");
    return selected;
}

inline std::vector<Instrument> discover(int target_count, const std::set<std::string>& crypto_symbols,
                                       const std::set<std::string>& required_symbols = {},
                                       std::size_t* eligible_count = nullptr,
                                       std::size_t* declared_count = nullptr,
                                       std::size_t* excluded_non_crypto_count = nullptr) {
    const auto instruments = request("/api/v5/public/instruments?instType=SWAP");
    const auto tickers = request("/api/v5/market/tickers?instType=SWAP");
    std::map<std::string, double> turnover;
    for (const auto& ticker : tickers["data"]) {
        // OKX documents volCcy24h for derivatives in base currency; convert to quote notional.
        const auto notional = quote_turnover_usd(ticker);
        if (notional) turnover[text(ticker, "instId")] = *notional;
    }

    std::vector<Instrument> eligible;
    std::vector<Instrument> all_valid_crypto;
    std::size_t swap_rows = 0U, live_rows = 0U, usdt_settle_rows = 0U, linear_rows = 0U;
    std::size_t excluded_non_crypto = 0U;
    for (const auto& item : instruments["data"]) {
        const auto id = text(item, "instId");
        if (id.size() < 10U || id.substr(id.size() - 10U) != "-USDT-SWAP") continue;
        ++swap_rows;
        if (text(item, "state") != "live") continue;
        ++live_rows;
        if (text(item, "settleCcy") != "USDT") continue;
        ++usdt_settle_rows;

        const auto first_dash = id.find('-');
        const auto second_dash = first_dash == std::string::npos ? std::string::npos : id.find('-', first_dash + 1U);
        const std::string parsed_base = first_dash == std::string::npos ? std::string{} : id.substr(0U, first_dash);
        const std::string base = text(item, "baseCcy").empty() ? parsed_base : text(item, "baseCcy");
        const std::string quote = text(item, "quoteCcy").empty() ? "USDT" : text(item, "quoteCcy");
        if (!is_verified_crypto_underlying(base, crypto_symbols)) {
            ++excluded_non_crypto;
            continue;
        }
        const auto vol = turnover.find(id);
        const double quote_turnover = vol == turnover.end() ? 0.0 : vol->second;
        if (!valid_linear_usdt_contract(item, base)) continue;
        ++linear_rows;
        const auto ct = number(item.value("ctVal", json{}));
        const auto mult = number(item.value("ctMult", json{}));
        const auto tick = number(item.value("tickSz", json{}));
        const auto lot = number(item.value("lotSz", json{}));
        const auto minimum = number(item.value("minSz", json{}));
        const auto listing = timestamp(item.value("listTime", json{}));
        const auto value_ccy = text(item, "ctValCcy");
        const Instrument parsed{id, base, quote, "USDT", *ct, *mult,
                                *tick, *lot, *minimum, quote_turnover, listing, value_ccy};
        all_valid_crypto.push_back(parsed);
        if (passes_liquidity(quote_turnover)) eligible.push_back(parsed);
        (void)second_dash;
    }
    if (eligible_count) *eligible_count = eligible.size();
    if (declared_count) *declared_count = usdt_settle_rows;
    if (excluded_non_crypto_count) *excluded_non_crypto_count = excluded_non_crypto;
    std::cerr << "OKX_UNIVERSE_DIAGNOSTICS total=" << instruments["data"].size()
              << " usdt_swap_suffix=" << swap_rows << " live=" << live_rows
              << " settle_usdt=" << usdt_settle_rows << " linear_or_unspecified=" << linear_rows
              << " excluded_non_crypto=" << excluded_non_crypto
              << " eligible=" << eligible.size() << " ticker_turnover=" << turnover.size() << '\n';
    // BTC is a mandatory reference; pinned pending symbols are added after the top-turnover universe.
    return select_instruments(target_count, std::move(eligible), all_valid_crypto, required_symbols);
}

inline json fetch_candles(const Instrument& instrument, std::int64_t start_ms,
                          std::int64_t end_ms) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 250; ++page) {
        std::string path = "/api/v5/market/history-candles?instId=" + encode(instrument.id) +
                           "&bar=1H&limit=300";
        if (after) path += "&after=" + std::to_string(*after);
        const auto payload = request(path);
        const auto page_retrieved_at = utc_iso(now_ms());
        if (payload["data"].empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload["data"]) {
            if (!row.is_array() || row.size() < 9U) continue;
            const auto ts = timestamp(row[0]);
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            const auto open = number(row[1]), high = number(row[2]), low = number(row[3]);
            const auto close = number(row[4]);
            const auto volume_contracts = number(row[5]);
            const auto volume_base = number(row[6]);
            const auto volume_quote = number(row[7]);
            const bool confirmed = text(json{{"v", row[8]}}, "v") == "1";
            if (ts < start_ms || ts >= end_ms || ts % 3'600'000LL != 0 || !confirmed || ts + 3'600'000LL > end_ms ||
                !open || !high || !low || !close || !volume_contracts || !volume_base || !volume_quote ||
                *open <= 0.0 || *high <= 0.0 || *low <= 0.0 || *close <= 0.0 ||
                *volume_contracts < 0.0 || *volume_base < 0.0 || *volume_quote < 0.0 ||
                *high < std::max({*open, *low, *close}) || *low > std::min({*open, *high, *close}))
                continue;
            rows[ts] = {{"timestamp_ms", ts}, {"open", *open}, {"high", *high},
                        {"low", *low}, {"close", *close}, {"price_currency", instrument.quote},
                        {"volume", *volume_contracts}, {"volume_unit", "contracts"}, {"volume_base", *volume_base},
                        {"volume_base_currency", instrument.base}, {"volume_quote", *volume_quote},
                        {"volume_quote_currency", instrument.quote},
                        {"closed", true}, {"retrieved_at_utc", page_retrieved_at}};
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

inline json fetch_recent_candles(const Instrument& instrument, const std::string& bar,
                                    std::int64_t interval_ms, std::int64_t end_ms,
                                    int limit = 100) {
    if ((bar != "1H" && bar != "15m" && bar != "5m") || interval_ms <= 0 || limit < 1 || limit > 300)
        throw std::invalid_argument("recent_candle_request_invalid");
    const auto payload = request("/api/v5/market/candles?instId=" + encode(instrument.id) +
                                  "&bar=" + encode(bar) + "&limit=" + std::to_string(limit));
    const auto retrieved_at = utc_iso(now_ms());
    std::map<std::int64_t, json> rows;
    for (const auto& row : payload["data"]) {
        if (!row.is_array() || row.size() < 9U) continue;
        const auto ts = timestamp(row[0]);
        const auto open = number(row[1]), high = number(row[2]), low = number(row[3]);
        const auto close = number(row[4]);
        const auto volume_contracts = number(row[5]);
        const auto volume_base = number(row[6]);
        const auto volume_quote = number(row[7]);
        const bool confirmed = text(json{{"v", row[8]}}, "v") == "1";
        if (ts <= 0 || ts % interval_ms != 0 || ts + interval_ms > end_ms || !confirmed ||
            !open || !high || !low || !close || !volume_contracts || !volume_base || !volume_quote ||
            *open <= 0.0 || *high <= 0.0 || *low <= 0.0 || *close <= 0.0 ||
            *volume_contracts < 0.0 || *volume_base < 0.0 || *volume_quote < 0.0 ||
            *high < std::max({*open, *low, *close}) ||
            *low > std::min({*open, *high, *close})) continue;
        rows[ts] = {
            {"timestamp_ms", ts}, {"open", *open}, {"high", *high},
            {"low", *low}, {"close", *close}, {"price_currency", instrument.quote},
            {"volume", *volume_contracts}, {"volume_unit", "contracts"},
            {"volume_base", *volume_base}, {"volume_base_currency", instrument.base},
            {"volume_quote", *volume_quote}, {"volume_quote_currency", instrument.quote},
            {"closed", true}, {"retrieved_at_utc", retrieved_at}
        };
    }
    json out = json::array();
    for (const auto& [ts, row] : rows) { (void)ts; out.push_back(row); }
    return out;
}

inline json fetch_funding(const Instrument& instrument, std::int64_t start_ms, std::int64_t end_ms) {
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < 20; ++page) {
        std::string path = "/api/v5/public/funding-rate-history?instId=" + encode(instrument.id) + "&limit=100";
        if (after) path += "&after=" + std::to_string(*after);
        const auto payload = request(path);
        const auto page_retrieved_at = utc_iso(now_ms());
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
                        {"funding_rate_unit", "fraction"},
                        {"mark_price", mark ? json(*mark) : json(nullptr)},
                        {"mark_price_currency", instrument.quote},
                        {"retrieved_at_utc", page_retrieved_at}};
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

inline json fetch_open_interest(const Instrument& instrument, std::int64_t start_ms, std::int64_t end_ms,
                                int max_pages = 12) {
    if (max_pages < 1 || max_pages > 12) throw std::invalid_argument("open_interest_max_pages_invalid");
    std::map<std::int64_t, json> rows;
    std::optional<std::int64_t> after;
    std::int64_t previous_oldest = end_ms + 1;
    for (int page = 0; page < max_pages; ++page) {
        std::string path = "/api/v5/rubik/stat/contracts/open-interest-history?instId=" +
                           encode(instrument.id) + "&period=1H&limit=100";
        if (after) path += "&end=" + std::to_string(*after);
        const auto payload = request(path);
        const auto page_retrieved_at = utc_iso(now_ms());
        if (payload["data"].empty()) break;
        std::int64_t oldest = std::numeric_limits<std::int64_t>::max();
        for (const auto& row : payload["data"]) {
            std::int64_t ts = 0;
            std::optional<double> amount, base_amount, usd_value;
            if (row.is_object()) {
                ts = timestamp(row.value("ts", row.value("timestamp", json{})));
                amount = number(row.value("oi", row.value("openInterestAmount", row.value("openInterest", json{}))));
                base_amount = number(row.value("oiCcy", row.value("openInterestBase", json{})));
                usd_value = number(row.value("oiUsd", row.value("openInterestValue", json{})));
            } else if (row.is_array() && row.size() >= 2U) {
                ts = timestamp(row[0]); amount = number(row[1]);
                if (row.size() >= 3U) base_amount = number(row[2]);
                if (row.size() >= 4U) usd_value = number(row[3]);
            }
            if (ts <= 0) continue;
            oldest = std::min(oldest, ts);
            if (ts < start_ms || ts >= end_ms) continue;
            rows[ts] = {{"timestamp_ms", ts},
                        {"open_interest", amount ? json(*amount) : json(nullptr)},
                        {"open_interest_unit", "contracts"},
                        {"open_interest_base", base_amount ? json(*base_amount) : json(nullptr)},
                        {"open_interest_base_currency", instrument.base},
                        {"open_interest_value_usd", usd_value ? json(*usd_value) : json(nullptr)},
                        {"open_interest_value_currency", "USD"},
                        {"retrieved_at_utc", page_retrieved_at}};
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
inline std::string open_interest_availability(const json& rows, double minimum_days = 29.0) {
    const auto base = availability(rows, "open_interest", minimum_days);
    if (base != "AVAILABLE") return base;
    for (const auto& row : rows) {
        if (!row.contains("open_interest_base") || row["open_interest_base"].is_null() ||
            !row.contains("open_interest_value_usd") || row["open_interest_value_usd"].is_null())
            return "PARTIAL";
    }
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
            {"fallback_status", std::string{probe.id} == "okx" ? "PRIMARY" :
                (std::string{probe.adapter} == "REFERENCE_ONLY" ? "REFERENCE_ONLY" : "UNAVAILABLE")},
            {"fallback_reason", std::string{probe.id} == "okx" ? "primary_provider" :
                (std::string{probe.adapter} == "REFERENCE_ONLY" ? "not_a_futures_fallback" :
                 (!reachable ? "provider_endpoint_unreachable" : "no_equivalence_verified_cpp_adapter"))},
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

inline json merge_timestamp_rows(const json& historical, const json& recent,
                                  std::int64_t start_ms, std::int64_t end_ms,
                                  std::int64_t interval_ms) {
    std::map<std::int64_t, json> merged;
    const auto add = [&](const json& rows) {
        if (!rows.is_array()) return;
        for (const auto& row : rows) {
            if (!row.is_object()) continue;
            const auto ts = row.value("timestamp_ms", std::int64_t{0});
            if (ts > 0 && ts >= start_ms && ts < end_ms && ts % interval_ms == 0)
                merged[ts] = row;
        }
    };
    add(historical);
    add(recent);
    json result = json::array();
    for (const auto& [ts, row] : merged) { (void)ts; result.push_back(row); }
    return result;
}

inline json collect(int symbol_count, int years,
                       const std::optional<json>& cached_crypto_universe = std::nullopt,
                       const std::optional<json>& cached_market_data = std::nullopt,
                       const std::set<std::string>& required_symbols = {}) {
    if (symbol_count < 1 || symbol_count > 100 || years < 1 || years > 2)
        throw std::invalid_argument("symbols_must_be_1_to_100_and_years_1_to_2");
    const auto acquired_ms = now_ms();
    const auto end_ms = (acquired_ms / 3'600'000LL) * 3'600'000LL;
    const auto start_ms = end_ms - static_cast<std::int64_t>(years * 365.25 * 24.0 * 3'600'000.0);
    const auto acquired_text = utc_iso(acquired_ms);
    const auto crypto_universe = load_crypto_universe(cached_crypto_universe);
    std::size_t eligible_count = 0U, declared_count = 0U, excluded_non_crypto_count = 0U;
    const auto selected = discover(symbol_count, crypto_universe.symbols, required_symbols,
                                    &eligible_count, &declared_count, &excluded_non_crypto_count);
    json instruments = json::array();
    for (const auto& item : selected) {
        json candles = json::array(), funding = json::array(), oi = json::array();
        json errors = json::array();
        const json* cached_instrument = nullptr;
        if (cached_market_data && cached_market_data->is_object() &&
            cached_market_data->contains("instruments") &&
            cached_market_data->at("instruments").is_array()) {
            for (const auto& cached_item : cached_market_data->at("instruments")) {
                if (cached_item.value("instrument_id", std::string{}) == item.id) {
                    cached_instrument = &cached_item;
                    break;
                }
            }
        }
        bool has_valid_candle_cache = cached_instrument &&
            cached_instrument->contains("candles") && cached_instrument->at("candles").is_array() &&
            !cached_instrument->at("candles").empty();
        if (has_valid_candle_cache) {
            const auto& cached_candles = cached_instrument->at("candles");
            const auto first_cached_ms = cached_candles.front().value("timestamp_ms", std::int64_t{0});
            const auto last_cached_ms = cached_candles.back().value("timestamp_ms", std::int64_t{0});
            const auto effective_start_ms = item.listing_time_ms > start_ms
                ? item.listing_time_ms : start_ms;
            const auto expected_rows = std::max<std::int64_t>(
                1, (end_ms - effective_start_ms) / 3'600'000LL);
            const double cached_coverage = 100.0 * static_cast<double>(cached_candles.size()) /
                                           static_cast<double>(expected_rows);
            has_valid_candle_cache = first_cached_ms > 0 &&
                first_cached_ms <= effective_start_ms + 3LL * 3'600'000LL &&
                last_cached_ms > 0 && end_ms >= last_cached_ms + 3'600'000LL &&
                end_ms - (last_cached_ms + 3'600'000LL) <= 10LL * 86'400'000LL &&
                cached_coverage >= 98.0;
        }
        bool oi_cache_complete = false;
        if (cached_instrument && cached_instrument->contains("open_interest") &&
            cached_instrument->at("open_interest").is_array() &&
            !cached_instrument->at("open_interest").empty()) {
            const auto& cached_oi = cached_instrument->at("open_interest");
            const auto first_oi_ms = cached_oi.front().value("timestamp_ms", std::int64_t{0});
            const auto last_oi_ms = cached_oi.back().value("timestamp_ms", std::int64_t{0});
            oi_cache_complete = first_oi_ms > 0 && last_oi_ms > first_oi_ms &&
                last_oi_ms - first_oi_ms >= 25LL * 86'400'000LL &&
                end_ms >= last_oi_ms && end_ms - last_oi_ms <= 3LL * 86'400'000LL;
        }
        try {
            if (has_valid_candle_cache) {
                const auto recent = fetch_recent_candles(item, "1H", 3'600'000LL, end_ms, 300);
                candles = merge_timestamp_rows(cached_instrument->at("candles"), recent,
                                                start_ms, end_ms, 3'600'000LL);
            } else {
                candles = fetch_candles(item, start_ms, end_ms);
            }
        } catch (const std::exception& e) {
            errors.push_back(std::string{"ohlcv:"} + e.what());
            if (has_valid_candle_cache) candles = cached_instrument->at("candles");
        }
        try {
            const auto fresh = fetch_funding(item, end_ms - 30LL * 86'400'000LL, end_ms);
            const auto old = cached_instrument && cached_instrument->contains("funding")
                ? cached_instrument->at("funding") : json::array();
            funding = merge_timestamp_rows(old, fresh, end_ms - 30LL * 86'400'000LL,
                                            end_ms, 1LL);
        } catch (const std::exception& e) {
            errors.push_back(std::string{"funding:"} + e.what());
            if (cached_instrument && cached_instrument->contains("funding") &&
                cached_instrument->at("funding").is_array())
                funding = cached_instrument->at("funding");
        }
        try {
            const auto fresh = fetch_open_interest(item, end_ms - 30LL * 86'400'000LL, end_ms,
                                                   oi_cache_complete ? 1 : 12);
            const auto old = cached_instrument && cached_instrument->contains("open_interest")
                ? cached_instrument->at("open_interest") : json::array();
            oi = merge_timestamp_rows(old, fresh, end_ms - 30LL * 86'400'000LL,
                                       end_ms, 1LL);
        } catch (const std::exception& e) {
            errors.push_back(std::string{"open_interest:"} + e.what());
            if (cached_instrument && cached_instrument->contains("open_interest") &&
                cached_instrument->at("open_interest").is_array())
                oi = cached_instrument->at("open_interest");
        }
        const auto expected = std::max<std::int64_t>(1, (end_ms - start_ms) / 3'600'000LL);
        const double coverage = 100.0 * static_cast<double>(candles.size()) / static_cast<double>(expected);
        const auto has_error_prefix = [&](const std::string& prefix) {
            return std::any_of(errors.begin(), errors.end(), [&](const json& error) {
                return error.is_string() && error.get<std::string>().rfind(prefix, 0U) == 0U;
            });
        };
        instruments.push_back({
            {"instrument_id", item.id}, {"unified_symbol", item.base + "/USDT:USDT"},
            {"base", item.base}, {"quote", item.quote}, {"settle", item.settle},
            {"contract_type", "linear_perpetual"},
            {"contract_size", item.contract_size}, {"contract_multiplier", item.contract_multiplier},
            {"contract_value_currency", item.contract_value_currency}, {"tick_size", item.tick_size},
            {"lot_size", item.lot_size}, {"min_size", item.min_size},
            {"listing_time_ms", item.listing_time_ms}, {"turnover_24h_usd", item.turnover},
            {"liquidity_threshold_usd", 10000000.0},
            {"liquidity_status", passes_liquidity(item.turnover) ? "ELIGIBLE" : "BELOW_THRESHOLD_PINNED"},
            {"provider_id", "okx"}, {"timeframe", "1h"}, {"candles", candles},
            {"provenance", {{"instrument_endpoint", "/api/v5/public/instruments?instType=SWAP"},
                            {"ticker_endpoint", "/api/v5/market/tickers?instType=SWAP"},
                            {"ohlcv_endpoint", "/api/v5/market/history-candles"},
                            {"funding_endpoint", "/api/v5/public/funding-rate-history"},
                            {"open_interest_endpoint", "/api/v5/rubik/stat/contracts/open-interest-history"},
                            {"retrieved_at_utc", utc_iso(now_ms())}}},
            {"funding", funding}, {"open_interest", oi},
            {"availability", {
                {"ohlcv", coverage >= 100.0 ? "AVAILABLE" : (candles.empty() ? "UNAVAILABLE" : "PARTIAL")},
                {"funding", has_error_prefix("funding:") ? "PARTIAL" : availability(funding, "funding_rate", 29.0)},
                {"open_interest", has_error_prefix("open_interest:") ? "PARTIAL" : open_interest_availability(oi, 29.0)}
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
    const auto provider_health = probe_provider_health();
    const auto fear_greed = fetch_fear_greed();
    json selected_ids = json::array();
    std::string scan_material = "1h|" + std::to_string(start_ms) + "|" + std::to_string(end_ms) + "|";
    for (const auto& item : selected) { selected_ids.push_back(item.id); scan_material += item.id + ";"; }
    const std::string scan_id = "scan-" + cfss::sha256_hex(scan_material);
    return {
        {"schema_version", "1.0.0"},
        {"run_id", "okx-cpp-" + std::to_string(acquired_ms)},
        {"scan_id", scan_id},
        {"producer", {{"name", "cfss-cpp-l1-collector"}, {"version", "1.0.0"},
                      {"source_commit", commit ? json(commit) : json(nullptr)}}},
        {"acquired_at_utc", acquired_text},
        {"window", {{"timeframe", "1h"}, {"start_ms", start_ms}, {"end_ms", end_ms}}},
        {"provider", {{"primary_provider_id", "okx"}, {"display_name", "OKX public market-data API"},
                      {"fallback_used", false}}},
        {"provider_health", provider_health}, {"fear_greed", fear_greed},
        {"crypto_universe", crypto_universe.artifact},
        {"universe", {{"declared_usdt_swap_count", declared_count},
                      {"crypto_universe_status", "VERIFIED"},
                      {"crypto_universe_source", "coinpaprika"},
                      {"crypto_universe_symbol_count", crypto_universe.symbols.size()},
                      {"crypto_universe_symbols_sha256", crypto_universe.artifact.at("symbols_sha256")},
                      {"excluded_non_crypto_count", excluded_non_crypto_count},
                      {"eligible_count", eligible_count},
                      {"selected_count", selected.size()}, {"target_count", symbol_count},
                      {"liquidity_threshold_usd", 10000000.0},
                      {"selection_method", "top_turnover_usd_desc_with_btc_first"},
                      {"selection_timestamp_utc", acquired_text},
                      {"selected_instrument_ids", selected_ids}}},
        {"instruments", instruments}
    };
}
} // namespace cfss::okx
