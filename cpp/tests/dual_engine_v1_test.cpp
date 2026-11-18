#include "cfss/dual_engines.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

nlohmann::json hourly_fixture(bool breakout, bool sweep) {
    using nlohmann::json;
    constexpr std::int64_t hour = 3'600'000LL;
    constexpr std::int64_t four_hours = 4LL * hour;
    json rows = json::array();
    for (std::int64_t i = 0; i < 22; ++i) {
        const double close = breakout && i == 21 ? 112.0 : 100.0 + 0.05 * static_cast<double>(i);
        double open = close - 0.2;
        double high = breakout && i == 21 ? 113.0 : 110.0;
        double low = 99.0;
        double volume = 1000.0;
        if (sweep && i == 21) {
            open = 100.2;
            high = 102.0;
            low = 98.0;
            volume = 2000.0;
        }
        if (breakout && i == 21) volume = 2000.0;
        const auto start = i * four_hours;
        for (std::int64_t k = 0; k < 4; ++k) {
            const double fraction = static_cast<double>(k + 1) / 4.0;
            const double hourly_close = open + (close - open) * fraction;
            const double hourly_open = k == 0 ? open :
                open + (close - open) * static_cast<double>(k) / 4.0;
            rows.push_back({
                {"timestamp_ms", start + k * hour},
                {"open", hourly_open}, {"high", high}, {"low", low},
                {"close", hourly_close}, {"volume_quote", volume / 4.0},
                {"closed", true}
            });
        }
    }
    return rows;
}

nlohmann::json instrument_fixture(bool breakout, bool sweep,
                                         double turnover = 20'000'000.0) {
    return {
        {"candles", hourly_fixture(breakout, sweep)},
        {"turnover_24h_usd", turnover},
        {"liquidity_threshold_usd", 10'000'000.0},
        {"liquidity_status", turnover > 10'000'000.0 ? "ELIGIBLE" : "BELOW_THRESHOLD_PINNED"}
    };
}

nlohmann::json lfs(double score) {
    return {
        {"status", "CALCULATED"}, {"score", score}, {"data_class", "PROXY"},
        {"component_coverage", {{"available_scores", 5}, {"required_scores", 5}}}
    };
}

nlohmann::json nss(double long_score, double short_score) {
    return {
        {"status", "CALCULATED"}, {"data_class", "PROXY"},
        {"nss_long", {
            {"status", "CALCULATED"}, {"score", long_score},
            {"component_coverage", {{"available_scores", 5}, {"required_scores", 5}}}
        }},
        {"nss_short", {
            {"status", "CALCULATED"}, {"score", short_score},
            {"component_coverage", {{"available_scores", 5}, {"required_scores", 5}}}
        }}
    };
}

nlohmann::json liquidity(const std::string& phase, bool demand_zone) {
    using nlohmann::json;
    json zones = json::array();
    if (demand_zone) {
        zones.push_back({
            {"side", "DEMAND"}, {"low", 99.0}, {"high", 100.0},
            {"status", "ACTIVE"}, {"confirmed_at_ms", 1}
        });
    }
    return {
        {"status", "AVAILABLE"}, {"phase", phase},
        {"zones", zones},
        {"nearest_support", {{"low", 99.0}, {"high", 100.0}}},
        {"nearest_resistance", {{"low", 110.0}, {"high", 112.0}}}
    };
}
}

int main() {
    const auto decision = 22LL * 4LL * 3'600'000LL;

    const auto lrt = cfss::engines::evaluate(
        "BTC/USDT:USDT",
        instrument_fixture(false, true),
        lfs(0.75), nss(0.60, 0.65), liquidity("RANGE", true), decision);
    require(lrt.lrt.status == "CANDIDATE" && lrt.lrt.direction == "LONG",
            "LRT independently recognizes a demand sweep and reclaim");
    require(lrt.nmt.status == "NO_QUALIFIED_SETUP",
            "NMT does not borrow the LRT sweep as its own trigger");
    require(lrt.lrt.score && std::abs(*lrt.lrt.score - 0.75) < 1e-12,
            "LRT reports its own LFS score");
    require(!lrt.lrt.actionable && lrt.lrt.confidence_status == "NOT_CALIBRATED",
            "Stage 5 candidates are never actionable or calibrated");

    const auto lrt_independent = cfss::engines::evaluate(
        "BTC/USDT:USDT",
        instrument_fixture(false, true),
        lfs(0.75), nss(0.10, 0.20), liquidity("RANGE", true), decision);
    require(lrt_independent.lrt.status == "CANDIDATE",
            "changing NSS below the veto threshold does not alter LRT logic");

    const auto nmt = cfss::engines::evaluate(
        "ETH/USDT:USDT",
        instrument_fixture(true, false),
        lfs(0.60), nss(0.75, 0.40), liquidity("UPTREND", false), decision);
    require(nmt.nmt.status == "CANDIDATE" && nmt.nmt.direction == "LONG",
            "NMT independently requires trend-aligned breakout, volume and directional NSS");
    require(nmt.lrt.status == "NO_QUALIFIED_SETUP",
            "LRT does not borrow the NMT breakout as a liquidity sweep");

    const auto nmt_independent = cfss::engines::evaluate(
        "ETH/USDT:USDT",
        instrument_fixture(true, false),
        lfs(0.10), nss(0.75, 0.40), liquidity("UPTREND", false), decision);
    require(nmt_independent.nmt.status == "CANDIDATE",
            "changing LFS below the veto threshold does not alter NMT logic");

    const auto veto = cfss::engines::evaluate(
        "BTC/USDT:USDT",
        instrument_fixture(true, true),
        lfs(0.71), nss(0.71, 0.40), liquidity("UPTREND", true), decision);
    require(veto.golden_rule_evaluated && veto.golden_rule_veto,
            "simultaneous strict scores above 0.70 trigger the Golden Rule");
    require(veto.lrt.status == "GOLDEN_RULE_NO_TRADE" &&
            veto.nmt.status == "GOLDEN_RULE_NO_TRADE",
            "Golden Rule veto blocks both independent engines");

    const auto exact_boundary = cfss::engines::evaluate(
        "BTC/USDT:USDT",
        {{"candles", hourly_fixture(false, true)}},
        lfs(0.70), nss(0.70, 0.40), liquidity("RANGE", true), decision);
    require(!exact_boundary.golden_rule_veto,
            "strict greater-than Golden Rule does not trigger at exactly 0.70");

    const auto missing = cfss::engines::evaluate(
        "BTC/USDT:USDT",
        {{"candles", hourly_fixture(false, true)}},
        {{"status", "UNAVAILABLE"}}, nss(0.8, 0.8), liquidity("RANGE", true), decision);
    require(!missing.golden_rule_evaluated &&
            missing.lrt.status == "INSUFFICIENT_DATA" &&
            missing.nmt.status == "INSUFFICIENT_DATA",
            "missing Golden Rule inputs block both engines rather than bypassing the veto");

    const auto below_liquidity = cfss::engines::evaluate(
        "LOW-LIQUIDITY/USDT:USDT",
        instrument_fixture(false, true, 9'999'999.0),
        lfs(0.90), nss(0.20, 0.10), liquidity("RANGE", true), decision);
    require(below_liquidity.lrt.status == "INSUFFICIENT_DATA" &&
            below_liquidity.nmt.status == "INSUFFICIENT_DATA" &&
            below_liquidity.lrt.reason == "CURRENT_LIQUIDITY_BELOW_CONFIGURED_THRESHOLD",
            "pinned resolution-only symbols cannot generate fresh LRT/NMT candidates below the liquidity gate");

    const auto exact_liquidity_boundary = cfss::engines::evaluate(
        "BOUNDARY/USDT:USDT",
        instrument_fixture(false, true, 10'000'000.0),
        lfs(0.90), nss(0.20, 0.10), liquidity("RANGE", true), decision);
    require(exact_liquidity_boundary.lrt.status == "INSUFFICIENT_DATA",
            "liquidity gate uses strict greater-than at the configured threshold");

    std::cout << "DUAL_ENGINE_V1_INDEPENDENCE_AND_VETO_TESTS_PASS\n";
    return 0;
}
