#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
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
    std::string profile{"DAILY_SWING"};
    std::string outcome_kind{"HYPOTHESIS_PROXY"};
    std::string execution_status{"NOT_EXECUTED"};
    std::string source_scan_id;
    std::string symbol;
    std::string score_model_version;
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

struct ReliabilityBin {
    double lower_bound{};
    double upper_bound{};
    std::size_t count{};
    double mean_probability{};
    double observed_win_rate{};
};

struct CalibrationReport {
    std::string score_model_version;
    std::string status{"NOT_CALIBRATED"};
    std::string reason{"INSUFFICIENT_OUTCOMES"};
    std::string method{"NONE"};
    std::size_t sample_count{};
    std::size_t train_count{};
    std::size_t validation_count{};
    std::size_t oos_count{};
    std::size_t train_scan_clusters{};
    std::size_t train_symbol_clusters{};
    std::size_t train_utc_day_clusters{};
    std::size_t validation_scan_clusters{};
    std::size_t validation_symbol_clusters{};
    std::size_t validation_utc_day_clusters{};
    std::size_t oos_scan_clusters{};
    std::size_t oos_symbol_clusters{};
    std::size_t oos_utc_day_clusters{};
    double train_effective_sample_size{};
    double validation_effective_sample_size{};
    double oos_effective_sample_size{};
    std::int64_t oos_period_start_ms{};
    std::int64_t oos_period_end_ms{};
    std::map<std::string, std::size_t> oos_symbol_distribution;
    std::map<std::string, std::size_t> oos_daily_distribution;
    std::string confidence_interval_method{"MAX_OF_ONE_WAY_CLUSTER_SE"};
    std::string win_rate_interval_method{"WILSON_95_PLUS_MAX_OF_ONE_WAY_CLUSTER_SE"};
    std::optional<double> brier_raw_oos;
    std::optional<double> brier_calibrated_oos;
    std::optional<double> brier_ci_low;
    std::optional<double> brier_ci_high;
    std::optional<double> log_loss_oos;
    std::optional<double> ece_raw_oos;
    std::optional<double> ece_calibrated_oos;
    std::vector<ReliabilityBin> reliability_bins;
    std::optional<double> win_rate_oos;
    std::optional<double> win_rate_ci_low;
    std::optional<double> win_rate_ci_high;
    std::optional<double> win_rate_cluster_ci_low;
    std::optional<double> win_rate_cluster_ci_high;
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

struct ClusterMetrics {
    std::size_t scan_clusters{};
    std::size_t symbol_clusters{};
    std::size_t utc_day_clusters{};
    double scan_effective_n{};
    double symbol_effective_n{};
    double utc_day_effective_n{};
    double effective_n{};
};

inline std::string cluster_key(const Outcome& row, int dimension) {
    if (dimension == 0) return row.source_scan_id;
    if (dimension == 1) return row.symbol;
    return std::to_string(row.closed_at_ms / 86'400'000LL);
}

inline double effective_n_for_groups(const std::vector<Outcome>& rows, int dimension) {
    if (rows.empty()) return 0.0;
    std::map<std::string, std::size_t> counts;
    for (const auto& row : rows)
        ++counts[cluster_key(row, dimension)];
    double sum_squares = 0.0;
    for (const auto& [key, count] : counts) {
        (void)key;
        const double n = static_cast<double>(count);
        sum_squares += n * n;
    }
    const double total = static_cast<double>(rows.size());
    return sum_squares > 0.0 ? (total * total) / sum_squares : 0.0;
}

inline ClusterMetrics cluster_metrics(const std::vector<Outcome>& rows) {
    std::set<std::string> scans, symbols, utc_days;
    for (const auto& row : rows) {
        scans.insert(row.source_scan_id);
        symbols.insert(row.symbol);
        utc_days.insert(cluster_key(row, 2));
    }
    ClusterMetrics metrics{};
    metrics.scan_clusters = scans.size();
    metrics.symbol_clusters = symbols.size();
    metrics.utc_day_clusters = utc_days.size();
    metrics.scan_effective_n = effective_n_for_groups(rows, 0);
    metrics.symbol_effective_n = effective_n_for_groups(rows, 1);
    metrics.utc_day_effective_n = effective_n_for_groups(rows, 2);
    metrics.effective_n = std::min({
        metrics.scan_effective_n, metrics.symbol_effective_n, metrics.utc_day_effective_n
    });
    return metrics;
}

inline double cluster_robust_se(const std::vector<double>& values,
                                const std::vector<Outcome>& rows,
                                int dimension) {
    if (values.size() != rows.size() || values.size() < 2U)
        return std::numeric_limits<double>::quiet_NaN();
    std::map<std::string, double> cluster_sums;
    const double mean = std::accumulate(values.begin(), values.end(), 0.0) /
                        static_cast<double>(values.size());
    for (std::size_t i = 0U; i < values.size(); ++i) {
        cluster_sums[cluster_key(rows[i], dimension)] += values[i] - mean;
    }
    if (cluster_sums.size() < 2U) return std::numeric_limits<double>::quiet_NaN();
    double sum_squares = 0.0;
    for (const auto& [key, sum] : cluster_sums) {
        (void)key;
        sum_squares += sum * sum;
    }
    const double clusters = static_cast<double>(cluster_sums.size());
    const double n = static_cast<double>(values.size());
    const double variance = (clusters / (clusters - 1.0)) * sum_squares / (n * n);
    return std::sqrt(std::max(0.0, variance));
}

inline double three_way_cluster_robust_se(const std::vector<double>& values,
                                          const std::vector<Outcome>& rows) {
    const double scan_se = cluster_robust_se(values, rows, 0);
    const double symbol_se = cluster_robust_se(values, rows, 1);
    const double day_se = cluster_robust_se(values, rows, 2);
    if (!std::isfinite(scan_se) || !std::isfinite(symbol_se) || !std::isfinite(day_se))
        return std::numeric_limits<double>::quiet_NaN();
    return std::max({scan_se, symbol_se, day_se});
}

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

inline std::pair<double, std::vector<ReliabilityBin>> expected_calibration_error(
    const std::vector<double>& probabilities, const std::vector<bool>& labels,
    std::size_t bin_count = 10U) {
    if (probabilities.empty() || probabilities.size() != labels.size() || bin_count == 0U)
        return {std::numeric_limits<double>::quiet_NaN(), {}};
    std::vector<std::size_t> counts(bin_count, 0U);
    std::vector<double> probability_sums(bin_count, 0.0);
    std::vector<std::size_t> win_counts(bin_count, 0U);
    for (std::size_t i = 0U; i < probabilities.size(); ++i) {
        const double p = std::clamp(probabilities[i], 0.0, 1.0);
        const auto index = std::min(bin_count - 1U,
            static_cast<std::size_t>(p * static_cast<double>(bin_count)));
        ++counts[index];
        probability_sums[index] += p;
        if (labels[i]) ++win_counts[index];
    }
    double ece = 0.0;
    std::vector<ReliabilityBin> bins;
    bins.reserve(bin_count);
    const double total = static_cast<double>(probabilities.size());
    for (std::size_t i = 0U; i < bin_count; ++i) {
        const double lower = static_cast<double>(i) / static_cast<double>(bin_count);
        const double upper = static_cast<double>(i + 1U) / static_cast<double>(bin_count);
        ReliabilityBin bin{lower, upper, counts[i], 0.0, 0.0};
        if (counts[i] > 0U) {
            bin.mean_probability = probability_sums[i] / static_cast<double>(counts[i]);
            bin.observed_win_rate = static_cast<double>(win_counts[i]) /
                                    static_cast<double>(counts[i]);
            ece += (static_cast<double>(counts[i]) / total) *
                   std::abs(bin.mean_probability - bin.observed_win_rate);
        }
        bins.push_back(bin);
    }
    return {ece, bins};
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
                                   const std::string& data_class = "PROXY",
                                   const std::string& profile = "DAILY_SWING",
                                   const std::string& score_model_version = "") {
    CalibrationReport report{};
    const std::string expected_score_model_version = score_model_version.empty()
        ? (path == "PLAN_A_LRT" ? "LFS_V2_PROXY" : "NSS_V2_PROXY")
        : score_model_version;
    report.score_model_version = expected_score_model_version;
    std::set<std::string> ids;
    std::vector<Outcome> selected;
    if (as_of_ms <= 0 || !std::isfinite(current_score) || current_score < 0.0 || current_score > 1.0) {
        report.reason = "INVALID_AS_OF_OR_CURRENT_SCORE";
        return report;
    }
    for (const auto& item : outcomes) {
        if (item.path != path || item.regime != regime || item.data_class != data_class ||
            item.profile != profile || item.score_model_version != expected_score_model_version ||
            item.outcome_kind != "HYPOTHESIS_PROXY" ||
            item.execution_status != "NOT_EXECUTED" || item.closed_at_ms >= as_of_ms) continue;
        if (item.signal_id.empty() || !ids.insert(item.signal_id).second ||
            item.source_scan_id.empty() || item.symbol.empty() ||
            item.closed_at_ms <= 0 || !std::isfinite(item.raw_score) ||
            item.raw_score < 0.0 || item.raw_score > 1.0 ||
            !std::isfinite(item.win_r) || !std::isfinite(item.loss_r) ||
            item.win_r < 0.0 || item.loss_r < 0.0 ||
            (item.costs_available && (!std::isfinite(item.fee_r) ||
             !std::isfinite(item.slippage_r) || !std::isfinite(item.funding_r) ||
             item.fee_r < 0.0 || item.slippage_r < 0.0)) ||
            (item.win && (item.win_r <= 0.0 || item.loss_r != 0.0)) ||
            (!item.win && (item.loss_r < 0.0 || item.win_r != 0.0))) {
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
        report.reason = "PROVISIONAL_SAMPLE_GUARD_250_PENDING_COHORT_POWER_ANALYSIS";
        return report;
    }

    report.train_count = (selected.size() * 60U) / 100U;
    report.validation_count = (selected.size() * 20U) / 100U;
    report.oos_count = selected.size() - report.train_count - report.validation_count;
    if (report.train_count < 100U || report.validation_count < 30U || report.oos_count < 50U) {
        report.reason = "PROVISIONAL_CHRONOLOGICAL_SPLIT_GUARD_NOT_MET";
        return report;
    }

    std::vector<Outcome> train(selected.begin(), selected.begin() + static_cast<std::ptrdiff_t>(report.train_count));
    std::vector<Outcome> validation(
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count),
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count + report.validation_count));
    std::vector<Outcome> oos(
        selected.begin() + static_cast<std::ptrdiff_t>(report.train_count + report.validation_count),
        selected.end());

    const auto train_clusters = cluster_metrics(train);
    const auto validation_clusters = cluster_metrics(validation);
    const auto oos_clusters = cluster_metrics(oos);
    report.train_scan_clusters = train_clusters.scan_clusters;
    report.train_symbol_clusters = train_clusters.symbol_clusters;
    report.train_utc_day_clusters = train_clusters.utc_day_clusters;
    report.validation_scan_clusters = validation_clusters.scan_clusters;
    report.validation_symbol_clusters = validation_clusters.symbol_clusters;
    report.validation_utc_day_clusters = validation_clusters.utc_day_clusters;
    report.oos_scan_clusters = oos_clusters.scan_clusters;
    report.oos_symbol_clusters = oos_clusters.symbol_clusters;
    report.oos_utc_day_clusters = oos_clusters.utc_day_clusters;
    report.train_effective_sample_size = train_clusters.effective_n;
    report.validation_effective_sample_size = validation_clusters.effective_n;
    report.oos_effective_sample_size = oos_clusters.effective_n;
    if (!oos.empty()) {
        report.oos_period_start_ms = oos.front().closed_at_ms;
        report.oos_period_end_ms = oos.back().closed_at_ms;
        for (const auto& row : oos) {
            ++report.oos_symbol_distribution[row.symbol];
            ++report.oos_daily_distribution[
                std::to_string(row.closed_at_ms / 86'400'000LL)];
        }
    }
    if (oos_clusters.effective_n < 30.0) {
        report.reason = "INSUFFICIENT_EFFECTIVE_OOS_SAMPLE_AFTER_SCAN_SYMBOL_AND_UTC_DAY_CLUSTERING";
        return report;
    }

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
    const auto raw_ece = expected_calibration_error(oos_raw, oos_labels);
    const auto calibrated_ece = expected_calibration_error(oos_calibrated, oos_labels);
    report.brier_raw_oos = raw_brier;
    report.brier_calibrated_oos = calibrated_brier;
    report.log_loss_oos = calibrated_logloss;
    report.ece_raw_oos = raw_ece.first;
    report.ece_calibrated_oos = calibrated_ece.first;
    report.reliability_bins = calibrated_ece.second;
    report.win_rate_oos = static_cast<double>(wins) / static_cast<double>(oos.size());
    const auto win_ci = wilson_interval(wins, oos.size());
    report.win_rate_ci_low = win_ci.first;
    report.win_rate_ci_high = win_ci.second;
    std::vector<double> win_values, brier_values;
    win_values.reserve(oos.size());
    brier_values.reserve(oos.size());
    for (std::size_t i = 0U; i < oos_calibrated.size(); ++i) {
        const double y = oos_labels[i] ? 1.0 : 0.0;
        win_values.push_back(y);
        const double error = oos_calibrated[i] - y;
        brier_values.push_back(error * error);
    }
    const double win_se = three_way_cluster_robust_se(win_values, oos);
    const double brier_se = three_way_cluster_robust_se(brier_values, oos);
    if (!std::isfinite(win_se) || !std::isfinite(brier_se)) {
        report.reason = "CLUSTER_ROBUST_CONFIDENCE_INTERVAL_UNAVAILABLE";
        return report;
    }
    report.win_rate_cluster_ci_low = std::max(0.0, *report.win_rate_oos - 1.96 * win_se);
    report.win_rate_cluster_ci_high = std::min(1.0, *report.win_rate_oos + 1.96 * win_se);
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
