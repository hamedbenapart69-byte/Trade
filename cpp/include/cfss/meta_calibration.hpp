#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace cfss::meta {

struct Outcome {
    std::string signal_id;
    std::string path;
    std::string regime;
    std::int64_t closed_at_ms{};
    double raw_score{};
    bool win{};
    double win_r{};
    double loss_r{};
    double fee_r{};
    double slippage_r{};
    double funding_r{};
    bool costs_available{true};
    std::string data_class{"PROXY"};
};

struct PlattModel {
    double a{};
    double b{};
    bool valid{};
    double predict(double score) const {
        const double z = std::clamp(a * score + b, -30.0, 30.0);
        return std::clamp(1.0 / (1.0 + std::exp(-z)), 1e-6, 1.0 - 1e-6);
    }
};

struct IsotonicBlock {
    double upper_score{};
    double probability{};
    std::size_t count{};
};

struct IsotonicModel {
    std::vector<IsotonicBlock> blocks;
    bool valid{};
    double predict(double score) const {
        if (blocks.empty()) return 0.5;
        for (const auto& block : blocks)
            if (score <= block.upper_score) return block.probability;
        return blocks.back().probability;
    }
};

struct CalibrationReport {
    std::string status{"NOT_CALIBRATED"};
    std::string reason{"INSUFFICIENT_OUTCOMES"};
    std::string method{"NONE"};
    std::size_t sample_count{};
    std::size_t train_count{};
    std::size_t validation_count{};
    std::size_t oos_count{};
    std::optional<double> brier_raw_oos;
    std::optional<double> brier_calibrated_oos;
    std::optional<double> brier_ci_low;
    std::optional<double> brier_ci_high;
    std::optional<double> log_loss_oos;
    std::optional<double> win_rate_oos;
    std::optional<double> win_rate_ci_low;
    std::optional<double> win_rate_ci_high;
    std::optional<double> probability_win;
    std::optional<double> avg_win_r;
    std::optional<double> avg_loss_r;
    std::optional<double> avg_fee_r;
    std::optional<double> avg_slippage_r;
    std::optional<double> avg_funding_r;
    std::optional<double> ev_net;
    std::string ev_status{"NOT_CALCULATED"};
    std::string ev_decision{"NOT_CALCULATED"};
};

inline double brier_score(const std::vector<double>& probabilities,
                          const std::vector<bool>& labels) {
    if (probabilities.empty() || probabilities.size() != labels.size())
        return std::numeric_limits<double>::quiet_NaN();
    double sum = 0.0;
    for (std::size_t i = 0U; i < probabilities.size(); ++i) {
        const double y = labels[i] ? 1.0 : 0.0;
        const double error = probabilities[i] - y;
        sum += error * error;
    }
    return sum / static_cast<double>(probabilities.size());
}

inline double log_loss(const std::vector<double>& probabilities,
                       const std::vector<bool>& labels) {
    if (probabilities.empty() || probabilities.size() != labels.size())
        return std::numeric_limits<double>::quiet_NaN();
    double sum = 0.0;
    for (std::size_t i = 0U; i < probabilities.size(); ++i) {
        const double p = std::clamp(probabilities[i], 1e-6, 1.0 - 1e-6);
        sum -= labels[i] ? std::log(p) : std::log(1.0 - p);
    }
    return sum / static_cast<double>(probabilities.size());
}

inline PlattModel fit_platt(const std::vector<Outcome>& outcomes) {
    PlattModel model{};
    if (outcomes.size() < 10U) return model;
    double a = 0.0;
    double b = 0.0;
    for (int iteration = 0; iteration < 100; ++iteration) {
        double g_a = 0.0, g_b = 0.0;
        double h_aa = 1e-6, h_ab = 0.0, h_bb = 1e-6;
        for (const auto& item : outcomes) {
            const double z = std::clamp(a * item.raw_score + b, -30.0, 30.0);
            const double p = 1.0 / (1.0 + std::exp(-z));
            const double y = item.win ? 1.0 : 0.0;
            const double error = p - y;
            const double weight = std::max(1e-9, p * (1.0 - p));
            g_a += error * item.raw_score;
            g_b += error;
            h_aa += weight * item.raw_score * item.raw_score;
            h_ab += weight * item.raw_score;
            h_bb += weight;
        }
        const double determinant = h_aa * h_bb - h_ab * h_ab;
        if (!std::isfinite(determinant) || std::abs(determinant) < 1e-12) return model;
        const double delta_a = (h_bb * g_a - h_ab * g_b) / determinant;
        const double delta_b = (-h_ab * g_a + h_aa * g_b) / determinant;
        a -= delta_a;
        b -= delta_b;
        if (!std::isfinite(a) || !std::isfinite(b)) return model;
        if (std::max(std::abs(delta_a), std::abs(delta_b)) < 1e-8) break;
    }
    model.a = a;
    model.b = b;
    model.valid = true;
    return model;
}

inline IsotonicModel fit_isotonic(const std::vector<Outcome>& outcomes) {
    struct Point { double score; double label; };
    struct Block { double upper; double sum; std::size_t count; };
    IsotonicModel model{};
    if (outcomes.size() < 10U) return model;
    std::vector<Point> points;
    points.reserve(outcomes.size());
    for (const auto& item : outcomes)
        points.push_back({item.raw_score, item.win ? 1.0 : 0.0});
    std::sort(points.begin(), points.end(), [](const Point& a, const Point& b) {
        return a.score < b.score;
    });
    std::vector<Block> blocks;
    for (const auto& point : points) {
        blocks.push_back({point.score, point.label, 1U});
        while (blocks.size() >= 2U) {
            const auto& left = blocks[blocks.size() - 2U];
            const auto& right = blocks.back();
            const double left_mean = left.sum / static_cast<double>(left.count);
            const double right_mean = right.sum / static_cast<double>(right.count);
            if (left_mean <= right_mean) break;
            Block merged{right.upper, left.sum + right.sum, left.count + right.count};
            blocks.pop_back();
            blocks.back() = merged;
        }
    }
    for (const auto& block : blocks)
        model.blocks.push_back({
            block.upper,
            std::clamp(block.sum / static_cast<double>(block.count), 1e-6, 1.0 - 1e-6),
            block.count
        });
    model.valid = !model.blocks.empty();
    return model;
}

inline std::pair<double, double> wilson_interval(std::size_t wins, std::size_t total) {
    if (total == 0U) return {0.0, 1.0};
    constexpr double z = 1.959963984540054;
    const double n = static_cast<double>(total);
    const double p = static_cast<double>(wins) / n;
    const double z2 = z * z;
    const double denominator = 1.0 + z2 / n;
    const double center = (p + z2 / (2.0 * n)) / denominator;
    const double margin = z * std::sqrt((p * (1.0 - p) / n) + z2 / (4.0 * n * n)) / denominator;
    return {std::max(0.0, center - margin), std::min(1.0, center + margin)};
}

inline CalibrationReport calibrate(std::vector<Outcome> outcomes,
                                   const std::string& path,
                                   const std::string& regime,
                                   double current_score, std::int64_t as_of_ms,
                                   const std::string& data_class = "PROXY") {
    CalibrationReport report{};
    std::set<std::string> ids;
    std::vector<Outcome> selected;
    if (as_of_ms <= 0 || !std::isfinite(current_score) || current_score < 0.0 || current_score > 1.0) {
        report.reason = "INVALID_AS_OF_OR_CURRENT_SCORE";
        return report;
    }
    for (const auto& item : outcomes) {
        if (item.path != path || item.regime != regime || item.data_class != data_class ||
            item.closed_at_ms >= as_of_ms) continue;
        if (item.signal_id.empty() || !ids.insert(item.signal_id).second ||
            item.closed_at_ms <= 0 || !std::isfinite(item.raw_score) ||
            item.raw_score < 0.0 || item.raw_score > 1.0 ||
            !std::isfinite(item.win_r) || !std::isfinite(item.loss_r) ||
            item.win_r < 0.0 || item.loss_r < 0.0 ||
            (item.costs_available && (!std::isfinite(item.fee_r) ||
             !std::isfinite(item.slippage_r) || !std::isfinite(item.funding_r) ||
             item.fee_r < 0.0 || item.slippage_r < 0.0 || item.funding_r < 0.0)) ||
            (item.win && (item.win_r <= 0.0 || item.loss_r != 0.0)) ||
            (!item.win && (item.loss_r <= 0.0 || item.win_r != 0.0))) {
            report.status = "INVALID_OUTCOME_LEDGER";
            report.reason = "INVALID_OR_DUPLICATE_OUTCOME_ROW";
            return report;
        }
        selected.push_back(item);
    }
    std::sort(selected.begin(), selected.end(), [](const Outcome& a, const Outcome& b) {
        if (a.closed_at_ms != b.closed_at_ms) return a.closed_at_ms < b.closed_at_ms;
        return a.signal_id < b.signal_id;
    });
    report.sample_count = selected.size();
    if (selected.size() < 250U) {
        report.reason = "INSUFFICIENT_PATH_REGIME_OUTCOMES_MIN_250_FOR_60_20_20_SPLIT";
        return report;
    }

    report.train_count = (selected.size() * 60U) / 100U;
    report.validation_count = (selected.size() * 20U) / 100U;
    report.oos_count = selected.size() - report.train_count - report.validation_count;
    if (report.train_count < 100U || report.validation_count < 30U || report.oos_count < 50U) {
        report.reason = "CHRONOLOGICAL_SPLIT_BELOW_MINIMUM_SAMPLE";
        return report;
    }

    std::vector<Outcome> train(selected.begin(), selected.begin() + static_cast<std::ptrdiff_t>(report.train_count));
    std::vector<Outcome> validation(
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count),
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count + report.validation_count));
    std::vector<Outcome> oos(
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count + report.validation_count),
        selected.end());

    const auto class_counts_valid = [](const std::vector<Outcome>& rows) {
        std::size_t wins = 0U;
        for (const auto& row : rows) if (row.win) ++wins;
        return wins > 0U && wins < rows.size();
    };
    if (!class_counts_valid(train) || !class_counts_valid(validation) || !class_counts_valid(oos)) {
        report.reason = "BOTH_OUTCOME_CLASSES_REQUIRED_IN_EACH_CHRONOLOGICAL_SPLIT";
        return report;
    }

    const auto platt = fit_platt(train);
    const auto isotonic = fit_isotonic(train);
    if (!platt.valid || !isotonic.valid) {
        report.reason = "CALIBRATOR_FIT_FAILED";
        return report;
    }

    std::vector<double> val_platt, val_isotonic;
    std::vector<bool> val_labels;
    for (const auto& item : validation) {
        val_platt.push_back(platt.predict(item.raw_score));
        val_isotonic.push_back(isotonic.predict(item.raw_score));
        val_labels.push_back(item.win);
    }
    const double platt_validation_brier = brier_score(val_platt, val_labels);
    const double isotonic_validation_brier = brier_score(val_isotonic, val_labels);
    const bool use_platt = platt_validation_brier <= isotonic_validation_brier;
    report.method = use_platt ? "PLATT" : "ISOTONIC";

    std::vector<double> oos_raw, oos_calibrated;
    std::vector<bool> oos_labels;
    std::size_t wins = 0U;
    double win_sum = 0.0, loss_sum = 0.0;
    double fee_sum = 0.0, slippage_sum = 0.0, funding_sum = 0.0;
    bool oos_costs_available = true;
    for (const auto& item : oos) {
        const double calibrated = use_platt ? platt.predict(item.raw_score) : isotonic.predict(item.raw_score);
        oos_raw.push_back(item.raw_score);
        oos_calibrated.push_back(calibrated);
        oos_labels.push_back(item.win);
        if (item.win) {
            ++wins;
            win_sum += item.win_r;
        } else {
            loss_sum += item.loss_r;
        }
        if (item.costs_available) {
            fee_sum += item.fee_r;
            slippage_sum += item.slippage_r;
            funding_sum += item.funding_r;
        } else {
            oos_costs_available = false;
        }
    }
    const double raw_brier = brier_score(oos_raw, oos_labels);
    const double calibrated_brier = brier_score(oos_calibrated, oos_labels);
    const double calibrated_logloss = log_loss(oos_calibrated, oos_labels);
    report.brier_raw_oos = raw_brier;
    report.brier_calibrated_oos = calibrated_brier;
    report.log_loss_oos = calibrated_logloss;
    report.win_rate_oos = static_cast<double>(wins) / static_cast<double>(oos.size());
    const auto win_ci = wilson_interval(wins, oos.size());
    report.win_rate_ci_low = win_ci.first;
    report.win_rate_ci_high = win_ci.second;

    double brier_variance = 0.0;
    for (std::size_t i = 0U; i < oos_calibrated.size(); ++i) {
        const double y = oos_labels[i] ? 1.0 : 0.0;
        const double error = oos_calibrated[i] - y;
        const double value = error * error;
        brier_variance += (value - calibrated_brier) * (value - calibrated_brier);
    }
    const double brier_se = std::sqrt(brier_variance /
        static_cast<double>(std::max<std::size_t>(1U, oos.size() - 1U)) /
        static_cast<double>(oos.size()));
    report.brier_ci_low = std::max(0.0, calibrated_brier - 1.96 * brier_se);
    report.brier_ci_high = std::min(1.0, calibrated_brier + 1.96 * brier_se);

    if (!(calibrated_brier < raw_brier) || !std::isfinite(calibrated_logloss)) {
        report.reason = "OOS_CALIBRATION_DID_NOT_IMPROVE_BRIER";
        return report;
    }
    report.status = "CALIBRATED";
    report.reason = "CHRONOLOGICAL_OOS_CALIBRATION_PASSED";
    report.probability_win = use_platt ? platt.predict(current_score) : isotonic.predict(current_score);

    if (wins == 0U || wins == oos.size()) return report;
    if (!oos_costs_available) {
        report.ev_status = "COSTS_UNAVAILABLE";
        report.ev_decision = "NOT_CALCULATED_COSTS_UNAVAILABLE";
        return report;
    }
    report.avg_win_r = win_sum / static_cast<double>(wins);
    report.avg_loss_r = loss_sum / static_cast<double>(oos.size() - wins);
    report.avg_fee_r = fee_sum / static_cast<double>(oos.size());
    report.avg_slippage_r = slippage_sum / static_cast<double>(oos.size());
    report.avg_funding_r = funding_sum / static_cast<double>(oos.size());
    const double average_cost = *report.avg_fee_r + *report.avg_slippage_r + *report.avg_funding_r;
    const double p_win = *report.probability_win;
    report.ev_net = p_win * *report.avg_win_r -
        (1.0 - p_win) * *report.avg_loss_r - average_cost;
    report.ev_status = "CALCULATED";
    report.ev_decision = *report.ev_net <= 0.0 ? "NO_TRADE" : "EV_POSITIVE_RESEARCH_ONLY";
    return report;
}

} // namespace cfss::meta
