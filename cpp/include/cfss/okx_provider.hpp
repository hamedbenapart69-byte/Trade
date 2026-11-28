#pragma once
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/kucoin_provider.hpp"
#include "cfss/provider_resilience.hpp"
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
#include <filesystem>
#include <functional>
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

inline bool retryable_http_failure(CURLcode transport, long status) {
    return transport != CURLE_OK || status == 408L || status == 429L ||
        (status >= 500L && status <= 599L);
}

inline bool retryable_okx_error_code(const std::string& code) {
    return code == "50011" || code == "50013";
}

inline std::chrono::milliseconds retry_delay(const std::string& url, int attempt) {
    const auto exponent = std::min(attempt, 4);
    const auto base_ms = std::min(8000, 500 * (1 << exponent));
    const auto jitter_seed = std::hash<std::string>{}(url + ":" + std::to_string(attempt));
    const auto jitter_ms = static_cast<int>(jitter_seed % 251U);
    return std::chrono::milliseconds(base_ms + jitter_ms);
}

inline json request(const std::string& path, int attempts = 3) {
    auto& breaker = cfss::resilience::okx_circuit_breaker();
    if (!breaker.allow_request()) throw std::runtime_error("okx_circuit_open");
    const std::string url = "https://www.okx.com" + path;
    std::string last_error = "provider_request_failed";
    for (int attempt = 0; attempt < attempts; ++attempt) {
        if (attempt > 0) http_retry_attempts().fetch_add(1U);
        HttpResponse response;
        try {
            response = get(url);
        } catch (const std::exception& e) {
            last_error = std::string{"okx_transport_exception:"} + e.what();
            if (attempt + 1 < attempts) {
                std::this_thread::sleep_for(retry_delay(url, attempt));
                continue;
            }
            break;
        }
        bool retryable = false;
        if (response.transport == CURLE_OK && response.status == 200) {
            json parsed;
            try {
                parsed = json::parse(response.body);
            } catch (const std::exception& e) {
                last_error = std::string{"json_parse_failed:"} + e.what();
                break;
            }
            const auto code = parsed.value("code", std::string{"missing_code"});
            if (code == "0" && parsed.contains("data") && parsed["data"].is_array()) {
                breaker.record_success();
                return parsed;
            }
            last_error = "okx_api_error:" + code + ":" + parsed.value("msg", std::string{});
            retryable = retryable_okx_error_code(code);
        } else {
            last_error = "http_or_transport_error:" + std::to_string(response.status) + ":" +
                         curl_easy_strerror(response.transport);
            retryable = retryable_http_failure(response.transport, response.status);
        }
        if (!retryable || attempt + 1 >= attempts) break;
        std::this_thread::sleep_for(retry_delay(url, attempt));
    }
    breaker.record_failure();
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

inline CryptoUniverse load_crypto_universe(const std::set<std::string>& required_symbols) {
    const auto retrieved_at = now_ms();
    if (required_symbols.size() != 9U || !required_symbols.contains("BTC"))
        throw std::invalid_argument("owner_universe_manifest_must_contain_exactly_nine_assets_including_btc");

    json symbol_array = json::array();
    std::string hash_material;
    for (const auto& raw_symbol : required_symbols) {
        const auto symbol = uppercase_symbol(raw_symbol);
        if (!valid_crypto_symbol(symbol) || is_known_non_crypto_underlying(symbol))
            throw std::invalid_argument("owner_universe_manifest_symbol_invalid:" + symbol);
        symbol_array.push_back(symbol);
        hash_material += symbol + "\n";
    }

    json artifact{
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_crypto_universe_v1"},
        {"status", "OWNER_MANIFEST_VERIFIED"},
        {"provider_id", "owner_manifest"},
        {"source_endpoint", "config/universe.json"},
        {"attribution", "Owner-configured V21.1 production universe"},
        {"freshness_status", "OWNER_CONFIG"},
        {"fetched_at_ms", retrieved_at},
        {"retrieved_at_ms", retrieved_at},
        {"symbol_count", required_symbols.size()},
        {"symbols_sha256", cfss::sha256_hex(hash_material)},
        {"symbols", symbol_array}
    };
    return {required_symbols, std::move(artifact)};
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
    std::string provider_id{"okx"};
    std::string provider_symbol;
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
inline std::vector<Instrument> select_production_nine_assets(
    const std::vector<Instrument>& all_valid_crypto,
    const std::set<std::string>& required_symbols) {
    if (required_symbols.size() != 9U || !required_symbols.contains("BTC"))
        throw std::invalid_argument("production_universe_must_contain_exactly_nine_assets_including_btc");

    std::map<std::string, Instrument> by_base;
    for (const auto& item : all_valid_crypto) {
        if (!by_base.emplace(item.base, item).second)
            throw std::runtime_error("duplicate_provider_instrument_for_canonical_asset:" + item.base);
    }

    std::vector<Instrument> selected;
    selected.reserve(9U);
    const auto append = [&](const std::string& base) {
        const auto found = by_base.find(base);
        if (found == by_base.end())
            throw std::runtime_error("production_asset_instrument_unavailable:" + base);
        // Universe membership is fixed by the owner-approved manifest.
        // Liquidity is a downstream eligibility gate; it must not silently shrink C10 coverage.
        selected.push_back(found->second);
    };

    append("BTC");
    for (const auto& base : required_symbols) {
        if (base != "BTC") append(base);
    }
    if (selected.size() != 9U)
        throw std::runtime_error("production_universe_selection_not_exactly_nine");
    return selected;
}

inline std::vector<Instrument> select_instruments(
    int target_count, std::vector<Instrument> eligible,
    const std::vector<Instrument>& all_valid_crypto,
    const std::set<std::string>& required_symbols = {}) {
    if (target_count < 1 || target_count > 100)
        throw std::invalid_argument("target_count_invalid");
    if (required_symbols.size() == 9U)
        return select_production_nine_assets(all_valid_crypto, required_symbols);
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

inline std::vector<Instrument> discover_okx(int target_count, const std::set<std::string>& crypto_symbols,
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
                                *tick, *lot, *minimum, quote_turnover, listing, value_ccy,
                                "okx", id};
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


inline std::vector<Instrument> discover_kucoin(
    int target_count, const std::set<std::string>& crypto_symbols,
    const std::set<std::string>& required_symbols = {},
    std::size_t* eligible_count = nullptr,
    std::size_t* declared_count = nullptr,
    std::size_t* excluded_non_crypto_count = nullptr) {
    const auto& contracts = cfss::kucoin::active_contracts_cached();
    std::vector<Instrument> eligible;
    std::vector<Instrument> all_valid_crypto;
    std::size_t excluded_non_crypto = 0U;
    for (const auto& contract : contracts) {
        if (!is_verified_crypto_underlying(contract.base, crypto_symbols)) {
            ++excluded_non_crypto;
            continue;
        }
        Instrument parsed{
            contract.base + "-USDT-SWAP", contract.base, "USDT", "USDT",
            contract.multiplier, 1.0, contract.tick_size, contract.lot_size,
            contract.min_size, contract.turnover_24h_usd, contract.listing_time_ms,
            contract.base, "kucoin", contract.symbol
        };
        parsed.provider_id = "kucoin";
        parsed.provider_symbol = contract.symbol;
        all_valid_crypto.push_back(parsed);
        if (passes_liquidity(contract.turnover_24h_usd)) eligible.push_back(parsed);
    }
    if (eligible_count) *eligible_count = eligible.size();
    if (declared_count) *declared_count = contracts.size();
    if (excluded_non_crypto_count) *excluded_non_crypto_count = excluded_non_crypto;
    std::cerr << "KUCOIN_UNIVERSE_DIAGNOSTICS declared=" << contracts.size()
              << " excluded_non_crypto=" << excluded_non_crypto
              << " eligible=" << eligible.size() << '\n';
    return select_instruments(target_count, std::move(eligible), all_valid_crypto, required_symbols);
}

inline std::vector<Instrument> discover(
    int target_count, const std::set<std::string>& crypto_symbols,
    const std::set<std::string>& required_symbols = {},
    std::size_t* eligible_count = nullptr,
    std::size_t* declared_count = nullptr,
    std::size_t* excluded_non_crypto_count = nullptr) {
    try {
        auto selected = discover_okx(target_count, crypto_symbols, required_symbols,
                                     eligible_count, declared_count, excluded_non_crypto_count);
        if (!selected.empty()) return selected;
        std::cerr << "OKX_DISCOVERY_EMPTY; attempting KuCoin public fallback\n";
    } catch (const std::exception& e) {
        std::cerr << "OKX_DISCOVERY_FAILED; attempting KuCoin public fallback: " << e.what() << '\n';
    }
    return discover_kucoin(target_count, crypto_symbols, required_symbols,
                           eligible_count, declared_count, excluded_non_crypto_count);
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

// شمارش کندل‌ها باید از ابتدای کندل هم‌پوشان با زمان شروع واقعی قرارداد آغاز شود.
inline std::int64_t expected_ohlcv_first_timestamp(std::int64_t start_ms,
                                                    std::int64_t end_ms,
                                                    std::int64_t listing_time_ms,
                                                    std::int64_t interval_ms = 3'600'000LL) {
    if (start_ms <= 0 || end_ms <= start_ms || interval_ms <= 0) return 0;
    const auto effective_start_ms = listing_time_ms > start_ms ? listing_time_ms : start_ms;
    if (effective_start_ms >= end_ms) return 0;
    return effective_start_ms - (effective_start_ms % interval_ms);
}

inline std::int64_t expected_ohlcv_rows(std::int64_t start_ms, std::int64_t end_ms,
                                        std::int64_t listing_time_ms,
                                        std::int64_t interval_ms = 3'600'000LL) {
    const auto first_expected_ms = expected_ohlcv_first_timestamp(
        start_ms, end_ms, listing_time_ms, interval_ms);
    if (first_expected_ms <= 0) return 0;
    return (end_ms - first_expected_ms) / interval_ms;
}

// فقط timestampهای مورد انتظار در شبکهٔ کندلی شمرده می‌شوند؛ ردیف اضافه یا خارج از شبکه
// نمی‌تواند جای یک کندل گمشده را بگیرد.
inline std::size_t ohlcv_present_expected_rows(const json& rows,
                                                std::int64_t start_ms,
                                                std::int64_t end_ms,
                                                std::int64_t listing_time_ms,
                                                std::int64_t interval_ms = 3'600'000LL) {
    if (!rows.is_array() || interval_ms <= 0) return 0U;
    const auto first_expected_ms = expected_ohlcv_first_timestamp(
        start_ms, end_ms, listing_time_ms, interval_ms);
    const auto expected_rows = expected_ohlcv_rows(start_ms, end_ms, listing_time_ms, interval_ms);
    if (first_expected_ms <= 0 || expected_rows <= 0) return 0U;
    std::set<std::int64_t> present;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        if (ts < first_expected_ms || ts >= end_ms || ts % interval_ms != 0) continue;
        present.insert(ts);
    }
    return present.size();
}

inline bool ohlcv_series_complete(const json& rows, std::int64_t start_ms,
                                  std::int64_t end_ms, std::int64_t listing_time_ms,
                                  std::int64_t interval_ms = 3'600'000LL) {
    if (!rows.is_array() || interval_ms <= 0) return false;
    const auto first_expected_ms = expected_ohlcv_first_timestamp(
        start_ms, end_ms, listing_time_ms, interval_ms);
    const auto expected_rows = expected_ohlcv_rows(start_ms, end_ms, listing_time_ms, interval_ms);
    if (first_expected_ms <= 0 || expected_rows <= 0) return false;
    std::size_t in_window_rows = 0U;
    std::set<std::int64_t> present;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        if (ts < start_ms || ts >= end_ms) continue;
        if (ts < first_expected_ms || ts % interval_ms != 0) return false;
        ++in_window_rows;
        present.insert(ts);
    }
    return in_window_rows == static_cast<std::size_t>(expected_rows) &&
           present.size() == static_cast<std::size_t>(expected_rows);
}

inline double ohlcv_coverage_pct(const json& rows, std::int64_t start_ms,
                                 std::int64_t end_ms, std::int64_t listing_time_ms,
                                 std::int64_t interval_ms = 3'600'000LL) {
    const auto expected_rows = expected_ohlcv_rows(start_ms, end_ms, listing_time_ms, interval_ms);
    if (expected_rows <= 0) return 0.0;
    const auto present = ohlcv_present_expected_rows(rows, start_ms, end_ms,
                                                    listing_time_ms, interval_ms);
    return std::min(100.0, 100.0 * static_cast<double>(present) /
                           static_cast<double>(expected_rows));
}

struct SeriesFreshness {
    json latest_age_ms{nullptr};
    std::int64_t max_age_ms{0};
    std::string status{"UNAVAILABLE"};
};

inline std::int64_t median_series_interval_ms(const json& rows) {
    if (!rows.is_array() || rows.size() < 2U) return 0;
    std::vector<std::int64_t> gaps;
    for (std::size_t i = 1; i < rows.size(); ++i) {
        if (!rows[i - 1U].is_object() || !rows[i].is_object() ||
            !rows[i - 1U].contains("timestamp_ms") || !rows[i].contains("timestamp_ms") ||
            !rows[i - 1U].at("timestamp_ms").is_number_integer() ||
            !rows[i].at("timestamp_ms").is_number_integer()) continue;
        const auto previous = rows[i - 1U].at("timestamp_ms").get<std::int64_t>();
        const auto current = rows[i].at("timestamp_ms").get<std::int64_t>();
        if (current > previous) gaps.push_back(current - previous);
    }
    if (gaps.empty()) return 0;
    if (gaps.size() > 20U) gaps.erase(gaps.begin(), gaps.end() - 20);
    std::sort(gaps.begin(), gaps.end());
    return gaps[(gaps.size() - 1U) / 2U];
}

inline SeriesFreshness evaluate_series_freshness(const json& rows,
                                                  std::int64_t reference_ms,
                                                  std::int64_t interval_multiplier,
                                                  std::int64_t absolute_cap_ms) {
    SeriesFreshness result;
    if (!rows.is_array() || rows.empty() || reference_ms <= 0 ||
        interval_multiplier <= 0 || absolute_cap_ms <= 0) return result;
    const auto& latest = rows.back();
    if (!latest.is_object() || !latest.contains("timestamp_ms") ||
        !latest.at("timestamp_ms").is_number_integer()) return result;
    const auto latest_ms = latest.at("timestamp_ms").get<std::int64_t>();
    if (latest_ms <= 0) return result;
    if (reference_ms >= latest_ms) result.latest_age_ms = reference_ms - latest_ms;
    const auto median_interval_ms = median_series_interval_ms(rows);
    if (median_interval_ms <= 0) return result;
    result.max_age_ms = std::min(absolute_cap_ms, median_interval_ms * interval_multiplier);
    if (reference_ms < latest_ms) {
        result.status = "STALE";
        return result;
    }
    result.status = reference_ms - latest_ms <= result.max_age_ms ? "FRESH" : "STALE";
    return result;
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

inline std::size_t normalize_open_interest_rows(json& rows) {
    if (!rows.is_array()) return 0U;
    std::size_t invalid_observations = 0U;
    for (auto& row : rows) {
        if (!row.is_object()) continue;
        for (const char* field : {"open_interest", "open_interest_base", "open_interest_value_usd"}) {
            if (!row.contains(field) || row.at(field).is_null() || !row.at(field).is_number()) continue;
            const double value = row.at(field).get<double>();
            const bool must_be_positive = std::string{field} != "open_interest_base";
            if (!std::isfinite(value) || (must_be_positive ? value <= 0.0 : value < 0.0)) {
                row[field] = nullptr;
                ++invalid_observations;
            }
        }
    }
    return invalid_observations;
}

inline json probe_provider_health() {
    const auto checked_at = utc_iso(now_ms());
    struct Probe { const char* id; const char* url; int rank; const char* adapter; };
    const std::vector<Probe> probes{
        {"okx", "https://www.okx.com/api/v5/public/time", 1, "IMPLEMENTED_PRIMARY"},
        {"bybit", "https://api.bybit.com/v5/market/time", 2, "NOT_IMPLEMENTED"},
        {"binance", "https://fapi.binance.com/fapi/v1/ping", 3, "NOT_IMPLEMENTED"},
        {"kucoin", "https://api-futures.kucoin.com/api/v1/timestamp", 4, "IMPLEMENTED_SECONDARY_PARTIAL"},
        {"mexc", "https://contract.mexc.com/api/v1/contract/detail", 5, "NOT_IMPLEMENTED"},
        {"bitget", "https://api.bitget.com/api/v2/mix/market/ticker?productType=USDT-FUTURES&symbol=BTCUSDT", 6, "NOT_IMPLEMENTED"}
    };
    json providers = json::array();
    for (const auto& probe : probes) {
        const auto response = get(probe.url, 12L);
        const bool reachable = response.transport == CURLE_OK && response.status == 200;
        const std::string provider_id{probe.id};
        std::string fallback_status = provider_id == "okx" ? "PRIMARY" :
            (std::string{probe.adapter} == "REFERENCE_ONLY" ? "REFERENCE_ONLY" : "UNAVAILABLE");
        std::string fallback_equivalence = "NOT_PROVEN";
        std::string fallback_reason = provider_id == "okx" ? "primary_provider" :
            (std::string{probe.adapter} == "REFERENCE_ONLY" ? "not_a_futures_fallback" :
             (!reachable ? "provider_endpoint_unreachable" : "adapter_live_equivalence_not_proven"));
        json entry = {
            {"provider_id", probe.id}, {"fallback_rank", probe.rank}, {"endpoint", probe.url},
            {"checked_at_utc", checked_at},
            {"connectivity_status", reachable ? "HTTP_REACHABLE" : "UNAVAILABLE"},
            {"http_status", response.status},
            {"transport_status", curl_easy_strerror(response.transport)},
            {"adapter_status", probe.adapter},
            {"fallback_status", fallback_status},
            {"fallback_equivalence", fallback_equivalence},
            {"fallback_reason", fallback_reason}
        };
        if (provider_id == "kucoin" && reachable) {
            try {
                const auto live = cfss::kucoin::live_probe("BTC");
                entry["fallback_probe"] = live;
                if (live.value("status", std::string{"FAIL"}) == "PASS") {
                    entry["fallback_status"] = "AVAILABLE_PARTIAL";
                    entry["fallback_equivalence"] = "PARTIAL";
                    entry["fallback_reason"] =
                        "public_live_probe_passed;OHLCV_and_funding_real;hourly_OI_retention_7d_days;30d_OI_remains_PARTIAL";
                } else {
                    entry["fallback_reason"] = "kucoin_public_live_probe_failed";
                }
            } catch (const std::exception& e) {
                entry["fallback_reason"] = std::string{"kucoin_public_live_probe_error:"} + e.what();
            }
        }
        if (provider_id == "okx")
            entry["circuit_breaker_state"] = cfss::resilience::okx_circuit_breaker().state();
        else if (provider_id == "kucoin")
            entry["circuit_breaker_state"] = cfss::resilience::kucoin_circuit_breaker().state();
        else
            entry["circuit_breaker_state"] = "NOT_APPLICABLE";
        providers.push_back(std::move(entry));
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
    }
    return {{"schema_version", "1.1.0"}, {"checked_at_utc", checked_at}, {"providers", providers}};
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

inline json cache_key_material(const std::string& instrument_id,
                                std::int64_t window_start_ms) {
    return {
        {"provider_id", "okx"},
        {"venue", "OKX"},
        {"instrument_id", instrument_id},
        {"market_type", "LINEAR_PERPETUAL"},
        {"timeframes", {
            {"candles", "1H"},
            {"funding", "8H"},
            {"open_interest", "1H"}
        }},
        {"window_start_ms", window_start_ms},
        {"window_policy", "ROLLING_2Y_OHLCV_30D_DERIVATIVES"},
        {"normalization_schema_version", "1.0.0"}
    };
}

inline json make_cache_entry(const json& instrument, std::int64_t window_start_ms,
                             std::int64_t window_end_ms) {
    const auto id = instrument.value("instrument_id", std::string{});
    auto metadata = cache_key_material(id, window_start_ms);
    metadata["window_end_ms"] = window_end_ms;
    metadata["data_revision"] = sha256_hex(instrument.dump());
    metadata["cache_key"] = sha256_hex(cache_key_material(id, window_start_ms).dump());
    return metadata;
}

inline bool valid_cache_entry(const json& cache_entries, const json& instrument,
                              const std::string& instrument_id,
                              std::int64_t current_start_ms, std::int64_t current_end_ms) {
    if (!cache_entries.is_object() || !cache_entries.contains(instrument_id) ||
        !instrument.is_object()) return false;
    const auto& metadata = cache_entries.at(instrument_id);
    if (!metadata.is_object()) return false;
    const auto expected = cache_key_material(instrument_id,
        metadata.value("window_start_ms", std::int64_t{0}));
    for (const auto& [key, value] : expected.items()) {
        if (!metadata.contains(key) || metadata.at(key) != value) return false;
    }
    const auto window_start = metadata.value("window_start_ms", std::int64_t{0});
    const auto window_end = metadata.value("window_end_ms", std::int64_t{0});
    if (window_start <= 0 || window_start > current_start_ms ||
        window_end <= 0 || window_end > current_end_ms ||
        current_end_ms - window_end > 10LL * 86'400'000LL) return false;
    const auto expected_key = sha256_hex(expected.dump());
    if (metadata.value("cache_key", std::string{}) != expected_key) return false;
    return metadata.value("data_revision", std::string{}) == sha256_hex(instrument.dump());
}

inline json make_market_cache_snapshot(const std::optional<json>& old_cache,
                                       const json& refreshed_instruments,
                                       std::int64_t window_start_ms,
                                       std::int64_t window_end_ms) {
    std::map<std::string, json> by_instrument;
    json cache_entries = json::object();
    if (old_cache && old_cache->is_object() && old_cache->contains("instruments") &&
        old_cache->at("instruments").is_array()) {
        for (const auto& item : old_cache->at("instruments")) {
            if (!item.is_object() || item.value("provider_id", std::string{"okx"}) != "okx") continue;
            const auto id = item.value("instrument_id", std::string{});
            if (!id.empty()) by_instrument[id] = item;
        }
        if (old_cache->contains("cache_entries") && old_cache->at("cache_entries").is_object())
            cache_entries = old_cache->at("cache_entries");
    }
    if (refreshed_instruments.is_array()) {
        for (const auto& item : refreshed_instruments) {
            if (!item.is_object() || item.value("provider_id", std::string{"okx"}) != "okx") continue;
            const auto id = item.value("instrument_id", std::string{});
            if (id.empty()) continue;
            // این snapshot فقط دادهٔ OKX را نگه می‌دارد؛ fallback نباید زیر کلید cache اولیه ذخیره شود.
            by_instrument[id] = item;
            cache_entries[id] = make_cache_entry(item, window_start_ms, window_end_ms);
        }
    }
    for (auto it = cache_entries.begin(); it != cache_entries.end();) {
        if (!by_instrument.contains(it.key())) it = cache_entries.erase(it);
        else ++it;
    }
    json instruments = json::array();
    for (const auto& [id, item] : by_instrument) { (void)id; instruments.push_back(item); }
    return {
        {"schema_version", "1.0.0"},
        {"cache_contract_version", "1.0.0"},
        {"provider", {{"primary_provider_id", "okx"}}},
        {"cache_policy", {
            {"venue", "OKX"},
            {"market_type", "LINEAR_PERPETUAL"},
            {"timeframes", {{"candles", "1H"}, {"funding", "8H"}, {"open_interest", "1H"}}},
            {"window_policy", "ROLLING_2Y_OHLCV_30D_DERIVATIVES"},
            {"normalization_schema_version", "1.0.0"}
        }},
        {"cache_entries", std::move(cache_entries)},
        {"instruments", std::move(instruments)}
    };
}

inline json collect(int symbol_count, int years,
                       const std::optional<json>& cached_crypto_universe = std::nullopt,
                       const std::optional<json>& cached_market_data = std::nullopt,
                       const std::set<std::string>& required_symbols = {},
                       const std::optional<std::filesystem::path>& market_cache_path = std::nullopt) {
    if (symbol_count < 1 || symbol_count > 100 || years < 1 || years > 2)
        throw std::invalid_argument("symbols_must_be_1_to_100_and_years_1_to_2");
    const auto acquired_ms = now_ms();
    const auto end_ms = (acquired_ms / 3'600'000LL) * 3'600'000LL;
    const auto start_ms = end_ms - static_cast<std::int64_t>(years * 365.25 * 24.0 * 3'600'000.0);
    const auto acquired_text = utc_iso(acquired_ms);
    (void)cached_crypto_universe; // Legacy CoinPaprika cache is deliberately not used by V21.1 production.\n    const auto crypto_universe = load_crypto_universe(required_symbols);
    std::size_t eligible_count = 0U, declared_count = 0U, excluded_non_crypto_count = 0U;
    const auto selected = discover(symbol_count, crypto_universe.symbols, required_symbols,
                                    &eligible_count, &declared_count, &excluded_non_crypto_count);
    const bool discovery_fallback_used = !selected.empty() && selected.front().provider_id != "okx";
    bool fallback_used_any = discovery_fallback_used;
    std::set<std::string> fallback_provider_ids;
    if (discovery_fallback_used) fallback_provider_ids.insert(selected.front().provider_id);
    json instruments = json::array();
    std::size_t instrument_index = 0U;
    for (const auto& item : selected) {
        ++instrument_index;
        json candles = json::array(), funding = json::array(), oi = json::array();
        json errors = json::array();
        Instrument effective_item = item;
        std::string active_provider = item.provider_id;
        std::string provider_instrument_id = item.provider_symbol.empty() ? item.id : item.provider_symbol;
        std::string primary_provider_error;
        bool item_fallback_used = item.provider_id != "okx";
        const json* cached_instrument = nullptr;
        if (item.provider_id == "okx" && cached_market_data && cached_market_data->is_object() &&
            cached_market_data->contains("instruments") &&
            cached_market_data->at("instruments").is_array()) {
            for (const auto& cached_item : cached_market_data->at("instruments")) {
                if (cached_item.value("instrument_id", std::string{}) == item.id) {
                    cached_instrument = &cached_item;
                    break;
                }
            }
        }
        if (cached_instrument) {
            const bool has_entries = cached_market_data && cached_market_data->contains("cache_entries") &&
                cached_market_data->at("cache_entries").is_object();
            if (!has_entries || !valid_cache_entry(cached_market_data->at("cache_entries"),
                    *cached_instrument, item.id, start_ms, end_ms))
                cached_instrument = nullptr;
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
            const auto cached_end_exclusive = last_cached_ms > 0
                ? last_cached_ms + 3'600'000LL : 0;
            has_valid_candle_cache = first_cached_ms > 0 &&
                first_cached_ms <= effective_start_ms + 3LL * 3'600'000LL &&
                last_cached_ms > 0 && end_ms >= cached_end_exclusive &&
                end_ms - cached_end_exclusive <= 10LL * 86'400'000LL &&
                ohlcv_series_complete(cached_candles, start_ms, cached_end_exclusive,
                                      item.listing_time_ms);
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
        std::cout << "L1_COLLECT_START " << instrument_index << "/" << selected.size()
                  << " instrument=" << item.id
                  << " ohlcv_cache=" << (has_valid_candle_cache ? "HIT" : "BACKFILL")
                  << " oi_cache=" << (oi_cache_complete ? "HIT" : "BACKFILL") << std::endl;
        if (item.provider_id == "okx") {
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
            const bool primary_needs_fallback = !errors.empty() ||
                candles.empty() || funding.empty() || oi.empty();
            if (primary_needs_fallback) {
                for (const auto& error : errors) {
                    if (!error.is_string()) continue;
                    if (!primary_provider_error.empty()) primary_provider_error += " | ";
                    primary_provider_error += error.get<std::string>();
                }
                if (primary_provider_error.empty()) primary_provider_error = "primary_series_empty";
                try {
                    const auto contract = cfss::kucoin::find_contract(item.base);
                    if (!contract) throw std::runtime_error("kucoin_contract_not_found");
                    const auto bundle = cfss::kucoin::fetch_bundle(
                        *contract, start_ms, end_ms,
                        end_ms - 30LL * 86'400'000LL,
                        end_ms - 7LL * 86'400'000LL);
                    if (!bundle.candles.empty()) {
                        candles = bundle.candles;
                        funding = bundle.funding;
                        oi = bundle.open_interest;
                        errors = bundle.errors;
                        active_provider = "kucoin";
                        provider_instrument_id = contract->symbol;
                        item_fallback_used = true;
                        effective_item.contract_size = contract->multiplier;
                        effective_item.contract_multiplier = 1.0;
                        effective_item.contract_value_currency = contract->base;
                        effective_item.tick_size = contract->tick_size;
                        effective_item.lot_size = contract->lot_size;
                        effective_item.min_size = contract->min_size;
                        effective_item.listing_time_ms = contract->listing_time_ms;
                        effective_item.turnover = contract->turnover_24h_usd;
                        effective_item.provider_id = "kucoin";
                        effective_item.provider_symbol = contract->symbol;
                    } else {
                        errors.push_back("fallback:kucoin_no_closed_ohlcv");
                    }
                } catch (const std::exception& e) {
                    errors.push_back(std::string{"fallback:kucoin:"} + e.what());
                }
            }
        } else if (item.provider_id == "kucoin") {
            try {
                const auto contract = cfss::kucoin::find_contract(item.base);
                if (!contract) throw std::runtime_error("kucoin_contract_not_found");
                const auto bundle = cfss::kucoin::fetch_bundle(
                    *contract, start_ms, end_ms,
                    end_ms - 30LL * 86'400'000LL,
                    end_ms - 7LL * 86'400'000LL);
                candles = bundle.candles;
                funding = bundle.funding;
                oi = bundle.open_interest;
                errors = bundle.errors;
                active_provider = "kucoin";
                provider_instrument_id = contract->symbol;
                item_fallback_used = true;
                effective_item.contract_size = contract->multiplier;
                effective_item.contract_multiplier = 1.0;
                effective_item.contract_value_currency = contract->base;
                effective_item.tick_size = contract->tick_size;
                effective_item.lot_size = contract->lot_size;
                effective_item.min_size = contract->min_size;
                effective_item.listing_time_ms = contract->listing_time_ms;
                effective_item.turnover = contract->turnover_24h_usd;
                effective_item.provider_symbol = contract->symbol;
            } catch (const std::exception& e) {
                errors.push_back(std::string{"fallback:kucoin:"} + e.what());
            }
        } else {
            errors.push_back("provider:unsupported_provider_id:" + item.provider_id);
        }
        if (item_fallback_used) {
            fallback_used_any = true;
            fallback_provider_ids.insert(active_provider);
        }
        // صفر برای OI دلاری/قراردادی در قرارداد داده معتبر نیست؛ آن را گمشده ثبت می‌کنیم،
        // نه اینکه کل اسکن را متوقف کنیم یا مقدار ساختگی جایگزین کنیم.
        const auto invalid_oi_observations = normalize_open_interest_rows(oi);
        if (invalid_oi_observations > 0U)
            errors.push_back("open_interest_nonpositive_observations:" +
                             std::to_string(invalid_oi_observations));
        const double coverage = ohlcv_coverage_pct(
            candles, start_ms, end_ms, effective_item.listing_time_ms);
        const bool ohlcv_complete = ohlcv_series_complete(
            candles, start_ms, end_ms, effective_item.listing_time_ms);
        const auto has_error_prefix = [&](const std::string& prefix) {
            return std::any_of(errors.begin(), errors.end(), [&](const json& error) {
                return error.is_string() && error.get<std::string>().rfind(prefix, 0U) == 0U;
            });
        };
        const auto funding_freshness = evaluate_series_freshness(
            funding, end_ms, 2LL, 24LL * 60LL * 60LL * 1000LL);
        const auto oi_freshness = evaluate_series_freshness(
            oi, end_ms, 3LL, 3LL * 60LL * 60LL * 1000LL);
        auto funding_status = has_error_prefix("funding:")
            ? std::string{"PARTIAL"} : availability(funding, "funding_rate", 29.0);
        auto oi_status = has_error_prefix("open_interest:")
            ? std::string{"PARTIAL"} : open_interest_availability(oi, 29.0);
        if (funding_status == "AVAILABLE" && funding_freshness.status != "FRESH")
            funding_status = "PARTIAL";
        if (oi_status == "AVAILABLE" && oi_freshness.status != "FRESH")
            oi_status = "PARTIAL";
        const bool kucoin_active = active_provider == "kucoin";
        const std::string instrument_endpoint = kucoin_active
            ? "https://api-futures.kucoin.com/api/v1/contracts/active"
            : "/api/v5/public/instruments?instType=SWAP";
        const std::string ticker_endpoint = kucoin_active
            ? "https://api-futures.kucoin.com/api/v1/contracts/active"
            : "/api/v5/market/tickers?instType=SWAP";
        const std::string ohlcv_endpoint = kucoin_active
            ? "https://api-futures.kucoin.com/api/v1/kline/query"
            : "/api/v5/market/history-candles";
        const std::string funding_endpoint = kucoin_active
            ? "https://api-futures.kucoin.com/api/v1/contract/funding-rates"
            : "/api/v5/public/funding-rate-history";
        const std::string open_interest_endpoint = kucoin_active
            ? "https://api.kucoin.com/api/ua/v2/market/open-interest"
            : "/api/v5/rubik/stat/contracts/open-interest-history";
        json provenance = {
            {"instrument_endpoint", instrument_endpoint},
            {"ticker_endpoint", ticker_endpoint},
            {"ohlcv_endpoint", ohlcv_endpoint},
            {"funding_endpoint", funding_endpoint},
            {"open_interest_endpoint", open_interest_endpoint},
            {"retrieved_at_utc", utc_iso(now_ms())},
            {"provider_instrument_id", provider_instrument_id},
            {"fallback_used", item_fallback_used}
        };
        if (!primary_provider_error.empty())
            provenance["primary_provider_error"] = primary_provider_error;
        instruments.push_back({
            {"instrument_id", effective_item.id},
            {"unified_symbol", effective_item.base + "/USDT:USDT"},
            {"base", effective_item.base}, {"quote", effective_item.quote}, {"settle", effective_item.settle},
            {"contract_type", "linear_perpetual"},
            {"contract_size", effective_item.contract_size},
            {"contract_multiplier", effective_item.contract_multiplier},
            {"contract_value_currency", effective_item.contract_value_currency},
            {"tick_size", effective_item.tick_size},
            {"lot_size", effective_item.lot_size}, {"min_size", effective_item.min_size},
            {"listing_time_ms", effective_item.listing_time_ms},
            {"turnover_24h_usd", effective_item.turnover},
            {"liquidity_threshold_usd", 10000000.0},
            {"liquidity_status", passes_liquidity(effective_item.turnover) ? "ELIGIBLE" : "BELOW_THRESHOLD_PINNED"},
            {"provider_id", active_provider}, {"timeframe", "1h"}, {"candles", candles},
            {"provenance", provenance},
            {"funding", funding}, {"open_interest", oi},
            {"availability", {
                {"ohlcv", ohlcv_complete ? "AVAILABLE" : (candles.empty() ? "UNAVAILABLE" : "PARTIAL")},
                {"funding", funding_status},
                {"open_interest", oi_status}
            }},
            {"coverage", {
                {"ohlcv_rows", candles.size()}, {"funding_rows", funding.size()},
                {"open_interest_rows", oi.size()}, {"ohlcv_coverage_pct", std::min(100.0, coverage)},
                {"funding_coverage_days", coverage_days(funding)},
                {"open_interest_coverage_days", coverage_days(oi)},
                {"funding_latest_age_ms", funding_freshness.latest_age_ms},
                {"funding_max_age_ms", funding_freshness.max_age_ms},
                {"funding_freshness_status", funding_freshness.status},
                {"open_interest_latest_age_ms", oi_freshness.latest_age_ms},
                {"open_interest_max_age_ms", oi_freshness.max_age_ms},
                {"open_interest_freshness_status", oi_freshness.status}
            }},
            {"errors", errors}
        });
        std::cout << "L1_COLLECT_DONE " << instrument_index << "/" << selected.size()
                  << " instrument=" << item.id
                  << " candles=" << candles.size()
                  << " funding=" << funding.size()
                  << " oi=" << oi.size()
                  << " errors=" << errors.size() << std::endl;
        if (market_cache_path &&
            (instrument_index % 25U == 0U || instrument_index == selected.size())) {
            const auto snapshot = make_market_cache_snapshot(cached_market_data, instruments,
                                                          start_ms, end_ms);
            cfss::write_file_atomic(*market_cache_path, snapshot.dump(2) + "\n", false);
            std::cout << "L1_CACHE_CHECKPOINT instruments="
                      << snapshot.at("instruments").size() << std::endl;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(120));
    }
    const char* commit = std::getenv("GITHUB_SHA");
    const auto provider_health = probe_provider_health();
    const auto fear_greed = fetch_fear_greed();
    json selected_ids = json::array();
    std::string scan_material = "1h|" + std::to_string(start_ms) + "|" + std::to_string(end_ms) + "|";
    for (const auto& item : selected) {
        selected_ids.push_back(item.id);
        scan_material += item.id + ":" + item.provider_id + ":" + item.provider_symbol + ";";
    }
    const std::string scan_id = "scan-" + cfss::sha256_hex(scan_material);
    return {
        {"schema_version", "1.2.0"},
        {"run_id", "okx-cpp-" + std::to_string(acquired_ms)},
        {"scan_id", scan_id},
        {"producer", {{"name", "cfss-cpp-l1-collector"}, {"version", "1.0.0"},
                      {"source_commit", commit ? json(commit) : json(nullptr)}}},
        {"acquired_at_utc", acquired_text},
        {"window", {{"timeframe", "1h"}, {"start_ms", start_ms}, {"end_ms", end_ms}}},
        {"provider", {{"primary_provider_id", "okx"},
                      {"display_name", "OKX primary with KuCoin public fallback"},
                      {"fallback_used", fallback_used_any},
                      {"fallback_provider_ids", json(std::vector<std::string>(fallback_provider_ids.begin(), fallback_provider_ids.end()))}}},
        {"provider_health", provider_health}, {"fear_greed", fear_greed},
        {"crypto_universe", crypto_universe.artifact},
        {"universe", {{"declared_usdt_swap_count", declared_count},
                      {"crypto_universe_status", "OWNER_MANIFEST_VERIFIED"},
                      {"crypto_universe_source", "owner_manifest"},
                      {"crypto_universe_symbol_count", crypto_universe.symbols.size()},
                      {"crypto_universe_symbols_sha256", crypto_universe.artifact.at("symbols_sha256")},
                      {"excluded_non_crypto_count", excluded_non_crypto_count},
                      {"eligible_count", eligible_count},
                      {"selected_count", selected.size()}, {"target_count", symbol_count},
                      {"liquidity_threshold_usd", 10000000.0},
                      {"selection_method", discovery_fallback_used
                          ? "kucoin_fallback_top_turnover_usd_desc_with_btc_first"
                          : "top_turnover_usd_desc_with_btc_first"},
                      {"selection_timestamp_utc", acquired_text},
                      {"selected_instrument_ids", selected_ids}}},
        {"instruments", instruments}
    };
}
} // namespace cfss::okx
