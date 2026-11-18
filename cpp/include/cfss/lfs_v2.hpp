#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace cfss::lfs {

struct V2Component {
    std::string id;
    std::optional<double> score;
    std::string data_class;
    std::int64_t available_at_ms{};
    std::string definition_id;
    std::string reason;
};

struct V2Result {
    std::string version{"LFS_V2_PROXY"};
    std::string status{"UNAVAILABLE"};
    std::optional<double> score;
    std::string data_class{"UNAVAILABLE"};
    std::array<V2Component, 5> components{};
    std::size_t missing_count{};
};

inline constexpr std::array<std::string, 5> v2_component_ids{
    "LFS1_BOOK_THINNESS",
    "LFS2_FUNDING_EXTREME",
    "LFS3_LONG_SHORT_POSITIONING",
    "LFS4_VOLATILITY_COMPRESSION",
    "LFS5_OPEN_INTEREST_CHANGE"
};
inline constexpr std::array<double, 5> v2_weights{0.25, 0.20, 0.20, 0.20, 0.15};

inline nlohmann::json filter_time_series(const nlohmann::json& rows, std::int64_t decision_time_ms) {
    if (!rows.is_array()) return nlohmann::json::array();
    nlohmann::json filtered = nlohmann::json::array();
    std::int64_t previous = 0;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        if (ts <= 0 || ts <= previous) continue;
        previous = ts;
        if (ts <= decision_time_ms) filtered.push_back(row);
    }
    return filtered;
}

inline std::optional<double> percentile_rank(const std::vector<double>& prior, double current) {
    if (prior.size() < 20U || !std::isfinite(current)) return std::nullopt;
    std::size_t less = 0U;
    std::size_t equal = 0U;
    for (const double value : prior) {
        if (!std::isfinite(value)) return std::nullopt;
        if (value < current) ++less;
        else if (value == current) ++equal;
    }
    const double numerator = static_cast<double>(less) + 0.5 * static_cast<double>(equal);
    return numerator / static_cast<double>(prior.size());
}

inline std::optional<double> numeric(const nlohmann::json& value) {
    if (value.is_number()) {
        const double n = value.get<double>();
        if (std::isfinite(n)) return n;
    }
    return std::nullopt;
}

inline std::vector<double> true_ranges(const nlohmann::json& candles) {
    std::vector<double> out;
    if (!candles.is_array() || candles.size() < 2U) return out;
    for (std::size_t i = 1U; i < candles.size(); ++i) {
        const auto high = numeric(candles[i].value("high", nlohmann::json{}));
        const auto low = numeric(candles[i].value("low", nlohmann::json{}));
        const auto prev_close = numeric(candles[i - 1U].value("close", nlohmann::json{}));
        if (!high || !low || !prev_close || *high < *low || *prev_close <= 0.0) return {};
        out.push_back(std::max({*high - *low, std::abs(*high - *prev_close), std::abs(*low - *prev_close)}));
    }
    return out;
}

inline std::optional<double> lfs1_proxy_score(const nlohmann::json& candles) {
    if (!candles.is_array() || candles.size() < 24U * 90U + 30U) return std::nullopt;
    const auto tr = true_ranges(candles);
    if (tr.size() + 1U != candles.size()) return std::nullopt;
    std::vector<double> atr_pct;
    std::vector<double> volume24;
    atr_pct.reserve(tr.size());
    volume24.reserve(tr.size());
    for (std::size_t i = 13U; i < tr.size(); ++i) {
        double atr = 0.0;
        for (std::size_t j = i - 13U; j <= i; ++j) atr += tr[j];
        atr /= 14.0;
        const auto close = numeric(candles[i + 1U].value("close", nlohmann::json{}));
        if (!close || *close <= 0.0) return std::nullopt;
        atr_pct.push_back(atr / *close);
    }
    for (std::size_t i = 23U; i < candles.size(); ++i) {
        double volume = 0.0;
        for (std::size_t j = i - 23U; j <= i; ++j) {
            const auto v = numeric(candles[j].value("volume", nlohmann::json{}));
            if (!v || *v < 0.0) return std::nullopt;
            volume += *v;
        }
        volume24.push_back(volume);
    }
    if (atr_pct.size() < 24U * 90U || volume24.size() < 24U * 90U) return std::nullopt;
    const double current_atr = atr_pct.back();
    const double current_volume = volume24.back();
    atr_pct.pop_back();
    volume24.pop_back();
    const auto atr_rank = percentile_rank(atr_pct, current_atr);
    const auto volume_rank = percentile_rank(volume24, current_volume);
    if (!atr_rank || !volume_rank) return std::nullopt;
    return 0.5 * *atr_rank + 0.5 * (1.0 - *volume_rank);
}

inline std::optional<double> funding_extreme_score(const nlohmann::json& funding) {
    if (!funding.is_array() || funding.size() < 21U) return std::nullopt;
    std::vector<double> values;
    values.reserve(funding.size());
    for (const auto& row : funding) {
        const auto rate = numeric(row.value("funding_rate", nlohmann::json{}));
        if (!rate) continue;
        values.push_back(std::abs(*rate));
    }
    if (values.size() < 21U) return std::nullopt;
    const double current = values.back();
    values.pop_back();
    return percentile_rank(values, current);
}

inline std::optional<double> long_short_extreme_score(const nlohmann::json& long_short) {
    if (!long_short.is_array() || long_short.size() < 21U) return std::nullopt;
    std::vector<double> values;
    values.reserve(long_short.size());
    for (const auto& row : long_short) {
        const auto ratio = numeric(row.value("ratio", nlohmann::json{}));
        if (!ratio || *ratio <= 0.0) continue;
        values.push_back(std::abs(std::log(*ratio)));
    }
    if (values.size() < 21U) return std::nullopt;
    const double current = values.back();
    values.pop_back();
    return percentile_rank(values, current);
}

inline std::optional<double> bb_width_compression_score(const nlohmann::json& candles) {
    if (!candles.is_array() || candles.size() < 24U * 90U + 20U) return std::nullopt;
    std::vector<double> widths;
    widths.reserve(candles.size() - 19U);
    for (std::size_t i = 19U; i < candles.size(); ++i) {
        std::array<double, 20> closes{};
        double mean = 0.0;
        for (std::size_t j = 0U; j < 20U; ++j) {
            const auto close = numeric(candles[i - 19U + j].value("close", nlohmann::json{}));
            if (!close || *close <= 0.0) return std::nullopt;
            closes[j] = *close;
            mean += *close;
        }
        mean /= 20.0;
        double variance = 0.0;
        for (const double close : closes) variance += (close - mean) * (close - mean);
        variance /= 20.0;
        const double width = 4.0 * std::sqrt(variance) / mean;
        if (!std::isfinite(width)) return std::nullopt;
        widths.push_back(width);
    }
    if (widths.size() < 24U * 90U) return std::nullopt;
    const double current = widths.back();
    widths.pop_back();
    const auto rank = percentile_rank(widths, current);
    if (!rank) return std::nullopt;
    return 1.0 - *rank;
}

inline std::optional<double> oi_change_score(const nlohmann::json& oi) {
    if (!oi.is_array() || oi.size() < 25U + 21U) return std::nullopt;
    std::vector<double> changes;
    changes.reserve(oi.size() - 24U);
    for (std::size_t i = 24U; i < oi.size(); ++i) {
        const auto current = numeric(oi[i].value("open_interest_value_usd", nlohmann::json{}));
        const auto prior = numeric(oi[i - 24U].value("open_interest_value_usd", nlohmann::json{}));
        if (!current || !prior || *current <= 0.0 || *prior <= 0.0) continue;
        changes.push_back(std::abs(*current / *prior - 1.0));
    }
    if (changes.size() < 21U) return std::nullopt;
    const double current = changes.back();
    changes.pop_back();
    return percentile_rank(changes, current);
}

inline V2Result aggregate_v2(const std::array<V2Component, 5>& components,
                             std::int64_t decision_time_ms) {
    V2Result result{};
    double weighted_sum = 0.0;
    bool has_proxy = false;
    for (std::size_t i = 0U; i < components.size(); ++i) {
        const auto& c = components[i];
        if (c.id != v2_component_ids[i] || !c.score || !std::isfinite(*c.score) ||
            *c.score < 0.0 || *c.score > 1.0 || c.available_at_ms <= 0 ||
            c.available_at_ms > decision_time_ms || c.definition_id.empty() ||
            (c.data_class != "REAL" && c.data_class != "PROXY")) {
            ++result.missing_count;
            continue;
        }
        weighted_sum += v2_weights[i] * *c.score;
        if (c.data_class == "PROXY") has_proxy = true;
    }
    result.components = components;
    if (result.missing_count != 0U) return result;
    result.score = weighted_sum;
    result.status = "CALCULATED";
    result.data_class = has_proxy ? "PROXY" : "REAL";
    return result;
}

} // namespace cfss::lfs
