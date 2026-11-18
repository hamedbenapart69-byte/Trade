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
    std::cout << "CRYPTO_UNIVERSE_TESTS_PASS\n";
    return 0;
}
