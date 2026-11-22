#include "cfss/bitget_provider_probe.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(EXIT_FAILURE);
    }
}
}

int main() {
    using cfss::bitget::json;
    constexpr std::int64_t hour = cfss::bitget::kHourMs;
    const std::int64_t now = 1'800'000'000'000LL;
    const std::int64_t ts0 = (1'700'000'000'000LL / hour) * hour;

    const json valid_instrument = {
        {"symbol", "BTCUSDT"}, {"category", "USDT-FUTURES"},
        {"baseCoin", "BTC"}, {"quoteCoin", "USDT"},
        {"settleCoin", "USDT"}, {"instrumentType", "crypto"},
        {"symbolType", "crypto"}, {"status", "online"},
        {"type", "perpetual"}, {"launchTime", "1600000000000"},
        {"fundInterval", "8"}
    };
    require(cfss::bitget::valid_crypto_usdt_perpetual(valid_instrument, "BTCUSDT"),
            "valid online crypto USDT perpetual instrument is admitted");
    auto spot = valid_instrument;
    spot["category"] = "SPOT";
    require(!cfss::bitget::valid_crypto_usdt_perpetual(spot, "BTCUSDT"),
            "spot instrument is rejected");
    auto stock = valid_instrument;
    stock["instrumentType"] = "stock";
    require(!cfss::bitget::valid_crypto_usdt_perpetual(stock, "BTCUSDT"),
            "traditional-finance instrument is rejected");
    auto delivery = valid_instrument;
    delivery["type"] = "delivery";
    require(!cfss::bitget::valid_crypto_usdt_perpetual(delivery, "BTCUSDT"),
            "delivery contract is rejected");
    auto offline = valid_instrument;
    offline["status"] = "offline";
    require(!cfss::bitget::valid_crypto_usdt_perpetual(offline, "BTCUSDT"),
            "offline contract is rejected");
    require(cfss::bitget::valid_symbol("BTCUSDT") &&
            !cfss::bitget::valid_symbol("BTC-USDT-SWAP") &&
            !cfss::bitget::valid_symbol("BTC/USDT"),
            "Bitget symbols are constrained to the provider-native alphanumeric form");

    const json raw_candles = json::array({
        json::array({std::to_string(ts0), "100", "103", "99", "102", "2.5", "250"}),
        json::array({std::to_string(ts0 + hour), "102", "104", "101", "103", "3.0", "309"}),
        json::array({std::to_string(ts0 + hour), "102", "104", "101", "103", "3.1", "319"}),
        json::array({std::to_string(ts0 + 2 * hour), "103", "105", "102", "104", "1", "104"})
    });
    const auto candles = cfss::bitget::normalize_candles(raw_candles, "BTC", ts0 + 2 * hour);
    require(candles.size() == 2U, "duplicate and still-open candles are excluded");
    require(candles[0].at("volume_unit") == "BASE_COIN" &&
            candles[0].at("volume_base") == 2.5 &&
            candles[0].at("volume_quote") == 250.0,
            "Bitget base-coin volume is not mislabeled as contract volume");
    require(candles[1].at("timestamp_ms") == ts0 + hour &&
            candles[1].at("volume_base") == 3.1,
            "duplicate candle timestamps keep the last normalized record");

    const json raw_funding = json::array({
        {{"fundingRateTimestamp", std::to_string(ts0)}, {"fundingRate", "0.0001"}},
        {{"fundingRateTimestamp", std::to_string(ts0 + 8 * hour)}, {"fundingRate", "-0.0002"}},
        {{"fundingRateTimestamp", std::to_string(now + hour)}, {"fundingRate", "0.0003"}},
        {{"fundingRateTimestamp", std::to_string(ts0 + 16 * hour)}, {"fundingRate", "NaN"}}
    });
    const auto funding = cfss::bitget::normalize_funding(raw_funding, ts0, now);
    require(funding.size() == 2U &&
            funding[0].at("funding_rate_unit") == "fraction" &&
            std::abs(funding[1].at("funding_rate").get<double>() + 0.0002) < 1e-12,
            "funding timestamps, finite rates and fractional units are validated");

    const json raw_oi = json::array({
        {{"timestamp", std::to_string(ts0)}, {"openInterest", "1200"},
         {"openInterestValue", "120000000"}},
        {{"timestamp", std::to_string(ts0 + hour)}, {"openInterest", "1210"},
         {"openInterestValue", "121000000"}},
        {{"timestamp", std::to_string(ts0 + 2 * hour)}, {"openInterest", "0"},
         {"openInterestValue", "0"}}
    });
    const auto oi = cfss::bitget::normalize_open_interest(raw_oi, ts0, now);
    require(oi.size() == 2U &&
            oi[0].at("open_interest_base_unit") == "BASE_COIN" &&
            oi[0].at("open_interest_value_unit") == "USDT",
            "OI and quote value retain their distinct provider-native units");

    const auto candle_coverage = cfss::bitget::coverage(candles, "timestamp_ms", hour);
    require(candle_coverage.count == 2U &&
            candle_coverage.missing_intervals == 0U &&
            candle_coverage.days > 0.0,
            "coverage uses unique ordered timestamps");
    const json empty = json::array();
    require(cfss::bitget::coverage(empty, "timestamp_ms", hour).count == 0U,
            "empty history is unavailable, not a zero-valued observation");
    require(cfss::bitget::number(json{"0.01"}).value_or(0.0) == 0.01 &&
            !cfss::bitget::number(json{"NaN"}).has_value() &&
            !cfss::bitget::number(json{nullptr}).has_value(),
            "numeric parsing rejects NaN and null values");
    std::cout << "BITGET_PROVIDER_TESTS_PASS\n";
    return EXIT_SUCCESS;
}
