#include "cfss/nss_v2.hpp"

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
}

int main() {
    using nlohmann::json;
    constexpr std::int64_t hour = 3'600'000LL;
    constexpr std::int64_t count = 600;
    json instrument = {
        {"candles", json::array()},
        {"funding", json::array()},
        {"open_interest", json::array()}
    };
    json basis = {{"basis", json::array()}};

    for (std::int64_t i = 1; i <= count; ++i) {
        const auto ts = i * hour;
        const double wave = std::sin(static_cast<double>(i) / 13.0);
        const double close = 100.0 + 0.015 * static_cast<double>(i) + 0.4 * wave;
        instrument["candles"].push_back({
            {"timestamp_ms", ts}, {"close", close},
            {"high", close + 0.6}, {"low", close - 0.6},
            {"volume_quote", 1000.0 + 100.0 * std::sin(static_cast<double>(i) / 7.0)}
        });
        instrument["open_interest"].push_back({
            {"timestamp_ms", ts},
            {"open_interest_value_usd", 10000000.0 + 10000.0 * static_cast<double>(i) +
                50000.0 * std::sin(static_cast<double>(i) / 17.0)}
        });
        basis["basis"].push_back({
            {"timestamp_ms", ts},
            {"basis_bps", 2.0 + 0.01 * static_cast<double>(i) +
                1.2 * std::sin(static_cast<double>(i) / 19.0)}
        });
        if (i % 8 == 0) {
            instrument["funding"].push_back({
                {"timestamp_ms", ts},
                {"funding_rate", 0.0001 * std::sin(static_cast<double>(i) / 11.0)}
            });
        }
    }

    const auto decision = count * hour;
    const auto result = cfss::nss::calculate_v2(instrument, basis, decision);
    require(result[0].status == "CALCULATED" && result[1].status == "CALCULATED",
            "both directional NSS v2 scores calculate with sufficient history");
    require(result[0].data_class == "PROXY" && result[1].data_class == "PROXY",
            "v2 explicitly labels proxy transformations");
    require(result[0].score && result[1].score &&
            *result[0].score >= 0.0 && *result[0].score <= 1.0 &&
            *result[1].score >= 0.0 && *result[1].score <= 1.0,
            "both aggregate scores remain bounded");
    require(std::abs(*result[0].score -
                     *cfss::nss::weighted_score(result[0].components, decision)) < 1e-12,
            "canonical NSS weights are applied");
    require(std::abs(*result[0].components[4].score -
                     *result[1].components[4].score) < 1e-12,
            "pre-breakout compression is direction-independent");

    const auto repeated = cfss::nss::calculate_v2(instrument, basis, decision);
    require(std::abs(*result[0].score - *repeated[0].score) < 1e-12 &&
            std::abs(*result[1].score - *repeated[1].score) < 1e-12,
            "identical inputs are deterministic");

    auto future_instrument = instrument;
    future_instrument["candles"].push_back({
        {"timestamp_ms", (count + 1) * hour}, {"close", 9999.0},
        {"high", 10000.0}, {"low", 9998.0}, {"volume_quote", 1e12}
    });
    future_instrument["open_interest"].push_back({
        {"timestamp_ms", (count + 1) * hour}, {"open_interest_value_usd", 1e15}
    });
    future_instrument["funding"].push_back({
        {"timestamp_ms", (count + 1) * hour}, {"funding_rate", 0.5}
    });
    auto future_basis = basis;
    future_basis["basis"].push_back({
        {"timestamp_ms", (count + 1) * hour}, {"basis_bps", 50000.0}
    });
    const auto future_result = cfss::nss::calculate_v2(
        future_instrument, future_basis, decision);
    require(std::abs(*result[0].score - *future_result[0].score) < 1e-12 &&
            std::abs(*result[1].score - *future_result[1].score) < 1e-12,
            "future perturbations cannot alter earlier NSS scores");

    const auto no_basis = cfss::nss::calculate_v2(instrument, json::object(), decision);
    require(no_basis[0].status == "UNAVAILABLE" && no_basis[0].missing_count > 0U,
            "missing basis blocks the complete five-component aggregate");

    std::cout << "NSS_V2_PROXY_TESTS_PASS\n";
    return 0;
}
