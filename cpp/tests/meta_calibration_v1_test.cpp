#include "cfss/meta_calibration.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

std::vector<cfss::meta::Outcome> fixture(double win_r, double loss_r,
                                          double fee, double slippage, double funding) {
    std::vector<cfss::meta::Outcome> out;
    out.reserve(250U);
    for (std::size_t i = 0U; i < 250U; ++i) {
        const bool low_score_group = i < 125U;
        const bool win = (i % 5U) < (low_score_group ? 2U : 3U);
        out.push_back({
            "signal-" + std::to_string(i),
            "PLAN_A_LRT",
            "DOWNTREND",
            static_cast<std::int64_t>(i + 1U) * 60'000LL,
            low_score_group ? 0.20 : 0.80,
            win,
            win ? win_r : 0.0,
            win ? 0.0 : loss_r,
            fee,
            slippage,
            funding
        });
    }
    return out;
}
}

int main() {
    const auto empty = cfss::meta::calibrate({}, "PLAN_A_LRT", "DOWNTREND", 0.7);
    require(empty.status == "NOT_CALIBRATED" && !empty.probability_win &&
            empty.ev_status == "NOT_CALCULATED",
            "empty outcome ledger never produces probability or EV");

    auto outcomes = fixture(2.0, 1.0, 0.04, 0.02, 0.01);
    const auto calibrated = cfss::meta::calibrate(
        outcomes, "PLAN_A_LRT", "DOWNTREND", 0.80);
    require(calibrated.status == "CALIBRATED",
            "chronological Platt/isotonic calibration improves held-out Brier");
    require(calibrated.train_count == 150U &&
            calibrated.validation_count == 50U &&
            calibrated.oos_count == 50U,
            "chronological 60/20/20 split is preserved");
    require(calibrated.probability_win.has_value() &&
            *calibrated.probability_win > 0.0 && *calibrated.probability_win < 1.0,
            "calibrated confidence is bounded");
    require(calibrated.brier_raw_oos && calibrated.brier_calibrated_oos &&
            *calibrated.brier_calibrated_oos < *calibrated.brier_raw_oos,
            "held-out Brier improves over raw score baseline");
    require(calibrated.brier_ci_low && calibrated.brier_ci_high &&
            calibrated.win_rate_ci_low && calibrated.win_rate_ci_high,
            "OOS confidence intervals are reported");
    require(calibrated.ev_status == "CALCULATED" &&
            calibrated.ev_net && *calibrated.ev_net > 0.0 &&
            calibrated.ev_decision == "EV_POSITIVE_RESEARCH_ONLY",
            "net EV uses calibrated probability and all three cost terms");

    auto future_extended = outcomes;
    future_extended.push_back({
        "signal-250", "PLAN_A_LRT", "DOWNTREND", 251LL * 60'000LL,
        0.80, false, 0.0, 1.0, 0.04, 0.02, 0.01
    });
    const auto with_future = cfss::meta::calibrate(
        future_extended, "PLAN_A_LRT", "DOWNTREND", 0.80);
    require(with_future.status == "CALIBRATED" &&
            std::abs(*with_future.probability_win - *calibrated.probability_win) < 1e-9,
            "future OOS outcomes do not change the fitted calibration probability");

    auto negative = fixture(0.5, 2.0, 0.10, 0.05, 0.05);
    const auto negative_ev = cfss::meta::calibrate(
        negative, "PLAN_A_LRT", "DOWNTREND", 0.80);
    require(negative_ev.status == "CALIBRATED" &&
            negative_ev.ev_status == "CALCULATED" &&
            negative_ev.ev_net && *negative_ev.ev_net <= 0.0 &&
            negative_ev.ev_decision == "NO_TRADE",
            "calibrated non-positive net EV forces NO_TRADE");

    auto duplicate = outcomes;
    duplicate.push_back(outcomes.front());
    const auto duplicate_result = cfss::meta::calibrate(
        duplicate, "PLAN_A_LRT", "DOWNTREND", 0.80);
    require(duplicate_result.status == "INVALID_OUTCOME_LEDGER",
            "duplicate signal IDs invalidate the calibration ledger");

    const auto other_regime = cfss::meta::calibrate(
        outcomes, "PLAN_A_LRT", "UPTREND", 0.80);
    require(other_regime.status == "NOT_CALIBRATED" &&
            other_regime.sample_count == 0U,
            "calibration is isolated by path and regime");

    std::cout << "META_CALIBRATION_V1_TESTS_PASS\n";
    return 0;
}
