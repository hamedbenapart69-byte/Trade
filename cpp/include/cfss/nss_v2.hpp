#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::nss {

struct V2Component {
    std::string id;
    std::optional<double> score;
    std::string data_class{"PROXY"};
    std::int64_t available_at_ms{};
    std::string definition_id;
    std::string reason;
};

struct V2DirectionResult {
    std::string direction;
    std::string status{"UNAVAILABLE"};
    std::optional<double> score;
    std::string data_class{"UNAVAILABLE"};
    std::array<V2Component, 5> components{};
    std::size_t missing_count{};
};

inline constexpr std::array<std::string_view, 5> nss_v2_component_ids{
    "NSS1_OPEN_INTEREST_GROWTH",
    "NSS2_HEALTHY_FUNDING",
    "NSS3_BASIS_EXPANSION",
    "NSS4_VOLUME_EXPANSION",
    "NSS5_PRE_BREAKOUT_COMPRESSION"
};
inline constexpr std::array<double, 5> nss_weights{0.30, 0.20, 0.20, 0.15, 0.15};

inline std::optional<double> v2_number(const nlohmann::json& value) {
    if (!value.is_number()) return std::nullopt;
    const double number = value.get<double>();
    return std::isfinite(number) ? std::optional<double>{number} : std::nullopt;
}

inline nlohmann::json point_in_time_rows(const nlohmann::json& rows,
                                         std::int64_t decision_time_ms) {
    using json = nlohmann::json;
    json out = json::array();
    if (!rows.is_array()) return out;
    std::int64_t previous = 0;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        if (ts <= previous || ts <= 0 || ts > decision_time_ms) continue;
        previous = ts;
        out.push_back(row);
    }
    return out;
}

inline std::optional<double> logistic_zscore(const std::vector<double>& prior,
                                              double current,
                                              double polarity = 1.0) {
    if (prior.size() < 20U || !std::isfinite(current) || !std::isfinite(polarity))
        return std::nullopt;
    double mean = 0.0;
    for (const double value : prior) {
        if (!std::isfinite(value)) return std::nullopt;
        mean += value;
    }
    mean /= static_cast<double>(prior.size());
    double variance = 0.0;
    for (const double value : prior) {
        const double delta = value - mean;
        variance += delta * delta;
    }
    variance /= static_cast<double>(prior.size());
    const double deviation = std::sqrt(variance);
    if (!std::isfinite(deviation) || deviation <= 1e-12) return std::nullopt;
    const double z = std::clamp(polarity * (current - mean) / deviation, -8.0, 8.0);
    const double score = 1.0 / (1.0 + std::exp(-z));
    if (!std::isfinite(score)) return std::nullopt;
    return score;
}

struct NormalizedFundingSeries {
    std::vector<std::pair<std::int64_t, double>> observations;
    std::int64_t median_interval_ms{};
    std::size_t skipped_gap_count{};
};

inline NormalizedFundingSeries normalize_funding_to_8h(const nlohmann::json& rows,
                                                        std::int64_t decision_time_ms) {
    using json = nlohmann::json;
    NormalizedFundingSeries result{};
    const auto filtered = point_in_time_rows(rows, decision_time_ms);
    if (filtered.size() < 2U) return result;
    std::vector<std::int64_t> intervals;
    intervals.reserve(filtered.size() - 1U);
    for (std::size_t i = 1U; i < filtered.size(); ++i) {
        const auto current = filtered[i].at("timestamp_ms").get<std::int64_t>();
        const auto previous = filtered[i - 1U].at("timestamp_ms").get<std::int64_t>();
        const auto interval = current - previous;
        if (interval >= 30LL * 60'000LL && interval <= 24LL * 3'600'000LL)
            intervals.push_back(interval);
    }
    if (intervals.empty()) return result;
    std::sort(intervals.begin(), intervals.end());
    result.median_interval_ms = intervals[intervals.size() / 2U];
    constexpr std::int64_t min_interval_ms = 30LL * 60'000LL;
    constexpr std::int64_t max_interval_ms = 24LL * 3'600'000LL;
    constexpr std::int64_t standard_interval_ms = 8LL * 3'600'000LL;
    for (std::size_t i = 1U; i < filtered.size(); ++i) {
        const auto ts = filtered[i].at("timestamp_ms").get<std::int64_t>();
        const auto previous = filtered[i - 1U].at("timestamp_ms").get<std::int64_t>();
        const auto interval = ts - previous;
        const auto rate = v2_number(filtered[i].value("funding_rate", json{}));
        if (!rate || interval < min_interval_ms || interval > max_interval_ms ||
            (result.median_interval_ms > 0 &&
             static_cast<double>(interval) > 1.5 * static_cast<double>(result.median_interval_ms))) {
            ++result.skipped_gap_count;
            continue;
        }
        const double normalized = *rate *
            (static_cast<double>(standard_interval_ms) / static_cast<double>(interval));
        if (std::isfinite(normalized)) result.observations.emplace_back(ts, normalized);
    }
    return result;
}

inline std::optional<double> weighted_score(const std::array<V2Component, 5>& components,
                                             std::int64_t decision_time_ms) {
    double total = 0.0;
    for (std::size_t i = 0U; i < components.size(); ++i) {
        const auto& component = components[i];
        if (component.id != nss_v2_component_ids[i] || !component.score ||
            !std::isfinite(*component.score) || *component.score < 0.0 ||
            *component.score > 1.0 || component.available_at_ms <= 0 ||
            component.available_at_ms > decision_time_ms || component.definition_id.empty() ||
            component.data_class != "PROXY") return std::nullopt;
        total += nss_weights[i] * *component.score;
    }
    return std::isfinite(total) ? std::optional<double>{total} : std::nullopt;
}

inline std::array<V2DirectionResult, 2> calculate_v2(
    const nlohmann::json& instrument,
    const nlohmann::json& basis_instrument,
    std::int64_t decision_time_ms) {
    using json = nlohmann::json;
    const auto candles = point_in_time_rows(instrument.value("candles", json::array()), decision_time_ms);
    const auto funding = point_in_time_rows(instrument.value("funding", json::array()), decision_time_ms);
    const auto oi = point_in_time_rows(instrument.value("open_interest", json::array()), decision_time_ms);
    const auto basis = point_in_time_rows(basis_instrument.value("basis", json::array()), decision_time_ms);

    std::map<std::int64_t, double> close_by_time, volume_by_time, oi_by_time, basis_by_time;
    for (const auto& row : candles) {
        const auto close = v2_number(row.value("close", json{}));
        const auto volume = v2_number(row.value("volume_quote", json{}));
        if (close && *close > 0.0) close_by_time[row.at("timestamp_ms").get<std::int64_t>()] = *close;
        if (volume && *volume >= 0.0) volume_by_time[row.at("timestamp_ms").get<std::int64_t>()] = *volume;
    }
    for (const auto& row : oi) {
        const auto value = v2_number(row.value("open_interest_value_usd", json{}));
        if (value && *value > 0.0) oi_by_time[row.at("timestamp_ms").get<std::int64_t>()] = *value;
    }
    for (const auto& row : basis) {
        const auto value = v2_number(row.value("basis_bps", json{}));
        if (value) basis_by_time[row.at("timestamp_ms").get<std::int64_t>()] = *value;
    }

    std::vector<double> oi_long, oi_short;
    std::vector<double> funding_long, funding_short;
    std::vector<double> basis_long, basis_short;
    std::vector<double> volume_long, volume_short;
    std::vector<double> compression;
    std::int64_t oi_time = 0, funding_time = 0, basis_time = 0, volume_time = 0, compression_time = 0;

    constexpr std::int64_t hour_ms = 3'600'000LL;
    for (const auto& [ts, current_oi] : oi_by_time) {
        const auto prior_oi = oi_by_time.find(ts - 24LL * hour_ms);
        const auto current_close = close_by_time.find(ts);
        const auto prior_close = close_by_time.find(ts - 24LL * hour_ms);
        if (prior_oi == oi_by_time.end() || current_close == close_by_time.end() ||
            prior_close == close_by_time.end() || prior_oi->second <= 0.0) continue;
        const double oi_change = current_oi / prior_oi->second - 1.0;
        const double price_return = current_close->second / prior_close->second - 1.0;
        if (!std::isfinite(oi_change) || !std::isfinite(price_return)) continue;
        oi_long.push_back(price_return * oi_change);
        oi_short.push_back(-price_return * oi_change);
        oi_time = ts;
    }

    const auto normalized_funding = normalize_funding_to_8h(funding, decision_time_ms);
    for (const auto& [ts, rate] : normalized_funding.observations) {
        funding_long.push_back(-rate);
        funding_short.push_back(rate);
        funding_time = ts;
    }

    for (const auto& [ts, current_basis] : basis_by_time) {
        const auto prior = basis_by_time.find(ts - 24LL * hour_ms);
        if (prior == basis_by_time.end()) continue;
        const double change = current_basis - prior->second;
        if (!std::isfinite(change)) continue;
        basis_long.push_back(change);
        basis_short.push_back(-change);
        basis_time = ts;
    }

    std::vector<std::pair<std::int64_t, double>> volume24;
    for (const auto& [ts, unused] : close_by_time) {
        (void)unused;
        double sum = 0.0;
        bool complete = true;
        for (std::int64_t offset = 0; offset < 24; ++offset) {
            const auto it = volume_by_time.find(ts - offset * hour_ms);
            if (it == volume_by_time.end()) { complete = false; break; }
            sum += it->second;
        }
        if (complete && sum > 0.0) volume24.emplace_back(ts, sum);
    }
    for (std::size_t i = 480U; i < volume24.size(); ++i) {
        const auto ts = volume24[i].first;
        const double current_volume = volume24[i].second;
        double prior_mean = 0.0;
        for (std::size_t j = i - 480U; j < i; ++j) prior_mean += volume24[j].second;
        prior_mean /= 480.0;
        const auto current_close = close_by_time.find(ts);
        const auto prior_close = close_by_time.find(ts - 24LL * hour_ms);
        if (prior_mean <= 0.0 || current_close == close_by_time.end() || prior_close == close_by_time.end())
            continue;
        const double price_return = current_close->second / prior_close->second - 1.0;
        const double expansion = std::log(current_volume / prior_mean);
        const double aligned = price_return * expansion;
        if (!std::isfinite(aligned)) continue;
        volume_long.push_back(aligned);
        volume_short.push_back(-aligned);
        volume_time = ts;
    }

    std::vector<std::pair<std::int64_t, double>> widths;
    for (std::size_t i = 19U; i < candles.size(); ++i) {
        double mean = 0.0;
        std::array<double, 20> closes{};
        bool valid = true;
        for (std::size_t j = 0U; j < 20U; ++j) {
            const auto value = v2_number(candles[i - 19U + j].value("close", json{}));
            if (!value || *value <= 0.0) { valid = false; break; }
            closes[j] = *value;
            mean += *value;
        }
        if (!valid) continue;
        mean /= 20.0;
        double variance = 0.0;
        for (const double value : closes) variance += (value - mean) * (value - mean);
        variance /= 20.0;
        const double width = 4.0 * std::sqrt(variance) / mean;
        if (std::isfinite(width)) widths.emplace_back(
            candles[i].at("timestamp_ms").get<std::int64_t>(), -width);
    }
    for (const auto& item : widths) {
        compression.push_back(item.second);
        compression_time = item.first;
    }

    const auto build_direction = [&](const std::string& direction, double sign) {
        V2DirectionResult result{};
        result.direction = direction;
        const auto component_score = [&](const std::vector<double>& values,
                                         const std::string& id,
                                         const std::string& definition,
                                         std::int64_t timestamp,
                                         std::int64_t max_age_ms,
                                         const std::string& reason) {
            V2Component component{};
            component.id = id;
            component.data_class = "PROXY";
            component.available_at_ms = timestamp;
            component.definition_id = definition;
            component.reason = reason;
            const bool fresh = timestamp > 0 && timestamp <= decision_time_ms &&
                               decision_time_ms - timestamp <= max_age_ms;
            if (fresh && values.size() >= 21U) {
                std::vector<double> prior(values.begin(), values.end() - 1);
                component.score = logistic_zscore(prior, values.back());
            }
            if (!fresh) component.reason = "STALE_OR_INVALID_COMPONENT_TIMESTAMP";
            else if (!component.score) component.reason = "INSUFFICIENT_OR_CONSTANT_REFERENCE";
            return component;
        };
        const auto choose = [&](const std::vector<double>& long_values,
                                const std::vector<double>& short_values) -> const std::vector<double>& {
            return sign > 0.0 ? long_values : short_values;
        };
        result.components = {{
            component_score(choose(oi_long, oi_short), "NSS1_OPEN_INTEREST_GROWTH",
                            "NSS_V2_OI_PRICE_ALIGNMENT_ZSIGMOID_24H", oi_time, 2LL * hour_ms, "OI_GROWTH_ALIGNED_WITH_PRICE_DIRECTION"),
            component_score(choose(funding_long, funding_short), "NSS2_HEALTHY_FUNDING",
                            "NSS_V2_DIRECTIONAL_FUNDING_8H_NORMALIZED_ZSIGMOID", funding_time, 24LL * hour_ms, "FUNDING_COST_NORMALIZED_TO_8H;MEDIAN_INTERVAL_MS=" + std::to_string(normalized_funding.median_interval_ms) + ";SKIPPED_GAPS=" + std::to_string(normalized_funding.skipped_gap_count)),
            component_score(choose(basis_long, basis_short), "NSS3_BASIS_EXPANSION",
                            "NSS_V2_SPOT_PERP_BASIS_CHANGE_ZSIGMOID_24H", basis_time, 2LL * hour_ms, "REAL_BASIS_INPUT_PROXY_TRANSFORM"),
            component_score(choose(volume_long, volume_short), "NSS4_VOLUME_EXPANSION",
                            "NSS_V2_DIRECTIONAL_VOLUME_EXPANSION_ZSIGMOID", volume_time, 2LL * hour_ms, "VOLUME_EXPANSION_ALIGNED_WITH_PRICE_DIRECTION"),
            component_score(compression, "NSS5_PRE_BREAKOUT_COMPRESSION",
                            "NSS_V2_INVERSE_BB_WIDTH_ZSIGMOID_20H", compression_time, 2LL * hour_ms, "LOWER_BB_WIDTH_SCORES_HIGHER")
        }};
        result.missing_count = 0U;
        for (const auto& component : result.components) if (!component.score) ++result.missing_count;
        if (result.missing_count == 0U) {
            result.score = weighted_score(result.components, decision_time_ms);
            if (result.score) {
                result.status = "CALCULATED";
                result.data_class = "PROXY";
            }
        }
        return result;
    };

    return {build_direction("LONG", 1.0), build_direction("SHORT", -1.0)};
}

} // namespace cfss::nss
