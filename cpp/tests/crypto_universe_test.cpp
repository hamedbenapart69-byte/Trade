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
    const cfss::okx::Instrument btc{"BTC-USDT-SWAP", "BTC", "USDT", "USDT", 1, 1, 0.1, 1, 1, 100, 1, "BTC"};
    const cfss::okx::Instrument eth{"ETH-USDT-SWAP", "ETH", "USDT", "USDT", 1, 1, 0.1, 1, 1, 90, 1, "ETH"};
    const cfss::okx::Instrument sol{"SOL-USDT-SWAP", "SOL", "USDT", "USDT", 1, 1, 0.1, 1, 1, 1, 1, "SOL"};
    const auto pinned = cfss::okx::select_instruments(
        1, {eth, btc}, {btc, eth, sol}, {"SOL"});
    require(pinned.size() == 3U && pinned.front().base == "BTC" &&
            pinned.back().base == "SOL",
            "pending candidates remain in L1 even after falling outside top-turnover eligibility");
    std::cout << "CRYPTO_UNIVERSE_TESTS_PASS\n";
    return 0;
}
