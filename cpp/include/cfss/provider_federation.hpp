#pragma once

#include "cfss/provider_resilience.hpp"

#include <curl/curl.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <cstdio>
#include <utility>
#include <optional>
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

inline HttpResult http_get(std::string_view url, long timeout_seconds = 20L, int max_attempts = 3) {
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
        curl_easy_setopt(handle, CURLOPT_HTTPHEADER, headers);
        result.transport = curl_easy_perform(handle);
        curl_slist_free_all(headers);
        if (result.transport == CURLE_OK) curl_easy_getinfo(handle, CURLINFO_RESPONSE_CODE, &result.status);
        curl_easy_cleanup(handle);
        last = result;
        const bool success = result.transport == CURLE_OK && result.status == 200L;
        const bool retryable = result.transport != CURLE_OK || result.status == 408L ||
            result.status == 429L || (result.status >= 500L && result.status <= 599L);
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
        if (!row.is_object() || !row.contains("quote")) return;
        const json* usd_pointer = nullptr;
        const auto& quote = row.at("quote");
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
            row.value("cmc_rank", std::int64_t{0})
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
            row.value("rank", std::int64_t{0})
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

    auto response = http_get(
        "https://pro-api.coinmarketcap.com/public-api/v3/cryptocurrency/listings/latest?start=1&limit=100&convert=USD");
    snapshot.endpoint_used = "listings_latest";
    snapshot.request_attempts = response.attempts;
    if (response.transport != CURLE_OK || response.status != 200L) {
        const auto fallback = http_get(
            "https://pro-api.coinmarketcap.com/public-api/v3/cryptocurrency/quotes/latest?symbol=BTC,ETH,SOL,BNB,XRP,DOGE,ADA,LINK,AVAX&convert=USD");
        snapshot.request_attempts += fallback.attempts;
        if (fallback.transport == CURLE_OK && fallback.status == 200L) {
            response = fallback;
            snapshot.endpoint_used = "quotes_latest_fallback";
            snapshot.error = "listings_latest_failed_quotes_latest_fallback_used";
        } else {
            snapshot.http_status = fallback.status;
            breaker.record_failure();
            snapshot.status = fallback.status == 403L ? "PROVIDER_BLOCKED" :
                (fallback.status == 429L ? "PROVIDER_RATE_LIMITED" : "UNAVAILABLE");
            snapshot.error = std::string{"coinmarketcap_endpoints_failed:listings="} +
                std::to_string(response.status) + ",quotes=" + std::to_string(fallback.status);
            return snapshot;
        }
    }

    snapshot.http_status = response.status;
    try {
        const auto payload = json::parse(response.body);
        snapshot.tickers = parse_coinmarketcap(payload);
        snapshot.status = snapshot.tickers.empty() ? "FAILED" : "LIVE_RESPONSE_PARSED";
        snapshot.freshness_status = "NOT_TESTED";
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
            row.value("market_cap_rank", std::int64_t{0})
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

inline const MarketTicker* find_by_provider_id(const ProviderSnapshot& snapshot,
                                                std::string_view provider_asset_id) {
    const auto found = std::find_if(snapshot.tickers.begin(), snapshot.tickers.end(),
        [&](const MarketTicker& ticker) { return ticker.provider_asset_id == provider_asset_id; });
    return found == snapshot.tickers.end() ? nullptr : &*found;
}

struct CrossProviderReference {
    std::string canonical_asset_id;
    std::string canonical_symbol;
    std::string classification{"UNAVAILABLE"};
    double coinmarketcap_price_usd{0.0};
    double coingecko_price_usd{0.0};
    double coinpaprika_price_usd{0.0};
    double price_difference_bps{0.0};
    double coinmarketcap_market_cap_usd{0.0};
    double coingecko_market_cap_usd{0.0};
    double coinpaprika_market_cap_usd{0.0};
    double coinmarketcap_volume_24h_usd{0.0};
    double coingecko_volume_24h_usd{0.0};
    double coinpaprika_volume_24h_usd{0.0};
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

} // namespace cfss::federation
