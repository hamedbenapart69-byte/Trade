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
        cfss::meta::Outcome row{
            "signal-" + std::to_string(i),
            "PLAN_A_LRT",
            "DOWNTREND",
            static_cast<std::int64_t>(i + 1U) * 86'400'000LL,
            low_score_group ? 0.20 : 0.80,
            win,
            win ? win_r : 0.0,
            win ? 0.0 : loss_r,
            fee,
            slippage,
            funding,
            true, "PROXY", "DAILY_SWING", "HYPOTHESIS_PROXY", "NOT_EXECUTED",
            "scan-" + std::to_string(i), "SYMBOL-" + std::to_string(i), "LFS_V2_PROXY"
        };
        out.push_back(row);
    }
    return out;
}
}

int main() {
    const auto empty = cfss::meta::calibrate({}, "PLAN_A_LRT", "DOWNTREND", 0.7, 251LL * 86'400'000LL);
    require(empty.status == "NOT_CALIBRATED" && !empty.probability_win &&
            empty.ev_status == "NOT_CALCULATED",
            "empty outcome ledger never produces probability or EV");

    auto outcomes = fixture(2.0, 1.0, 0.04, 0.02, 0.01);
    const auto calibrated = cfss::meta::calibrate(
        outcomes, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
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
            calibrated.win_rate_ci_low && calibrated.win_rate_ci_high &&
            calibrated.win_rate_cluster_ci_low && calibrated.win_rate_cluster_ci_high,
            "Wilson and three-way clustered OOS confidence intervals are both reported");
    require(calibrated.oos_scan_clusters == 50U &&
            calibrated.oos_symbol_clusters == 50U &&
            calibrated.oos_utc_day_clusters == 50U &&
            calibrated.oos_symbol_distribution.size() == 50U &&
            calibrated.oos_daily_distribution.size() == 50U &&
            calibrated.oos_period_start_ms > 0 &&
            calibrated.oos_period_end_ms >= calibrated.oos_period_start_ms &&
            std::abs(calibrated.oos_effective_sample_size - 50.0) < 1e-9,
            "effective independent OOS sample size accounts for scan, symbol and UTC-day clusters");

    auto correlated = outcomes;
    for (std::size_t i = 0U; i < correlated.size(); ++i) {
        correlated[i].source_scan_id = "scan-block-" + std::to_string(i / 50U);
        correlated[i].symbol = "symbol-block-" + std::to_string(i / 50U);
    }
    const auto correlated_result = cfss::meta::calibrate(
        correlated, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(correlated_result.status == "NOT_CALIBRATED" &&
            correlated_result.reason ==
                "INSUFFICIENT_EFFECTIVE_OOS_SAMPLE_AFTER_SCAN_SYMBOL_AND_UTC_DAY_CLUSTERING",
            "large row count cannot hide a small independent clustered sample");

    require(calibrated.ev_status == "CALCULATED" &&
            calibrated.ev_net && *calibrated.ev_net > 0.0 &&
            calibrated.ev_decision == "EV_POSITIVE_RESEARCH_ONLY",
            "net EV uses calibrated probability and all three cost terms");

    auto future_extended = outcomes;
    future_extended.push_back({
        "signal-250", "PLAN_A_LRT", "DOWNTREND", 251LL * 86'400'000LL,
        0.80, false, 0.0, 1.0, 0.04, 0.02, 0.01,
        true, "PROXY", "DAILY_SWING", "HYPOTHESIS_PROXY", "NOT_EXECUTED",
        "scan-future", "SYMBOL-FUTURE", "LFS_V2_PROXY"
    });
    const auto with_future = cfss::meta::calibrate(
        future_extended, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(with_future.status == "CALIBRATED" &&
            std::abs(*with_future.probability_win - *calibrated.probability_win) < 1e-9,
            "future OOS outcomes do not change the fitted calibration probability");

    auto no_costs = fixture(2.0, 1.0, 0.0, 0.0, 0.0);
    for (auto& row : no_costs) row.costs_available = false;
    const auto calibrated_without_costs = cfss::meta::calibrate(
        no_costs, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(calibrated_without_costs.status == "CALIBRATED" &&
            calibrated_without_costs.ev_status == "COSTS_UNAVAILABLE" &&
            !calibrated_without_costs.ev_net &&
            calibrated_without_costs.ev_decision == "NOT_CALCULATED_COSTS_UNAVAILABLE",
            "probability calibration may pass while EV remains blocked without costs");

    auto other_data_class = outcomes;
    for (auto& row : other_data_class) row.data_class = "REAL";
    const auto isolated_data_class = cfss::meta::calibrate(
        other_data_class, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL, "PROXY");
    require(isolated_data_class.status == "NOT_CALIBRATED" &&
            isolated_data_class.sample_count == 0U,
            "REAL and PROXY outcomes are never pooled");

    auto scalp_outcomes = outcomes;
    for (auto& row : scalp_outcomes) row.profile = "INTRADAY_SCALP";
    const auto isolated_profile = cfss::meta::calibrate(
        scalp_outcomes, "PLAN_A_LRT", "DOWNTREND", 0.80,
        251LL * 86'400'000LL, "PROXY", "DAILY_SWING");
    require(isolated_profile.status == "NOT_CALIBRATED" &&
            isolated_profile.sample_count == 0U,
            "Daily and Scalp calibration samples are never pooled");

    auto executed_outcomes = outcomes;
    for (auto& row : executed_outcomes) row.execution_status = "EXECUTED";
    const auto isolated_execution = cfss::meta::calibrate(
        executed_outcomes, "PLAN_A_LRT", "DOWNTREND", 0.80,
        251LL * 86'400'000LL);
    require(isolated_execution.status == "NOT_CALIBRATED" &&
            isolated_execution.sample_count == 0U,
            "hypothesis proxy calibration never absorbs executed-trade outcomes");

    auto funding_credit = fixture(2.0, 1.0, 0.04, 0.02, -0.01);
    const auto credit_ev = cfss::meta::calibrate(
        funding_credit, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(credit_ev.status == "CALIBRATED" &&
            credit_ev.ev_status == "CALCULATED" &&
            credit_ev.avg_funding_r && *credit_ev.avg_funding_r < 0.0,
            "negative funding credit is preserved rather than clamped to a cost");

    auto negative = fixture(0.5, 2.0, 0.10, 0.05, 0.05);
    const auto negative_ev = cfss::meta::calibrate(
        negative, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(negative_ev.status == "CALIBRATED" &&
            negative_ev.ev_status == "CALCULATED" &&
            negative_ev.ev_net && *negative_ev.ev_net <= 0.0 &&
            negative_ev.ev_decision == "NO_TRADE",
            "calibrated non-positive net EV forces NO_TRADE");

    auto duplicate = outcomes;
    duplicate.push_back(outcomes.front());
    const auto duplicate_result = cfss::meta::calibrate(
        duplicate, "PLAN_A_LRT", "DOWNTREND", 0.80, 251LL * 86'400'000LL);
    require(duplicate_result.status == "INVALID_OUTCOME_LEDGER",
            "duplicate signal IDs invalidate the calibration ledger");

    auto wrong_score_version = outcomes;
    for (auto& row : wrong_score_version) row.score_model_version = "LFS_V1_FORMULA";
    const auto isolated_score_version = cfss::meta::calibrate(
        wrong_score_version, "PLAN_A_LRT", "DOWNTREND", 0.80,
        251LL * 86'400'000LL);
    require(isolated_score_version.status == "NOT_CALIBRATED" &&
            isolated_score_version.sample_count == 0U,
            "outcomes from a different score formula version are never pooled");

    const auto other_regime = cfss::meta::calibrate(
        outcomes, "PLAN_A_LRT", "UPTREND", 0.80, 251LL * 86'400'000LL);
    require(other_regime.status == "NOT_CALIBRATED" &&
            other_regime.sample_count == 0U,
            "calibration is isolated by path and regime");

    std::cout << "META_CALIBRATION_V1_TESTS_PASS\n";
    return 0;
}
