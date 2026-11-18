#include "cfss/liquidity_phase.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

nlohmann::json make_hourly(std::size_t count) {
    using nlohmann::json;
    constexpr std::int64_t four_hours = 4LL * 3'600'000LL;
    constexpr std::int64_t hour = 3'600'000LL;
    json rows = json::array();
    for (std::size_t i = 0U; i < count; ++i) {
        const double x = static_cast<double>(i);
        const double close = 100.0 + 0.025 * x + 5.0 * std::sin(x * 0.12);
        double open = close - 0.2;
        double high = close + 0.5;
        double low = close - 0.5;
        double volume = 1000.0;
        if (i == 220U || i == 167U || i == 114U || i == 61U) {
            high = close + 2.5;
            open = close - 0.2;
            volume = 2500.0;
        }
        if (i == 246U || i == 193U || i == 140U || i == 87U || i == 34U) {
            low = close - 2.5;
            open = close + 0.2;
            volume = 2500.0;
        }
        const auto start = static_cast<std::int64_t>(i) * four_hours;
        for (std::int64_t k = 0; k < 4; ++k) {
            const double fraction = static_cast<double>(k + 1) / 4.0;
            const double hourly_close = open + (close - open) * fraction;
            const double hourly_open = k == 0 ? open :
                open + (close - open) * static_cast<double>(k) / 4.0;
            rows.push_back({
                {"timestamp_ms", start + k * hour},
                {"open", hourly_open},
                {"high", high},
                {"low", low},
                {"close", hourly_close},
                {"volume_quote", volume / 4.0}
            });
        }
    }
    return rows;
}
}

int main() {
    constexpr std::int64_t four_hours = 4LL * 3'600'000LL;
    constexpr std::size_t bar_count = 260U;
    auto hourly = make_hourly(bar_count);
    const auto decision = static_cast<std::int64_t>(bar_count) * four_hours;

    const auto result = cfss::liquidity::calculate("BTC/USDT:USDT", hourly, decision);
    require(result.status == "AVAILABLE", "sufficient closed hourly data produces an output");
    require(result.phase != "UNAVAILABLE", "phase classifier has sufficient confirmed structure");
    require(!result.zones.empty(), "confirmed wick and volume pivots produce zones");

    for (const auto& zone : result.zones) {
        require(zone.confirmed_at_ms > zone.pivot_time_ms,
                "zone confirmation occurs after its pivot");
        require(zone.confirmed_at_ms <= decision,
                "no unconfirmed zone is emitted");
        require(zone.low < zone.high, "zone bounds are strictly ordered");
        require(zone.wick_ratio >= 0.35 && zone.volume_ratio >= 1.20,
                "both registered v1 confluence filters are satisfied");
    }

    const auto repeated = cfss::liquidity::calculate("BTC/USDT:USDT", hourly, decision);
    require(cfss::liquidity::to_json(result).dump() ==
            cfss::liquidity::to_json(repeated).dump(),
            "identical inputs produce byte-stable JSON output");

    auto future = hourly;
    const auto future_start = static_cast<std::int64_t>(bar_count) * four_hours;
    for (std::int64_t k = 0; k < 4; ++k) {
        future.push_back({
            {"timestamp_ms", future_start + k * 3'600'000LL},
            {"open", 9000.0}, {"high", 10000.0}, {"low", 8000.0},
            {"close", 9500.0}, {"volume_quote", 1e12}
        });
    }
    const auto future_perturbed = cfss::liquidity::calculate(
        "BTC/USDT:USDT", future, decision);
    require(cfss::liquidity::to_json(result).dump() ==
            cfss::liquidity::to_json(future_perturbed).dump(),
            "future bars cannot repaint an earlier as-of result");

    const auto pivot_time = 220LL * four_hours;
    const auto confirm_time = 223LL * four_hours;
    const auto before_confirmation = cfss::liquidity::calculate(
        "BTC/USDT:USDT", hourly, confirm_time - 1LL);
    const auto at_confirmation = cfss::liquidity::calculate(
        "BTC/USDT:USDT", hourly, confirm_time);
    const std::string pivot_id = "BTC/USDT:USDT|4H|SUPPLY|" + std::to_string(pivot_time);
    bool present_before = false;
    bool present_after = false;
    for (const auto& zone : before_confirmation.zones)
        if (zone.id == pivot_id) present_before = true;
    for (const auto& zone : at_confirmation.zones)
        if (zone.id == pivot_id) present_after = true;
    require(!present_before && present_after,
            "a pivot is published only after the two right-hand bars close");

    auto invalidation_input = hourly;
    const auto invalidation_start = static_cast<std::int64_t>(bar_count) * four_hours;
    for (std::int64_t k = 0; k < 4; ++k) {
        invalidation_input.push_back({
            {"timestamp_ms", invalidation_start + k * 3'600'000LL},
            {"open", 2000.0}, {"high", 2200.0}, {"low", 1990.0},
            {"close", 2100.0}, {"volume_quote", 1000.0}
        });
    }
    const auto invalidated = cfss::liquidity::calculate(
        "BTC/USDT:USDT", invalidation_input,
        static_cast<std::int64_t>(bar_count + 1U) * four_hours);
    bool invalidation_seen = false;
    for (const auto& zone : invalidated.zones)
        if (zone.id == pivot_id && zone.status == "INVALIDATED" &&
            zone.invalidated_at_ms > zone.confirmed_at_ms) invalidation_seen = true;
    require(invalidation_seen,
            "invalidation is recorded only after a post-confirmation close beyond the buffer");

    auto incomplete = hourly;
    incomplete.erase(incomplete.end() - 2, incomplete.end());
    const auto bars_full = cfss::liquidity::aggregate_4h(hourly, decision);
    const auto bars_incomplete = cfss::liquidity::aggregate_4h(incomplete, decision);
    require(bars_incomplete.size() == bars_full.size() - 1U,
            "incomplete four-hour candles are excluded");

    std::cout << "LIQUIDITY_PHASE_V1_CAUSAL_TESTS_PASS\n";
    return 0;
}
