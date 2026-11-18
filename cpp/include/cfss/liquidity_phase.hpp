#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::liquidity {

struct Bar4H {
    std::int64_t timestamp_ms{};
    std::int64_t available_at_ms{};
    double open{};
    double high{};
    double low{};
    double close{};
    double volume_quote{};
};

struct Zone {
    std::string id;
    std::string side;
    double low{};
    double high{};
    double wick_ratio{};
    double volume_ratio{};
    double atr{};
    std::int64_t pivot_time_ms{};
    std::int64_t confirmed_at_ms{};
    std::int64_t invalidated_at_ms{};
    std::size_t touch_count{};
    std::string status{"ACTIVE"};
};

struct Result {
    std::string symbol;
    std::string status{"UNAVAILABLE"};
    std::string phase{"UNAVAILABLE"};
    std::string phase_reason;
    std::int64_t as_of_ms{};
    double current_price{};
    std::vector<Zone> zones;
    std::optional<Zone> nearest_support;
    std::optional<Zone> nearest_resistance;
};

inline std::optional<double> number(const nlohmann::json& row, const char* key) {
    if (!row.is_object() || !row.contains(key) || !row.at(key).is_number())
        return std::nullopt;
    const double value = row.at(key).get<double>();
    return std::isfinite(value) ? std::optional<double>{value} : std::nullopt;
}

inline std::vector<Bar4H> aggregate_4h(const nlohmann::json& hourly,
                                       std::int64_t decision_time_ms) {
    using json = nlohmann::json;
    constexpr std::int64_t hour_ms = 3'600'000LL;
    constexpr std::int64_t four_hours_ms = 4LL * hour_ms;
    std::map<std::int64_t, std::vector<json>> buckets;
    if (!hourly.is_array()) return {};
    std::int64_t previous = 0;
    for (const auto& row : hourly) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        const auto ts = row.at("timestamp_ms").get<std::int64_t>();
        if (ts <= previous || ts <= 0 || ts + hour_ms > decision_time_ms) continue;
        previous = ts;
        buckets[(ts / four_hours_ms) * four_hours_ms].push_back(row);
    }

    std::vector<Bar4H> out;
    for (const auto& [bucket_start, rows] : buckets) {
        if (rows.size() != 4U) continue;
        bool complete = true;
        for (std::size_t i = 0U; i < 4U; ++i) {
            if (rows[i].at("timestamp_ms").get<std::int64_t>() !=
                bucket_start + static_cast<std::int64_t>(i) * hour_ms) {
                complete = false;
                break;
            }
        }
        if (!complete || bucket_start + four_hours_ms > decision_time_ms) continue;
        const auto open = number(rows.front(), "open");
        const auto close = number(rows.back(), "close");
        if (!open || !close || *open <= 0.0 || *close <= 0.0) continue;
        Bar4H bar{};
        bar.timestamp_ms = bucket_start;
        bar.available_at_ms = bucket_start + four_hours_ms;
        bar.open = *open;
        bar.close = *close;
        bar.high = -std::numeric_limits<double>::infinity();
        bar.low = std::numeric_limits<double>::infinity();
        for (const auto& row : rows) {
            const auto high = number(row, "high");
            const auto low = number(row, "low");
            const auto volume = number(row, "volume_quote");
            if (!high || !low || !volume || *high < *low || *volume < 0.0) {
                complete = false;
                break;
            }
            bar.high = std::max(bar.high, *high);
            bar.low = std::min(bar.low, *low);
            bar.volume_quote += *volume;
        }
        if (!complete || bar.high < bar.low || bar.volume_quote < 0.0) continue;
        out.push_back(bar);
    }
    return out;
}

inline double true_range(const Bar4H& current, const Bar4H& previous) {
    return std::max({current.high - current.low,
                     std::abs(current.high - previous.close),
                     std::abs(current.low - previous.close)});
}

inline std::optional<double> atr14(const std::vector<Bar4H>& bars, std::size_t index) {
    if (index < 14U || index >= bars.size()) return std::nullopt;
    double total = 0.0;
    for (std::size_t i = index - 13U; i <= index; ++i)
        total += true_range(bars[i], bars[i - 1U]);
    const double value = total / 14.0;
    return std::isfinite(value) && value > 0.0 ? std::optional<double>{value} : std::nullopt;
}

inline std::optional<double> median_prior_volume(const std::vector<Bar4H>& bars,
                                                  std::size_t index) {
    if (index < 20U || index >= bars.size()) return std::nullopt;
    std::vector<double> values;
    values.reserve(20U);
    for (std::size_t i = index - 20U; i < index; ++i)
        values.push_back(bars[i].volume_quote);
    std::sort(values.begin(), values.end());
    const double value = (values[9U] + values[10U]) / 2.0;
    return value > 0.0 && std::isfinite(value) ? std::optional<double>{value} : std::nullopt;
}

inline bool pivot_high(const std::vector<Bar4H>& bars, std::size_t index) {
    if (index < 2U || index + 2U >= bars.size()) return false;
    for (std::size_t i = index - 2U; i <= index + 2U; ++i)
        if (i != index && bars[i].high >= bars[index].high) return false;
    return true;
}

inline bool pivot_low(const std::vector<Bar4H>& bars, std::size_t index) {
    if (index < 2U || index + 2U >= bars.size()) return false;
    for (std::size_t i = index - 2U; i <= index + 2U; ++i)
        if (i != index && bars[i].low <= bars[index].low) return false;
    return true;
}

inline double ema(const std::vector<Bar4H>& bars, std::size_t end, std::size_t period) {
    const double alpha = 2.0 / (static_cast<double>(period) + 1.0);
    double value = bars.front().close;
    for (std::size_t i = 1U; i <= end; ++i)
        value = alpha * bars[i].close + (1.0 - alpha) * value;
    return value;
}

inline std::string classify_phase(const std::vector<Bar4H>& bars,
                                  const std::vector<std::pair<std::size_t, double>>& highs,
                                  const std::vector<std::pair<std::size_t, double>>& lows,
                                  std::string& reason) {
    if (bars.size() < 200U || highs.size() < 2U || lows.size() < 2U) {
        reason = "INSUFFICIENT_CONFIRMED_STRUCTURE";
        return "UNAVAILABLE";
    }
    const auto& h0 = highs[highs.size() - 2U];
    const auto& h1 = highs.back();
    const auto& l0 = lows[lows.size() - 2U];
    const auto& l1 = lows.back();
    const double ema50 = ema(bars, bars.size() - 1U, 50U);
    const double ema200 = ema(bars, bars.size() - 1U, 200U);
    const double close = bars.back().close;
    if (h1.second > h0.second && l1.second > l0.second &&
        close > ema50 && close > ema200) {
        reason = "HIGHER_HIGH_HIGHER_LOW_AND_CLOSE_ABOVE_EMA50_EMA200";
        return "UPTREND";
    }
    if (h1.second < h0.second && l1.second < l0.second &&
        close < ema50 && close < ema200) {
        reason = "LOWER_HIGH_LOWER_LOW_AND_CLOSE_BELOW_EMA50_EMA200";
        return "DOWNTREND";
    }
    const auto atr = atr14(bars, bars.size() - 1U);
    if (atr) {
        double highest = -std::numeric_limits<double>::infinity();
        double lowest = std::numeric_limits<double>::infinity();
        for (std::size_t i = bars.size() - 20U; i < bars.size(); ++i) {
            highest = std::max(highest, bars[i].high);
            lowest = std::min(lowest, bars[i].low);
        }
        if ((highest - lowest) <= 8.0 * *atr &&
            std::abs(ema50 - ema200) <= *atr) {
            reason = "20_BAR_RANGE_WITH_COMPRESSED_EMA_SPREAD";
            return "RANGE";
        }
    }
    reason = "STRUCTURE_AND_TREND_FILTERS_DISAGREE";
    return "TRANSITION";
}

inline Result calculate(const std::string& symbol,
                        const nlohmann::json& hourly_candles,
                        std::int64_t decision_time_ms) {
    Result result{};
    result.symbol = symbol;
    result.as_of_ms = decision_time_ms;
    const auto bars = aggregate_4h(hourly_candles, decision_time_ms);
    if (bars.size() < 220U) {
        result.phase_reason = "INSUFFICIENT_CLOSED_4H_HISTORY";
        return result;
    }
    result.current_price = bars.back().close;

    std::vector<std::pair<std::size_t, double>> swing_highs;
    std::vector<std::pair<std::size_t, double>> swing_lows;
    for (std::size_t i = 2U; i + 2U < bars.size(); ++i) {
        const auto confirmed_at = bars[i + 2U].available_at_ms;
        if (confirmed_at > decision_time_ms) continue;
        if (pivot_high(bars, i)) swing_highs.emplace_back(i, bars[i].high);
        if (pivot_low(bars, i)) swing_lows.emplace_back(i, bars[i].low);
    }

    constexpr double min_wick_ratio = 0.35;
    constexpr double min_volume_ratio = 1.20;
    constexpr double min_zone_atr = 0.15;
    constexpr double invalidation_atr = 0.25;
    for (std::size_t i = 22U; i + 2U < bars.size(); ++i) {
        const auto confirmed_at = bars[i + 2U].available_at_ms;
        if (confirmed_at > decision_time_ms) continue;
        const auto atr = atr14(bars, i);
        const auto median_volume = median_prior_volume(bars, i);
        if (!atr || !median_volume) continue;
        const double volume_ratio = bars[i].volume_quote / *median_volume;
        const double range = bars[i].high - bars[i].low;
        if (range <= 0.0 || !std::isfinite(volume_ratio)) continue;

        const double body_high = std::max(bars[i].open, bars[i].close);
        const double body_low = std::min(bars[i].open, bars[i].close);
        if (pivot_high(bars, i)) {
            const double wick = (bars[i].high - body_high) / range;
            if (wick >= min_wick_ratio && volume_ratio >= min_volume_ratio) {
                Zone zone{};
                zone.side = "SUPPLY";
                zone.high = bars[i].high;
                zone.low = body_high;
                if (zone.high - zone.low < min_zone_atr * *atr)
                    zone.low = zone.high - min_zone_atr * *atr;
                zone.wick_ratio = wick;
                zone.volume_ratio = volume_ratio;
                zone.atr = *atr;
                zone.pivot_time_ms = bars[i].timestamp_ms;
                zone.confirmed_at_ms = confirmed_at;
                zone.id = symbol + "|4H|SUPPLY|" + std::to_string(zone.pivot_time_ms);
                for (std::size_t j = i + 3U; j < bars.size(); ++j) {
                    if (bars[j].available_at_ms > decision_time_ms) break;
                    if (bars[j].high >= zone.low && bars[j].low <= zone.high)
                        ++zone.touch_count;
                    if (bars[j].close > zone.high + invalidation_atr * zone.atr) {
                        zone.status = "INVALIDATED";
                        zone.invalidated_at_ms = bars[j].available_at_ms;
                        break;
                    }
                }
                result.zones.push_back(zone);
            }
        }
        if (pivot_low(bars, i)) {
            const double wick = (body_low - bars[i].low) / range;
            if (wick >= min_wick_ratio && volume_ratio >= min_volume_ratio) {
                Zone zone{};
                zone.side = "DEMAND";
                zone.low = bars[i].low;
                zone.high = body_low;
                if (zone.high - zone.low < min_zone_atr * *atr)
                    zone.high = zone.low + min_zone_atr * *atr;
                zone.wick_ratio = wick;
                zone.volume_ratio = volume_ratio;
                zone.atr = *atr;
                zone.pivot_time_ms = bars[i].timestamp_ms;
                zone.confirmed_at_ms = confirmed_at;
                zone.id = symbol + "|4H|DEMAND|" + std::to_string(zone.pivot_time_ms);
                for (std::size_t j = i + 3U; j < bars.size(); ++j) {
                    if (bars[j].available_at_ms > decision_time_ms) break;
                    if (bars[j].high >= zone.low && bars[j].low <= zone.high)
                        ++zone.touch_count;
                    if (bars[j].close < zone.low - invalidation_atr * zone.atr) {
                        zone.status = "INVALIDATED";
                        zone.invalidated_at_ms = bars[j].available_at_ms;
                        break;
                    }
                }
                result.zones.push_back(zone);
            }
        }
    }

    result.phase = classify_phase(bars, swing_highs, swing_lows, result.phase_reason);
    result.status = "AVAILABLE";
    double support_distance = std::numeric_limits<double>::infinity();
    double resistance_distance = std::numeric_limits<double>::infinity();
    for (const auto& zone : result.zones) {
        if (zone.status != "ACTIVE") continue;
        if (zone.side == "DEMAND" && zone.high <= result.current_price) {
            const double distance = result.current_price - zone.high;
            if (distance < support_distance) {
                support_distance = distance;
                result.nearest_support = zone;
            }
        }
        if (zone.side == "SUPPLY" && zone.low >= result.current_price) {
            const double distance = zone.low - result.current_price;
            if (distance < resistance_distance) {
                resistance_distance = distance;
                result.nearest_resistance = zone;
            }
        }
    }
    return result;
}

inline nlohmann::json to_json(const Result& result) {
    using json = nlohmann::json;
    json zones = json::array();
    for (const auto& zone : result.zones) {
        zones.push_back({
            {"id", zone.id}, {"side", zone.side},
            {"low", zone.low}, {"high", zone.high},
            {"wick_ratio", zone.wick_ratio},
            {"volume_ratio", zone.volume_ratio},
            {"atr14", zone.atr},
            {"pivot_time_ms", zone.pivot_time_ms},
            {"confirmed_at_ms", zone.confirmed_at_ms},
            {"invalidated_at_ms", zone.invalidated_at_ms},
            {"touch_count", zone.touch_count},
            {"status", zone.status},
            {"source_quality", "REAL"},
            {"timeframe", "4H"}
        });
    }
    const auto optional_zone = [](const std::optional<Zone>& zone) -> json {
        if (!zone) return nullptr;
        return {{"id", zone->id}, {"low", zone->low}, {"high", zone->high},
                {"distance_from_price", zone->side == "DEMAND" ? 0.0 : 0.0},
                {"side", zone->side}, {"confirmed_at_ms", zone->confirmed_at_ms}};
    };
    return {
        {"symbol", result.symbol},
        {"status", result.status},
        {"phase", result.phase},
        {"phase_reason", result.phase_reason},
        {"as_of_ms", result.as_of_ms},
        {"current_price", result.current_price},
        {"zones", zones},
        {"nearest_support", optional_zone(result.nearest_support)},
        {"nearest_resistance", optional_zone(result.nearest_resistance)},
        {"actionable", false}
    };
}

} // namespace cfss::liquidity
