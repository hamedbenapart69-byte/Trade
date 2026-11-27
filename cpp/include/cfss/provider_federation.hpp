#pragma once

#include "cfss/provider_resilience.hpp"

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <cstdio>
#include <utility>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

namespace cfss::federation {

using json = nlohmann::json;

inline std::string utc_now_iso() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t value = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#if defined(_WIN32)
    gmtime_s(&utc, &value);
#else
    gmtime_r(&value, &utc);
#endif
    char buffer[32]{};
    std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
    return std::string{buffer};
}

struct HttpResult {
    long status{0};
    CURLcode transport{CURLE_FAILED_INIT};
    std::string body;
    int attempts{0};
};

inline std::size_t write_body(char* data, std::size_t size, std::size_t count, void* context) {
    if (!context || (size != 0U && count > static_cast<std::size_t>(-1) / size)) return 0U;
    const auto bytes = size * count;
    static_cast<std::string*>(context)->append(data, bytes);
    return bytes;
}

inline HttpResult http_get(std::string_view url, long timeout_seconds = 20L, int max_attempts = 3,
                           const std::vector<std::string>& extra_headers = {}) {
    HttpResult last;
    const std::string url_text{url};
    for (int attempt = 0; attempt < std::max(1, max_attempts); ++attempt) {
        HttpResult result;
        result.attempts = attempt + 1;
        CURL* handle = curl_easy_init();
        if (!handle) throw std::runtime_error("federation_curl_init_failed");
        curl_easy_setopt(handle, CURLOPT_URL, url_text.c_str());
        curl_easy_setopt(handle, CURLOPT_WRITEFUNCTION, write_body);
        curl_easy_setopt(handle, CURLOPT_WRITEDATA, &result.body);
        curl_easy_setopt(handle, CURLOPT_CONNECTTIMEOUT, 8L);
        curl_easy_setopt(handle, CURLOPT_TIMEOUT, timeout_seconds);
        curl_easy_setopt(handle, CURLOPT_FOLLOWLOCATION, 0L);
        curl_easy_setopt(handle, CURLOPT_SSL_VERIFYPEER, 1L);
        curl_easy_setopt(handle, CURLOPT_SSL_VERIFYHOST, 2L);
        curl_easy_setopt(handle, CURLOPT_NOSIGNAL, 1L);
        curl_easy_setopt(handle, CURLOPT_USERAGENT, "CFSS-provider-federation/21.1");
        curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Accept: application/json");
        for (const auto& header : extra_headers) headers = curl_slist_append(headers, header.c_str());
        curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
        result.transport = curl_easy_perform(handle);
        curl_slist_free_all(headers);
        if (result.transport == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &result.status);
        curl_easy_cleanup(handle);
        last = result;
        const bool success = result.transport == CURLE_OK && result.status == 200L;
        // HTTP 429 is not retried blindly: without honoring Retry-After, retries
        // amplify provider throttling and consume quota. The caller records RATE_LIMITED.
        const bool retryable = result.transport != CURLE_OK || result.status == 408L ||
            (result.status >= 500L && result.status <= 599L);
        if (success || !retryable || attempt + 1 >= std::max(1, max_attempts)) return result;
        const auto delay = std::chrono::milliseconds(250 * (1 << std::min(attempt, 3)));
        std::this_thread::sleep_for(delay);
    }
    return last;
}

inline cfss::resilience::CircuitBreaker& coinmarketcap_breaker() {
    static cfss::resilience::CircuitBreaker breaker(3U, std::chrono::seconds(60));
    return breaker;
}

inline cfss::resilience::CircuitBreaker& coinpaprika_breaker() {
    static cfss::resilience::CircuitBreaker breaker(3U, std::chrono::seconds(60));
    return breaker;
}

inline std::optional<double> numeric_value(const json& value) {
    try {
        if (value.is_number()) {
            const double number = value.get<double>();
            if (std::isfinite(number)) return number;
        }
        if (value.is_string()) {
            const auto raw = value.get<std::string>();
            std::size_t consumed = 0U;
            const double number = std::stod(raw, &consumed);
            if (consumed == raw.size() && std::isfinite(number)) return number;
        }
    } catch (...) {}
    return std::nullopt;
}

inline std::string string_value(const json& value) {
    if (value.is_string()) return value.get<std::string>();
    if (value.is_number_integer()) return std::to_string(value.get<std::int64_t>());
    return {};
}

struct MarketTicker {
    std::string provider_id;
    std::string provider_asset_id;
    std::string symbol;
    std::string name;
    std::string provider_timestamp_utc;
    double price_usd{0.0};
    double market_cap_usd{0.0};
    double volume_24h_usd{0.0};
    std::int64_t rank{0};
    std::string external_asset_id;
};

struct ProviderSnapshot {
    std::string provider_id;
    std::string status{"NOT_TESTED"};
    std::string retrieved_at_utc;
    long http_status{0};
    std::string error;
    std::string endpoint_used;
    std::string freshness_status{"NOT_TESTED"};
    std::string license_status{"NOT_VERIFIED"};
    int request_attempts{0};
    std::vector<MarketTicker> tickers;
};

struct ProviderCapability {
    std::string provider_id;
    std::string field;
    std::string market_scope;
    std::string unit;
    std::string quote_currency;
    std::vector<std::string> canonical_assets;
    std::int64_t max_age_ms{0};
    std::int64_t history_days{0};
    std::string license_status{"NOT_VERIFIED"};
    std::string runtime_status{"NOT_TESTED"};
};

struct CanonicalRecord {
    std::string canonical_asset_id;
    std::string canonical_symbol;
    std::string provider_id;
    std::string provider_instrument_id;
    std::string market_scope;
    std::string field;
    double value{0.0};
    std::string unit;
    std::string quote_currency;
    std::string interval;
    std::int64_t event_timestamp_ms{0};
    std::int64_t provider_timestamp_ms{0};
    std::int64_t retrieved_at_ms{0};
    std::string quality_status{"NOT_VERIFIED"};
    std::string data_class{"UNAVAILABLE"};
    std::string license_status{"NOT_VERIFIED"};
};

class ProviderCapabilityRegistry {
public:
    void add(ProviderCapability capability) {
        if (capability.provider_id.empty() || capability.field.empty() ||
            capability.market_scope.empty() || capability.unit.empty() ||
            capability.max_age_ms <= 0 || capability.license_status.empty() ||
            capability.runtime_status.empty()) {
            throw std::invalid_argument("provider_capability_invalid");
        }
        const auto duplicate = std::find_if(entries_.begin(), entries_.end(),
            [&](const ProviderCapability& existing) {
                return existing.provider_id == capability.provider_id &&
                       existing.field == capability.field &&
                       existing.market_scope == capability.market_scope;
            });
        if (duplicate != entries_.end()) throw std::invalid_argument("provider_capability_duplicate");
        entries_.push_back(std::move(capability));
    }

    std::vector<ProviderCapability> eligible(std::string_view field,
                                              std::string_view market_scope,
                                              std::string_view canonical_symbol) const {
        std::vector<ProviderCapability> result;
        for (const auto& item : entries_) {
            const bool asset_supported = item.canonical_assets.empty() ||
                std::find(item.canonical_assets.begin(), item.canonical_assets.end(),
                          canonical_symbol) != item.canonical_assets.end();
            if (item.field == field && item.market_scope == market_scope &&
                asset_supported && item.license_status == "COMPATIBLE" &&
                item.runtime_status == "REACHABLE") {
                result.push_back(item);
            }
        }
        return result;
    }

private:
    std::vector<ProviderCapability> entries_;
};

inline bool fallback_compatible(const CanonicalRecord& required,
                                const CanonicalRecord& candidate,
                                std::int64_t now_ms, std::int64_t max_age_ms) {
    if (max_age_ms <= 0 || required.provider_id.empty() || candidate.provider_id.empty() ||
        required.provider_id == candidate.provider_id || candidate.provider_instrument_id.empty() ||
        required.canonical_asset_id != candidate.canonical_asset_id ||
        required.market_scope != candidate.market_scope ||
        required.field != candidate.field || required.unit != candidate.unit ||
        required.quote_currency != candidate.quote_currency ||
        required.interval != candidate.interval ||
        required.event_timestamp_ms != candidate.event_timestamp_ms ||
        candidate.event_timestamp_ms <= 0 || candidate.provider_timestamp_ms <= 0 ||
        candidate.retrieved_at_ms <= 0 || candidate.provider_timestamp_ms > now_ms ||
        candidate.retrieved_at_ms > now_ms ||
        candidate.quality_status != "VALID" || candidate.data_class != "REAL" ||
        candidate.license_status != "COMPATIBLE") {
        return false;
    }
    return std::isfinite(candidate.value) &&
        now_ms - candidate.provider_timestamp_ms <= max_age_ms &&
        now_ms - candidate.retrieved_at_ms <= max_age_ms;
}

struct AssetIdentity {
    std::string canonical_asset_id;
    std::string canonical_symbol;
    std::string coinmarketcap_id;
    std::string coingecko_id;
    std::string coinpaprika_id;
};

inline const MarketTicker* find_by_provider_id(const ProviderSnapshot& snapshot,
                                                std::string_view provider_asset_id);
inline const MarketTicker* find_by_external_id(const ProviderSnapshot& snapshot,
                                                std::string_view external_asset_id);

inline std::optional<std::int64_t> parse_utc_iso_ms(const std::string& value) {
    if (value.size() < 19U) return std::nullopt;
    std::tm parsed{};
    std::istringstream input{value.substr(0U, 19U)};
    input >> std::get_time(&parsed, "%Y-%m-%dT%H:%M:%S");
    if (input.fail()) return std::nullopt;
#if defined(_WIN32)
    const auto seconds = _mkgmtime(&parsed);
#else
    const auto seconds = timegm(&parsed);
#endif
    if (seconds < 0) return std::nullopt;
    return static_cast<std::int64_t>(seconds) * 1000LL;
}

inline void evaluate_snapshot_freshness(ProviderSnapshot& snapshot,
                                        const std::vector<AssetIdentity>& identities,
                                        std::int64_t now_ms,
                                        std::int64_t max_age_ms) {
    if (snapshot.status != "LIVE_RESPONSE_PARSED") {
        snapshot.freshness_status = "UNAVAILABLE";
        return;
    }
    if (identities.empty() || now_ms <= 0 || max_age_ms <= 0) {
        snapshot.freshness_status = "NOT_TESTED";
        return;
    }
    std::size_t checked = 0U;
    for (const auto& identity : identities) {
        const std::string* provider_id = nullptr;
        if (snapshot.provider_id == "coinmarketcap") provider_id = &identity.coinmarketcap_id;
        else if (snapshot.provider_id == "coingecko") provider_id = &identity.coingecko_id;
        else if (snapshot.provider_id == "coinpaprika") provider_id = &identity.coinpaprika_id;
        if (snapshot.provider_id == "coinranking") {
            const auto* ticker = find_by_external_id(snapshot, identity.coinmarketcap_id);
            if (!ticker || ticker->symbol != identity.canonical_symbol) {
                snapshot.freshness_status = "PARTIAL_COVERAGE";
                return;
            }
            const auto timestamp = parse_utc_iso_ms(ticker->provider_timestamp_utc);
            if (!timestamp) {
                snapshot.freshness_status = "TIMESTAMP_UNAVAILABLE";
                return;
            }
            const auto age = now_ms - *timestamp;
            if (age < -300'000LL || age > max_age_ms) {
                snapshot.freshness_status = "STALE";
                return;
            }
            ++checked;
            continue;
        }
        if (!provider_id) {
            snapshot.freshness_status = "UNSUPPORTED_PROVIDER";
            return;
        }
        const auto* ticker = find_by_provider_id(snapshot, *provider_id);
        if (!ticker || ticker->symbol != identity.canonical_symbol) {
            snapshot.freshness_status = "PARTIAL_COVERAGE";
            return;
        }
        const auto timestamp = parse_utc_iso_ms(ticker->provider_timestamp_utc);
        if (!timestamp) {
            snapshot.freshness_status = "TIMESTAMP_UNAVAILABLE";
            return;
        }
        const auto age = now_ms - *timestamp;
        if (age < -300'000LL || age > max_age_ms) {
            snapshot.freshness_status = "STALE";
            return;
        }
        ++checked;
    }
    snapshot.freshness_status = checked == identities.size() ? "FRESH" : "PARTIAL_COVERAGE";
}

// This is a discovery seed only. Membership is not a production-universe decision.
inline const std::vector<AssetIdentity>& candidate_identity_seed() {
    static const std::vector<AssetIdentity> seed{
        {"bitcoin", "BTC", "1", "bitcoin", "btc-bitcoin"},
        {"ethereum", "ETH", "1027", "ethereum", "eth-ethereum"},
        {"solana", "SOL", "5426", "solana", "sol-solana"},
        {"binance-coin", "BNB", "1839", "binancecoin", "bnb-binance-coin"},
        {"ripple", "XRP", "52", "ripple", "xrp-xrp"},
        {"dogecoin", "DOGE", "74", "dogecoin", "doge-dogecoin"},
        {"cardano", "ADA", "2010", "cardano", "ada-cardano"},
        {"chainlink", "LINK", "1975", "chainlink", "link-chainlink"},
        {"avalanche", "AVAX", "5805", "avalanche-2", "avax-avalanche"}
    };
    return seed;
}

inline std::vector<MarketTicker> parse_coinmarketcap(const json& payload) {
    if (!payload.is_object() || !payload.contains("data") ||
        (!payload.at("data").is_array() && !payload.at("data").is_object())) {
        throw std::invalid_argument("coinmarketcap_response_shape_invalid");
    }
    std::vector<MarketTicker> output;
    const auto parse_row = [&](const json& row) {
        if (!row.is_object()) return;
        const json* quote_pointer = row.contains("quote") ? &row.at("quote") :
            (row.contains("quotes") ? &row.at("quotes") : nullptr);
        if (!quote_pointer) return;
        const json* usd_pointer = nullptr;
        const auto& quote = *quote_pointer;
        if (quote.is_array()) {
            for (const auto& quote_row : quote) {
                if (quote_row.is_object() && string_value(quote_row.value("symbol", json{})) == "USD") {
                    usd_pointer = &quote_row;
                    break;
                }
            }
        } else if (quote.is_object() && quote.contains("USD")) {
            usd_pointer = &quote.at("USD");
        }
        if (!usd_pointer) return;
        const auto& usd = *usd_pointer;
        const auto price = numeric_value(usd.value("price", json{}));
        const auto market_cap = numeric_value(usd.value("market_cap", json{}));
        const auto volume = numeric_value(usd.value("volume_24h", json{}));
        const auto id = string_value(row.value("id", json{}));
        const auto symbol = string_value(row.value("symbol", json{}));
        if (!price || !market_cap || !volume || id.empty() || symbol.empty() ||
            *price <= 0.0 || *market_cap < 0.0 || *volume < 0.0) return;
        output.push_back({
            "coinmarketcap", id, symbol, string_value(row.value("name", json{})),
            string_value(usd.value("last_updated", json{})), *price, *market_cap, *volume,
            row.value("cmc_rank", std::int64_t{0}), ""
        });
    };
    const auto& data = payload.at("data");
    if (data.is_array()) {
        for (const auto& row : data) parse_row(row);
    } else {
        for (const auto& item : data.items()) parse_row(item.value());
    }
    return output;
}

inline std::string epoch_seconds_to_utc_iso(std::int64_t seconds) {
    if (seconds <= 0) return {};
    const std::time_t raw = static_cast<std::time_t>(seconds);
    std::tm tm_value{};
#if defined(_WIN32)
    if (gmtime_s(&tm_value, &raw) != 0) return {};
#else
    if (!gmtime_r(&raw, &tm_value)) return {};
#endif
    char buffer[32]{};
    if (std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm_value) == 0U) return {};
    return std::string{buffer};
}

inline std::optional<MarketTicker> parse_coinranking_coin_detail(const json& payload) {
    if (!payload.is_object() || !payload.contains("data") ||
        !payload.at("data").is_object() || !payload.at("data").contains("coin") ||
        !payload.at("data").at("coin").is_object()) return std::nullopt;
    const auto& coin = payload.at("data").at("coin");
    const auto uuid = string_value(coin.value("uuid", json{}));
    const auto external_id = string_value(coin.value("coinMarketCapId", json{}));
    const auto symbol = string_value(coin.value("symbol", json{}));
    const auto name = string_value(coin.value("name", json{}));
    const auto price = numeric_value(coin.value("price", json{}));
    const auto market_cap = numeric_value(coin.value("marketCap", json{}));
    const auto volume = numeric_value(coin.value("24hVolume", json{}));
    const auto price_at = numeric_value(coin.value("priceAt", json{}));
    if (uuid.empty() || external_id.empty() || symbol.empty() || name.empty() ||
        !price || !market_cap || !volume || !price_at ||
        *price <= 0.0 || *market_cap < 0.0 || *volume < 0.0 || *price_at <= 0.0) {
        return std::nullopt;
    }
    const auto timestamp = epoch_seconds_to_utc_iso(static_cast<std::int64_t>(*price_at));
    if (timestamp.empty()) return std::nullopt;
    return MarketTicker{
        "coinranking", uuid, symbol, name, timestamp, *price, *market_cap, *volume,
        coin.value("rank", std::int64_t{0}), external_id
    };
}

inline std::vector<MarketTicker> parse_coinpaprika(const json& payload) {
    if (!payload.is_array()) throw std::invalid_argument("coinpaprika_response_shape_invalid");
    std::vector<MarketTicker> output;
    for (const auto& row : payload) {
        if (!row.is_object() || !row.contains("quotes") || !row.at("quotes").is_object() ||
            !row.at("quotes").contains("USD")) continue;
        const auto& usd = row.at("quotes").at("USD");
        const auto price = numeric_value(usd.value("price", json{}));
        const auto market_cap = numeric_value(usd.value("market_cap", json{}));
        const auto volume = numeric_value(usd.value("volume_24h", json{}));
        const auto id = string_value(row.value("id", json{}));
        const auto symbol = string_value(row.value("symbol", json{}));
        if (!price || !market_cap || !volume || id.empty() || symbol.empty() ||
            *price <= 0.0 || *market_cap < 0.0 || *volume < 0.0) continue;
        output.push_back({
            "coinpaprika", id, symbol, string_value(row.value("name", json{})),
            string_value(row.value("last_updated", json{})), *price, *market_cap, *volume,
            row.value("rank", std::int64_t{0}), ""
        });
    }
    return output;
}

inline ProviderSnapshot fetch_coinmarketcap() {
    ProviderSnapshot snapshot;
    snapshot.provider_id = "coinmarketcap";
    snapshot.retrieved_at_utc = utc_now_iso();
    auto& breaker = coinmarketcap_breaker();
    if (!breaker.allow_request()) {
        snapshot.status = "PROVIDER_CIRCUIT_OPEN";
        snapshot.error = "coinmarketcap_circuit_open";
        return snapshot;
    }

    const char* key_value = std::getenv("CMC_PRO_API_KEY");
    const bool authenticated = key_value && !std::string_view{key_value}.empty();
    std::vector<std::string> headers;
    std::string url;
    if (authenticated) {
        snapshot.license_status = "PERSONAL_FREE_BASIC_API_KEY";
        snapshot.endpoint_used = "v1_quotes_latest_authenticated";
        headers.push_back("X-CMC_PRO_API_KEY: " + std::string{key_value});
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
            "?id=1,1027,5426,1839,52,74,2010,1975,5805&convert=USD";
    } else {
        snapshot.license_status = "KEYLESS_EVALUATION_ONLY";
        snapshot.endpoint_used = "public_api_v2_simple_price";
        url = "https://pro-api.coinmarketcap.com/public-api/v2/simple/price"
            "?id=1,1027,5426,1839,52,74,2010,1975,5805&convert=USD&include_all=true&skip_invalid=true";
    }

    const auto response = http_get(url, 20L, 3, headers);
    snapshot.request_attempts = response.attempts;
    snapshot.http_status = response.status;
    if (response.transport != CURLE_OK || response.status != 200L) {
        snapshot.status = response.status == 429L ? "PROVIDER_RATE_LIMITED" :
            (response.status == 401L ? "PROVIDER_AUTH_FAILED" :
            (response.status == 403L ? "PROVIDER_BLOCKED" : "UNAVAILABLE"));
        snapshot.error = authenticated
            ? "coinmarketcap_authenticated_quotes_unavailable"
            : "coinmarketcap_keyless_simple_price_unavailable";
        breaker.record_failure();
        return snapshot;
    }
    try {
        const auto payload = json::parse(response.body);
        snapshot.tickers = parse_coinmarketcap(payload);
        snapshot.status = snapshot.tickers.empty() ? "FAILED" : "LIVE_RESPONSE_PARSED";
        if (snapshot.tickers.empty()) {
            snapshot.error = "coinmarketcap_no_valid_tickers";
            breaker.record_failure();
        } else {
            breaker.record_success();
        }
    } catch (const std::exception& error) {
        snapshot.status = "FAILED";
        snapshot.error = std::string{"coinmarketcap_parse_failed:"} + error.what();
        breaker.record_failure();
    }
    return snapshot;
}

inline std::vector<MarketTicker> parse_coingecko(const json& payload) {
    if (!payload.is_array()) throw std::invalid_argument("coingecko_response_shape_invalid");
    std::vector<MarketTicker> output;
    for (const auto& row : payload) {
        if (!row.is_object()) continue;
        const auto price = numeric_value(row.value("current_price", json{}));
        const auto market_cap = numeric_value(row.value("market_cap", json{}));
        const auto volume = numeric_value(row.value("total_volume", json{}));
        const auto id = string_value(row.value("id", json{}));
        auto symbol = string_value(row.value("symbol", json{}));
        std::transform(symbol.begin(), symbol.end(), symbol.begin(),
            [](unsigned char ch) { return static_cast<char>(std::toupper(ch)); });
        if (!price || !market_cap || !volume || id.empty() || symbol.empty() ||
            *price <= 0.0 || *market_cap < 0.0 || *volume < 0.0) continue;
        output.push_back({
            "coingecko", id, symbol, string_value(row.value("name", json{})),
            string_value(row.value("last_updated", json{})), *price, *market_cap, *volume,
            row.value("market_cap_rank", std::int64_t{0}), ""
        });
    }
    return output;
}

inline cfss::resilience::CircuitBreaker& coingecko_breaker() {
    static cfss::resilience::CircuitBreaker breaker(3U, std::chrono::seconds(60));
    return breaker;
}

inline ProviderSnapshot fetch_coingecko() {
    ProviderSnapshot snapshot;
    snapshot.provider_id = "coingecko";
    snapshot.endpoint_used = "coins_markets";
    snapshot.retrieved_at_utc = utc_now_iso();
    auto& breaker = coingecko_breaker();
    if (!breaker.allow_request()) {
        snapshot.status = "PROVIDER_CIRCUIT_OPEN";
        snapshot.error = "coingecko_circuit_open";
        return snapshot;
    }
    const auto response = http_get(
        "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false");
    snapshot.http_status = response.status;
    snapshot.request_attempts = response.attempts;
    if (response.transport != CURLE_OK || response.status != 200L) {
        breaker.record_failure();
        snapshot.status = response.status == 403L ? "PROVIDER_BLOCKED" :
            (response.status == 429L ? "PROVIDER_RATE_LIMITED" : "UNAVAILABLE");
        snapshot.error = std::string{"coingecko_transport_or_http_error:"} +
            std::to_string(response.status) + ":" + curl_easy_strerror(response.transport);
        return snapshot;
    }
    try {
        const auto payload = json::parse(response.body);
        snapshot.tickers = parse_coingecko(payload);
        snapshot.status = snapshot.tickers.empty() ? "FAILED" : "LIVE_RESPONSE_PARSED";
        snapshot.freshness_status = "NOT_TESTED";
        if (snapshot.tickers.empty()) snapshot.error = "coingecko_no_valid_tickers";
        if (snapshot.tickers.empty()) breaker.record_failure();
        else breaker.record_success();
    } catch (const std::exception& error) {
        snapshot.status = "FAILED";
        snapshot.error = std::string{"coingecko_parse_failed:"} + error.what();
        breaker.record_failure();
    }
    return snapshot;
}

inline ProviderSnapshot fetch_coinpaprika() {
    ProviderSnapshot snapshot;
    snapshot.provider_id = "coinpaprika";
    snapshot.license_status = "PERSONAL_USE_ONLY";
    snapshot.endpoint_used = "tickers";
    snapshot.retrieved_at_utc = utc_now_iso();
    auto& breaker = coinpaprika_breaker();
    if (!breaker.allow_request()) {
        snapshot.status = "PROVIDER_CIRCUIT_OPEN";
        snapshot.error = "coinpaprika_circuit_open";
        return snapshot;
    }
    const auto response = http_get("https://api.coinpaprika.com/v1/tickers?quotes=USD");
    snapshot.http_status = response.status;
    snapshot.request_attempts = response.attempts;
    if (response.transport != CURLE_OK || response.status != 200L) {
        snapshot.status = response.status == 429L ? "PROVIDER_RATE_LIMITED" : "UNAVAILABLE";
        breaker.record_failure();
        snapshot.status = response.status == 403L ? "PROVIDER_BLOCKED" :
            (response.status == 429L ? "PROVIDER_RATE_LIMITED" : "UNAVAILABLE");
        snapshot.error = std::string{"coinpaprika_transport_or_http_error:"} +
            std::to_string(response.status) + ":" + curl_easy_strerror(response.transport);
        return snapshot;
    }
    try {
        const auto payload = json::parse(response.body);
        snapshot.tickers = parse_coinpaprika(payload);
        snapshot.status = snapshot.tickers.empty() ? "FAILED" : "LIVE_RESPONSE_PARSED";
        snapshot.freshness_status = "NOT_TESTED";
        if (snapshot.tickers.empty()) snapshot.error = "coinpaprika_no_valid_tickers";
        if (snapshot.tickers.empty()) breaker.record_failure();
        else breaker.record_success();
    } catch (const std::exception& error) {
        snapshot.status = "FAILED";
        snapshot.error = std::string{"coinpaprika_parse_failed:"} + error.what();
        breaker.record_failure();
    }
    return snapshot;
}

inline ProviderSnapshot fetch_coinranking(
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    ProviderSnapshot snapshot;
    snapshot.provider_id = "coinranking";
    snapshot.license_status = "PERSONAL_INTERNAL_USE_FREE_PLAN";
    snapshot.endpoint_used = "coins+coin_details";
    snapshot.retrieved_at_utc = utc_now_iso();

    const char* key_value = std::getenv("COINRANKING_API_KEY");
    if (!key_value || std::string_view{key_value}.empty()) {
        snapshot.status = "NOT_CONFIGURED";
        snapshot.error = "coinranking_api_key_missing";
        return snapshot;
    }
    const std::string api_key{key_value};
    const std::vector<std::string> headers{"x-access-token: " + api_key};
    const auto listing = http_get(
        "https://api.coinranking.com/v2/coins?limit=100&orderBy=marketCap&orderDirection=desc",
        20L, 3, headers);
    snapshot.request_attempts = listing.attempts;
    snapshot.http_status = listing.status;
    if (listing.transport != CURLE_OK || listing.status != 200L) {
        snapshot.status = listing.status == 401L ? "PROVIDER_AUTH_FAILED" :
            (listing.status == 403L ? "PROVIDER_PLAN_RESTRICTED" :
            (listing.status == 429L ? "PROVIDER_RATE_LIMITED" : "UNAVAILABLE"));
        snapshot.error = "coinranking_coin_list_request_failed";
        return snapshot;
    }

    try {
        const auto payload = json::parse(listing.body);
        if (!payload.contains("data") || !payload.at("data").is_object() ||
            !payload.at("data").contains("coins") || !payload.at("data").at("coins").is_array()) {
            snapshot.status = "FAILED";
            snapshot.error = "coinranking_coin_list_shape_invalid";
            return snapshot;
        }
        const auto& coins = payload.at("data").at("coins");
        std::size_t missing = 0U;
        for (const auto& identity : identities) {
            const auto found = std::find_if(coins.begin(), coins.end(), [&](const json& coin) {
                return coin.is_object() &&
                    string_value(coin.value("coinMarketCapId", json{})) == identity.coinmarketcap_id &&
                    string_value(coin.value("symbol", json{})) == identity.canonical_symbol;
            });
            if (found == coins.end()) {
                ++missing;
                continue;
            }
            const auto uuid = string_value(found->value("uuid", json{}));
            if (uuid.empty()) {
                ++missing;
                continue;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(250));
            const auto detail = http_get(
                std::string{"https://api.coinranking.com/v2/coin/"} + uuid, 20L, 3, headers);
            snapshot.request_attempts += detail.attempts;
            snapshot.http_status = detail.status;
            if (detail.transport != CURLE_OK || detail.status != 200L) {
                ++missing;
                continue;
            }
            const auto parsed = parse_coinranking_coin_detail(json::parse(detail.body));
            if (!parsed || parsed->symbol != identity.canonical_symbol ||
                parsed->external_asset_id != identity.coinmarketcap_id) {
                ++missing;
                continue;
            }
            snapshot.tickers.push_back(*parsed);
        }
        snapshot.status = snapshot.tickers.empty() ? "FAILED" : "LIVE_RESPONSE_PARSED";
        if (missing > 0U) {
            snapshot.error = "coinranking_candidate_coverage_partial:" +
                std::to_string(snapshot.tickers.size()) + "/" + std::to_string(identities.size());
        }
        return snapshot;
    } catch (const std::exception& error) {
        snapshot.status = "FAILED";
        snapshot.error = std::string{"coinranking_parse_failed:"} + error.what();
        return snapshot;
    }
}

inline const MarketTicker* find_by_provider_id(const ProviderSnapshot& snapshot,
                                                std::string_view provider_asset_id) {
    const auto found = std::find_if(snapshot.tickers.begin(), snapshot.tickers.end(),
        [&](const MarketTicker& ticker) { return ticker.provider_asset_id == provider_asset_id; });
    return found == snapshot.tickers.end() ? nullptr : &*found;
}

inline const MarketTicker* find_by_external_id(const ProviderSnapshot& snapshot,
                                                std::string_view external_asset_id) {
    const auto found = std::find_if(snapshot.tickers.begin(), snapshot.tickers.end(),
        [&](const MarketTicker& ticker) { return ticker.external_asset_id == external_asset_id; });
    return found == snapshot.tickers.end() ? nullptr : &*found;
}

struct CrossProviderReference {
    std::string canonical_asset_id;
    std::string canonical_symbol;
    std::string classification{"UNAVAILABLE"};
    double coinmarketcap_price_usd{0.0};
    double coingecko_price_usd{0.0};
    double coinpaprika_price_usd{0.0};
    double coinranking_price_usd{0.0};
    double price_difference_bps{0.0};
    double coinmarketcap_market_cap_usd{0.0};
    double coingecko_market_cap_usd{0.0};
    double coinpaprika_market_cap_usd{0.0};
    double coinranking_market_cap_usd{0.0};
    double coinmarketcap_volume_24h_usd{0.0};
    double coingecko_volume_24h_usd{0.0};
    double coinpaprika_volume_24h_usd{0.0};
    double coinranking_volume_24h_usd{0.0};
};

inline std::vector<CrossProviderReference> compare_candidate_references(
    const ProviderSnapshot& cmc, const ProviderSnapshot& paprika,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_provider_id(cmc, identity.coinmarketcap_id);
        const auto* b = find_by_provider_id(paprika, identity.coinpaprika_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coinmarketcap_price_usd = a->price_usd;
            row.coinpaprika_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coinmarketcap_market_cap_usd = a->market_cap_usd;
            row.coinpaprika_market_cap_usd = b->market_cap_usd;
            row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coinmarketcap_price_usd = a->price_usd;
                row.coinmarketcap_market_cap_usd = a->market_cap_usd;
                row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coinpaprika_price_usd = b->price_usd;
                row.coinpaprika_market_cap_usd = b->market_cap_usd;
                row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline std::vector<CrossProviderReference> compare_cmc_coingecko_references(
    const ProviderSnapshot& cmc, const ProviderSnapshot& gecko,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_provider_id(cmc, identity.coinmarketcap_id);
        const auto* b = find_by_provider_id(gecko, identity.coingecko_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coinmarketcap_price_usd = a->price_usd;
            row.coingecko_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coinmarketcap_market_cap_usd = a->market_cap_usd;
            row.coingecko_market_cap_usd = b->market_cap_usd;
            row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            row.coingecko_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coinmarketcap_price_usd = a->price_usd;
                row.coinmarketcap_market_cap_usd = a->market_cap_usd;
                row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coingecko_price_usd = b->price_usd;
                row.coingecko_market_cap_usd = b->market_cap_usd;
                row.coingecko_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline std::vector<CrossProviderReference> compare_coingecko_coinpaprika_references(
    const ProviderSnapshot& gecko, const ProviderSnapshot& paprika,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_provider_id(gecko, identity.coingecko_id);
        const auto* b = find_by_provider_id(paprika, identity.coinpaprika_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coingecko_price_usd = a->price_usd;
            row.coinpaprika_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coingecko_market_cap_usd = a->market_cap_usd;
            row.coinpaprika_market_cap_usd = b->market_cap_usd;
            row.coingecko_volume_24h_usd = a->volume_24h_usd;
            row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coingecko_price_usd = a->price_usd;
                row.coingecko_market_cap_usd = a->market_cap_usd;
                row.coingecko_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coinpaprika_price_usd = b->price_usd;
                row.coinpaprika_market_cap_usd = b->market_cap_usd;
                row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline std::vector<CrossProviderReference> compare_cmc_coinranking_references(
    const ProviderSnapshot& cmc, const ProviderSnapshot& ranking,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_provider_id(cmc, identity.coinmarketcap_id);
        const auto* b = find_by_external_id(ranking, identity.coinmarketcap_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coinmarketcap_price_usd = a->price_usd;
            row.coinranking_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coinmarketcap_market_cap_usd = a->market_cap_usd;
            row.coinranking_market_cap_usd = b->market_cap_usd;
            row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            row.coinranking_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coinmarketcap_price_usd = a->price_usd;
                row.coinmarketcap_market_cap_usd = a->market_cap_usd;
                row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coinranking_price_usd = b->price_usd;
                row.coinranking_market_cap_usd = b->market_cap_usd;
                row.coinranking_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline std::vector<CrossProviderReference> compare_cmc_coinpaprika_references(
    const ProviderSnapshot& cmc, const ProviderSnapshot& paprika,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_provider_id(cmc, identity.coinmarketcap_id);
        const auto* b = find_by_provider_id(paprika, identity.coinpaprika_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coinmarketcap_price_usd = a->price_usd;
            row.coinpaprika_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coinmarketcap_market_cap_usd = a->market_cap_usd;
            row.coinpaprika_market_cap_usd = b->market_cap_usd;
            row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coinmarketcap_price_usd = a->price_usd;
                row.coinmarketcap_market_cap_usd = a->market_cap_usd;
                row.coinmarketcap_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coinpaprika_price_usd = b->price_usd;
                row.coinpaprika_market_cap_usd = b->market_cap_usd;
                row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline std::vector<CrossProviderReference> compare_coinranking_coinpaprika_references(
    const ProviderSnapshot& ranking, const ProviderSnapshot& paprika,
    const std::vector<AssetIdentity>& identities = candidate_identity_seed()) {
    std::vector<CrossProviderReference> output;
    for (const auto& identity : identities) {
        CrossProviderReference row;
        row.canonical_asset_id = identity.canonical_asset_id;
        row.canonical_symbol = identity.canonical_symbol;
        const auto* a = find_by_external_id(ranking, identity.coinmarketcap_id);
        const auto* b = find_by_provider_id(paprika, identity.coinpaprika_id);
        if (a && b && a->symbol == identity.canonical_symbol && b->symbol == identity.canonical_symbol) {
            row.classification = "TWO_SOURCE_IDENTITY_MATCHED";
            row.coinranking_price_usd = a->price_usd;
            row.coinpaprika_price_usd = b->price_usd;
            const double midpoint = (a->price_usd + b->price_usd) / 2.0;
            row.price_difference_bps = midpoint > 0.0
                ? std::abs(a->price_usd - b->price_usd) / midpoint * 10000.0 : 0.0;
            row.coinranking_market_cap_usd = a->market_cap_usd;
            row.coinpaprika_market_cap_usd = b->market_cap_usd;
            row.coinranking_volume_24h_usd = a->volume_24h_usd;
            row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
        } else if (a || b) {
            row.classification = "ONE_SOURCE_IDENTITY_MATCHED";
            if (a) {
                row.coinranking_price_usd = a->price_usd;
                row.coinranking_market_cap_usd = a->market_cap_usd;
                row.coinranking_volume_24h_usd = a->volume_24h_usd;
            }
            if (b) {
                row.coinpaprika_price_usd = b->price_usd;
                row.coinpaprika_market_cap_usd = b->market_cap_usd;
                row.coinpaprika_volume_24h_usd = b->volume_24h_usd;
            }
        }
        output.push_back(std::move(row));
    }
    return output;
}

inline json snapshot_health_to_json(const ProviderSnapshot& snapshot) {
    return {
        {"provider_id", snapshot.provider_id},
        {"status", snapshot.status},
        {"license_status", snapshot.license_status},
        {"retrieved_at_utc", snapshot.retrieved_at_utc},
        {"http_status", snapshot.http_status},
        {"error", snapshot.error},
        {"endpoint_used", snapshot.endpoint_used},
        {"freshness_status", snapshot.freshness_status},
        {"request_attempts", snapshot.request_attempts},
        {"ticker_count", snapshot.tickers.size()}
    };
}

inline json snapshot_to_json(const ProviderSnapshot& snapshot) {
    json tickers = json::array();
    for (const auto& ticker : snapshot.tickers) {
        tickers.push_back({
            {"provider_id", ticker.provider_id}, {"provider_asset_id", ticker.provider_asset_id},
            {"symbol", ticker.symbol}, {"name", ticker.name},
            {"provider_timestamp_utc", ticker.provider_timestamp_utc},
            {"price_usd", ticker.price_usd}, {"market_cap_usd", ticker.market_cap_usd},
            {"volume_24h_usd", ticker.volume_24h_usd}, {"rank", ticker.rank}
        });
    }
    return {
        {"provider_id", snapshot.provider_id}, {"status", snapshot.status}, {"license_status", snapshot.license_status},
        {"retrieved_at_utc", snapshot.retrieved_at_utc}, {"http_status", snapshot.http_status},
        {"error", snapshot.error}, {"endpoint_used", snapshot.endpoint_used},
        {"freshness_status", snapshot.freshness_status},
        {"request_attempts", snapshot.request_attempts}, {"ticker_count", tickers.size()}, {"tickers", tickers}
    };
}

inline json collect_market_wide_provider_federation() {
    auto cmc = fetch_coinmarketcap();
    ProviderSnapshot gecko{
        "coingecko", "DISABLED_BY_JURISDICTION_POLICY", utc_now_iso(),
        0, "excluded_country_policy_applies_to_IR", "disabled_without_request",
        "UNAVAILABLE", "EXCLUDED_COUNTRY_IR", 0, {}
    };
    auto ranking = fetch_coinranking();
    auto paprika = fetch_coinpaprika();

    const auto& identities = candidate_identity_seed();
    const auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    evaluate_snapshot_freshness(cmc, identities, now_ms, 15LL * 60LL * 1000LL);
    evaluate_snapshot_freshness(ranking, identities, now_ms, 15LL * 60LL * 1000LL);
    evaluate_snapshot_freshness(paprika, identities, now_ms, 15LL * 60LL * 1000LL);

    const bool cmc_eligible = cmc.freshness_status == "FRESH" &&
        cmc.license_status == "PERSONAL_FREE_BASIC_API_KEY";
    const bool ranking_eligible = ranking.freshness_status == "FRESH" &&
        ranking.license_status == "PERSONAL_INTERNAL_USE_FREE_PLAN";
    const bool paprika_eligible = paprika.freshness_status == "FRESH" &&
        paprika.license_status == "PERSONAL_USE_ONLY";
    const auto cmc_ranking = compare_cmc_coinranking_references(cmc, ranking);
    const auto cmc_paprika = compare_cmc_coinpaprika_references(cmc, paprika);
    const auto ranking_paprika = compare_coinranking_coinpaprika_references(ranking, paprika);

    json candidate_rows = json::array();
    bool btc_two_source_match = false;
    std::size_t matched_asset_count = 0U;
    for (std::size_t i = 0; i < identities.size(); ++i) {
        const auto& cr = cmc_ranking[i];
        const auto& cp = cmc_paprika[i];
        const auto& rp = ranking_paprika[i];
        const bool cr_match = cmc_eligible && ranking_eligible &&
            cr.classification == "TWO_SOURCE_IDENTITY_MATCHED";
        const bool cp_match = cmc_eligible && paprika_eligible &&
            cp.classification == "TWO_SOURCE_IDENTITY_MATCHED";
        const bool rp_match = ranking_eligible && paprika_eligible &&
            rp.classification == "TWO_SOURCE_IDENTITY_MATCHED";

        std::string classification = "UNAVAILABLE";
        std::string pair = "NONE";
        if (cr_match || cp_match || rp_match) {
            classification = "TWO_SOURCE_IDENTITY_MATCHED";
            double best_difference = std::numeric_limits<double>::max();
            const auto consider = [&](bool matched, const CrossProviderReference& row,
                                      const std::string& pair_name) {
                if (matched && row.price_difference_bps < best_difference) {
                    best_difference = row.price_difference_bps;
                    pair = pair_name;
                }
            };
            consider(cr_match, cr, "coinmarketcap+coinranking");
            consider(cp_match, cp, "coinmarketcap+coinpaprika");
            consider(rp_match, rp, "coinranking+coinpaprika");
            ++matched_asset_count;
        } else {
            const auto* cmc_ticker = find_by_provider_id(cmc, identities[i].coinmarketcap_id);
            const auto* ranking_ticker = find_by_external_id(ranking, identities[i].coinmarketcap_id);
            const auto* paprika_ticker = find_by_provider_id(paprika, identities[i].coinpaprika_id);
            if ((cmc_eligible && cmc_ticker) || (ranking_eligible && ranking_ticker) ||
                (paprika_eligible && paprika_ticker)) {
                classification = "ONE_SOURCE_IDENTITY_MATCHED";
            }
        }
        if (identities[i].canonical_symbol == "BTC" &&
            classification == "TWO_SOURCE_IDENTITY_MATCHED") btc_two_source_match = true;
        candidate_rows.push_back({
            {"canonical_asset_id", identities[i].canonical_asset_id},
            {"canonical_symbol", identities[i].canonical_symbol},
            {"classification", classification},
            {"matched_provider_pair", pair}
        });
    }
    const int live_provider_count =
        (cmc.status == "LIVE_RESPONSE_PARSED" ? 1 : 0) +
        (ranking.status == "LIVE_RESPONSE_PARSED" ? 1 : 0) +
        (paprika.status == "LIVE_RESPONSE_PARSED" ? 1 : 0);
    const int eligible_fresh_provider_count =
        (cmc_eligible ? 1 : 0) + (ranking_eligible ? 1 : 0) + (paprika_eligible ? 1 : 0);
    const bool pass = eligible_fresh_provider_count >= 2 &&
        btc_two_source_match && matched_asset_count == identities.size();
    const char* universe_source_value = std::getenv("CFSS_UNIVERSE_SOURCE");
    const bool frozen_production_universe = universe_source_value &&
        std::string_view{universe_source_value} == "config/universe.json";

    return {
        {"schema_version", "1.0.0"},
        {"status", pass
            ? "TWO_FRESH_LICENSE_ELIGIBLE_PROVIDERS_FULL_NINE_ASSET_MATCH"
            : "PROVIDER_DISCOVERY_PARTIAL"},
        {"generated_at_utc", utc_now_iso()},
        {"production_universe_status", frozen_production_universe
            ? "PRODUCTION_UNIVERSE_FROZEN" : "DISCOVERY_ONLY_NOT_FROZEN"},
        {"live_provider_count", live_provider_count},
        {"production_eligible_fresh_provider_count", eligible_fresh_provider_count},
        {"matched_asset_count", matched_asset_count},
        {"required_asset_count", identities.size()},
        {"providers", json::array({
            snapshot_health_to_json(cmc),
            snapshot_health_to_json(gecko),
            snapshot_health_to_json(ranking),
            snapshot_health_to_json(paprika)
        })},
        {"candidate_seed", candidate_rows},
        {"attribution", "Market-wide reference data sources: CoinMarketCap, Coinranking and CoinPaprika. CoinGecko is disabled for this jurisdiction."},
        {"limitations", json::array({
            "CoinGecko is disabled: the published excluded-country list includes Iran; HTTP reachability does not override license restrictions.",
            "CoinMarketCap keyless access is evaluation-only. Production eligibility requires the free Basic API key and an eligible account.",
            "Coinranking free tier requires COINRANKING_API_KEY and internal-use compliance; account eligibility must be confirmed by key issuance.",
            "CoinPaprika free API is personal-use only; no raw ticker payload is redistributed.",
            "Provider account eligibility from the user's jurisdiction is not inferred from an HTTP response.",
            "Raw provider ticker payloads and absolute market metrics are not emitted to public workflow artifacts.",
            "Market-wide spot references are not perpetual contract prices.",
            "This reference federation does not provide futures OHLCV, funding, open interest or order-book depth.",
            "The nine-asset candidate seed is provisional and is not a frozen production universe.",
            "Provider overlap by itself is not evidence of executable liquidity or a trading edge."
        })}
    };
}

} // namespace cfss::federation
