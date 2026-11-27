#include "cfss/okx_provider.hpp"

#include <cstdlib>
#include <iostream>
#include <set>
#include <string>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    const std::set<std::string> verified{"BTC", "ETH", "SOL", "DOGE"};
    require(cfss::okx::valid_crypto_symbol("BTC") &&
            cfss::okx::valid_crypto_symbol("1INCH") &&
            !cfss::okx::valid_crypto_symbol("ABC.DEF") &&
            !cfss::okx::valid_crypto_symbol("ABC-DEF") &&
            !cfss::okx::valid_crypto_symbol("ABCDEFGHIJKLMNOPQRSTU"),
            "universe symbols match the exact schema-safe uppercase alphanumeric contract");
    require(cfss::okx::is_verified_crypto_underlying("BTC", verified),
            "verified crypto base symbol is admitted");
    require(cfss::okx::is_verified_crypto_underlying("eth", verified),
            "crypto symbols are case-normalized");
    require(!cfss::okx::is_verified_crypto_underlying("SOXL", {"BTC", "SOXL"}),
            "known leveraged equity ETF is excluded even if symbol collides");
    require(!cfss::okx::is_verified_crypto_underlying("NVDA", {"BTC", "NVDA"}),
            "known equity underlying is excluded");
    require(!cfss::okx::is_verified_crypto_underlying("XAU", {"BTC", "XAU"}),
            "commodity underlying is excluded");
    require(!cfss::okx::is_verified_crypto_underlying("SNDK", verified),
            "unverified symbol is excluded from the crypto universe");
    const nlohmann::json old_rows = nlohmann::json::array({
        {{"timestamp_ms", 3'600'000}, {"close", 10.0}},
        {{"timestamp_ms", 7'200'000}, {"close", 11.0}}
    });
    const nlohmann::json recent_rows = nlohmann::json::array({
        {{"timestamp_ms", 7'200'000}, {"close", 12.0}},
        {{"timestamp_ms", 10'800'000}, {"close", 13.0}}
    });
    const auto merged = cfss::okx::merge_timestamp_rows(
        old_rows, recent_rows, 3'600'000, 10'800'001, 3'600'000);
    require(merged.size() == 3U && merged.at(1).at("close") == 12.0,
            "incremental cache merge deduplicates by timestamp and prefers fresh candles");
    require(merged.front().at("timestamp_ms") == 3'600'000 &&
            merged.back().at("timestamp_ms") == 10'800'000,
            "incremental cache preserves history and appends fresh closed bars");
    const cfss::okx::Instrument btc{"BTC-USDT-SWAP", "BTC", "USDT", "USDT", 1, 1, 0.1, 1, 1, 100, 1, "BTC", "okx", "BTC-USDT-SWAP"};
    const cfss::okx::Instrument eth{"ETH-USDT-SWAP", "ETH", "USDT", "USDT", 1, 1, 0.1, 1, 1, 90, 1, "ETH", "okx", "ETH-USDT-SWAP"};
    const cfss::okx::Instrument sol{"SOL-USDT-SWAP", "SOL", "USDT", "USDT", 1, 1, 0.1, 1, 1, 1, 1, "SOL", "okx", "SOL-USDT-SWAP"};
    const auto pinned = cfss::okx::select_instruments(
        1, {eth, btc}, {btc, eth, sol}, {"SOL"});
    require(pinned.size() == 3U && pinned.front().base == "BTC" &&
            pinned.back().base == "SOL",
            "pending candidates remain in L1 even after falling outside top-turnover eligibility");
    const cfss::okx::Instrument sol_liquid{"SOL-USDT-SWAP", "SOL", "USDT", "USDT", 1, 1, 0.1, 1, 1, 20, 1, "SOL", "okx", "SOL-USDT-SWAP"};
    const auto exact_nine = cfss::okx::select_instruments(
        2, {btc, eth, sol_liquid}, {btc, eth, sol_liquid}, {"ETH", "SOL"}, true);
    require(exact_nine.size() == 3U &&
            std::set<std::string>{exact_nine[0].base, exact_nine[1].base, exact_nine[2].base} ==
                std::set<std::string>{"BTC", "ETH", "SOL"},
            "exact-universe mode returns only BTC plus the complete requested candidate set");
    bool exact_missing_rejected = false;
    try {
        (void)cfss::okx::select_instruments(
            2, {btc, eth}, {btc, eth, sol_liquid}, {"ETH", "SOL"}, true);
    } catch (const std::runtime_error&) {
        exact_missing_rejected = true;
    }
    require(exact_missing_rejected,
            "exact-universe mode rejects a candidate that fails liquidity or provider availability");
    const nlohmann::json old_cache = {
        {"schema_version", "1.0.0"},
        {"provider", {{"primary_provider_id", "okx"}}},
        {"instruments", nlohmann::json::array({
            {{"instrument_id", "BTC-USDT-SWAP"}, {"candles", nlohmann::json::array({1, 2})}},
            {{"instrument_id", "ETH-USDT-SWAP"}, {"candles", nlohmann::json::array({3, 4})}}
        })}
    };
    const nlohmann::json refreshed = nlohmann::json::array({
        {{"instrument_id", "ETH-USDT-SWAP"}, {"candles", nlohmann::json::array({5, 6})}},
        {{"instrument_id", "SOL-USDT-SWAP"}, {"candles", nlohmann::json::array({7, 8})}}
    });
    const auto checkpoint = cfss::okx::make_market_cache_snapshot(old_cache, refreshed, 1000, 2000);
    require(checkpoint.at("instruments").size() == 3U &&
            checkpoint.at("instruments").at(1).at("instrument_id") == "ETH-USDT-SWAP" &&
            checkpoint.at("instruments").at(1).at("candles").at(0) == 5 &&
            checkpoint.at("cache_entries").contains("ETH-USDT-SWAP") &&
            cfss::okx::valid_cache_entry(checkpoint.at("cache_entries"),
                checkpoint.at("instruments").at(1), "ETH-USDT-SWAP", 1000, 2000),
            "partial checkpoints preserve data and attach a verifiable provider/venue/market/timeframe/window cache key");
    auto tampered_data = checkpoint.at("instruments").at(1);
    tampered_data["candles"][0] = 999;
    require(!cfss::okx::valid_cache_entry(checkpoint.at("cache_entries"),
                tampered_data, "ETH-USDT-SWAP", 1000, 2000),
            "modified cached data is rejected by the data revision hash");
    auto tampered_metadata = checkpoint.at("cache_entries");
    tampered_metadata["ETH-USDT-SWAP"]["venue"] = "OTHER";
    require(!cfss::okx::valid_cache_entry(tampered_metadata,
                checkpoint.at("instruments").at(1), "ETH-USDT-SWAP", 1000, 2000),
            "cache entries with a mismatched venue are rejected");
    require(cfss::okx::retryable_http_failure(CURLE_OPERATION_TIMEDOUT, 0L) &&
            cfss::okx::retryable_http_failure(CURLE_OK, 429L) &&
            cfss::okx::retryable_http_failure(CURLE_OK, 503L) &&
            !cfss::okx::retryable_http_failure(CURLE_OK, 400L) &&
            !cfss::okx::retryable_http_failure(CURLE_OK, 404L),
            "provider retries are limited to transport, timeout, rate-limit and server failures");
    require(cfss::okx::retryable_okx_error_code("50011") &&
            cfss::okx::retryable_okx_error_code("50013") &&
            !cfss::okx::retryable_okx_error_code("51001"),
            "invalid instrument and parameter errors are not retried");
    require(cfss::okx::retry_delay("https://www.okx.com/api", 1) >
            cfss::okx::retry_delay("https://www.okx.com/api", 0),
            "retry backoff grows exponentially with bounded deterministic jitter");
    std::cout << "CRYPTO_UNIVERSE_TESTS_PASS\n";
    return 0;
}
