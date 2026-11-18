#include "cfss/lfs_v2.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
using json = nlohmann::json;

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

json candles(std::size_t count) {
    json rows = json::array();
    for (std::size_t i = 0; i < count; ++i) {
        const double base = 100.0 + static_cast<double>(i) * 0.01 + std::sin(static_cast<double>(i) / 11.0);
        rows.push_back({
            {"timestamp_ms", static_cast<std::int64_t>(i + 1U) * 3'600'000LL},
            {"open", base}, {"high", base + 1.0 + static_cast<double>(i % 7U) * 0.01},
            {"low", base - 1.0}, {"close", base + 0.2},
            {"volume", 1000.0 + static_cast<double>((i * 17U) % 300U)}
        });
    }
    return rows;
}

json funding_rows(std::size_t count) {
    json rows = json::array();
    for (std::size_t i = 0; i < count; ++i) {
        rows.push_back({
            {"timestamp_ms", static_cast<std::int64_t>(i + 1U) * 28'800'000LL},
            {"funding_rate", (static_cast<double>(i % 13U) - 6.0) * 0.0001}
        });
    }
    return rows;
}

json ratio_rows(std::size_t count) {
    json rows = json::array();
    for (std::size_t i = 0; i < count; ++i) {
        rows.push_back({
            {"timestamp_ms", static_cast<std::int64_t>(i + 1U) * 3'600'000LL},
            {"ratio", 0.8 + static_cast<double>(i % 19U) * 0.025}
        });
    }
    return rows;
}

json oi_rows(std::size_t count) {
    json rows = json::array();
    for (std::size_t i = 0; i < count; ++i) {
        rows.push_back({
            {"timestamp_ms", static_cast<std::int64_t>(i + 1U) * 3'600'000LL},
            {"open_interest_value_usd", 1000000.0 + static_cast<double>(i) * 123.0 +
                                         static_cast<double>(i % 9U) * 500.0}
        });
    }
    return rows;
}
}

int main() {
    const auto c = candles(2200U);
    const auto f = funding_rows(100U);
    const auto l = ratio_rows(100U);
    const auto oi = oi_rows(720U);

    const auto decision_time = 2200LL * 3'600'000LL;
    auto future_candles = c;
    future_candles.push_back({
        {"timestamp_ms", decision_time + 3'600'000LL},
        {"open", 100.0}, {"high", 102.0}, {"low", 99.0}, {"close", 101.0}, {"volume", 5000.0}
    });
    const auto filtered_base = cfss::lfs::filter_time_series(c, decision_time);
    const auto filtered_future = cfss::lfs::filter_time_series(future_candles, decision_time);
    require(filtered_base == filtered_future, "future candle perturbations are excluded at decision time");

    const auto s1 = cfss::lfs::lfs1_proxy_score(c);
    const auto s2 = cfss::lfs::funding_extreme_score(f);
    const auto s3 = cfss::lfs::long_short_extreme_score(l);
    const auto s4 = cfss::lfs::bb_width_compression_score(c);
    const auto s5 = cfss::lfs::oi_change_score(oi);
    require(s1 && s2 && s3 && s4 && s5, "all v2 components calculate with sufficient history");
    for (const auto* score : {&s1, &s2, &s3, &s4, &s5}) {
        require(**score >= 0.0 && **score <= 1.0, "every component remains in [0,1]");
    }

    const std::array<cfss::lfs::V2Component, 5> components{{
        {"LFS1_BOOK_THINNESS", s1, "PROXY", 2200LL * 3'600'000LL, "lfs1_v2", "OHLCV proxy"},
        {"LFS2_FUNDING_EXTREME", s2, "REAL", 100LL * 28'800'000LL, "lfs2_v2", "REAL funding"},
        {"LFS3_LONG_SHORT_POSITIONING", s3, "REAL", 100LL * 3'600'000LL, "lfs3_v2", "REAL long-short"},
        {"LFS4_VOLATILITY_COMPRESSION", s4, "REAL", 2200LL * 3'600'000LL, "lfs4_v2", "REAL OHLCV"},
        {"LFS5_OPEN_INTEREST_CHANGE", s5, "REAL", 720LL * 3'600'000LL, "lfs5_v2", "REAL OI"}
    }};
    const auto result = cfss::lfs::aggregate_v2(components, 3000LL * 3'600'000LL);
    require(result.status == "CALCULATED" && result.score.has_value(), "complete v2 aggregate calculates");
    require(*result.score >= 0.0 && *result.score <= 1.0, "aggregate remains in [0,1]");
    require(result.data_class == "PROXY", "any proxy component marks aggregate PROXY");

    auto missing = components;
    missing[2].score.reset();
    require(cfss::lfs::aggregate_v2(missing, 3000LL * 3'600'000LL).status == "UNAVAILABLE",
            "missing component blocks aggregate");

    auto future = components;
    future[3].available_at_ms = 4000LL * 3'600'000LL;
    require(cfss::lfs::aggregate_v2(future, 3000LL * 3'600'000LL).status == "UNAVAILABLE",
            "future component is rejected");

    std::cout << "LFS_V2_PROXY_TESTS_PASS\n";
    return 0;
}
