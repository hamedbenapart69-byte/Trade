#pragma once

#include "cfss/liquidity_phase.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <limits>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::engines {

struct Candidate {
    std::string path;
    std::string status{"NO_QUALIFIED_SETUP"};
    std::string direction{"NONE"};
    std::optional<double> score;
    std::string data_class{"UNAVAILABLE"};
    std::string hypothesis;
    std::string falsification;
    std::string reason;
    std::string horizon;
    std::optional<double> entry_reference;
    std::optional<double> invalidation_reference;
    std::optional<double> target_reference;
    std::int64_t decision_time_ms{};
    std::string confidence_status{"NOT_CALIBRATED"};
    bool actionable{false};
};

struct Result {
    std::string symbol;
    std::int64_t decision_time_ms{};
    bool golden_rule_evaluated{};
    bool golden_rule_veto{};
    std::optional<double> lfs_score;
    std::optional<double> nss_long_score;
    std::optional<double> nss_short_score;
    Candidate lrt;
    Candidate nmt;
};

inline std::optional<double> numeric(const nlohmann::json& object, const char* key) {
    if (!object.is_object() || !object.contains(key) || !object.at(key).is_number())
        return std::nullopt;
    const double value = object.at(key).get<double>();
    return std::isfinite(value) ? std::optional<double>{value} : std::nullopt;
}

inline std::optional<double> direction_score(const nlohmann::json& nss,
                                             const char* key) {
    if (!nss.is_object() || !nss.contains(key) || !nss.at(key).is_object() ||
        nss.at(key).value("status", std::string{}) != "CALCULATED") return std::nullopt;
    const auto coverage = nss.at(key).value("component_coverage", nlohmann::json::object());
    if (coverage.value("available_scores", 0) != 5 ||
        coverage.value("required_scores", 0) != 5) return std::nullopt;
    return numeric(nss.at(key), "score");
}

inline std::optional<double> nss_component_score(const nlohmann::json& direction,
                                                  const std::string& component_id) {
    if (!direction.contains("components") || !direction.at("components").is_array())
        return std::nullopt;
    for (const auto& component : direction.at("components")) {
        if (component.value("id", std::string{}) == component_id)
            return numeric(component, "score");
    }
    return std::nullopt;
}

inline std::optional<cfss::liquidity::Bar4H> last_closed_bar(
    const nlohmann::json& hourly, std::int64_t decision_time_ms) {
    const auto bars = cfss::liquidity::aggregate_4h(hourly, decision_time_ms);
    if (bars.empty()) return std::nullopt;
    return bars.back();
}

inline std::optional<double> latest_closed_hourly_close(
    const nlohmann::json& instrument, std::int64_t decision_time_ms) {
    if (!instrument.contains("candles") || !instrument.at("candles").is_array())
        return std::nullopt;
    std::optional<std::pair<std::int64_t, double>> latest;
    for (const auto& candle : instrument.at("candles")) {
        if (!candle.value("closed", false)) continue;
        const auto ts = candle.value("timestamp_ms", std::int64_t{0});
        if (ts <= 0 || ts + 3'600'000LL > decision_time_ms) continue;
        const auto close = numeric(candle, "close");
        if (!close || *close <= 0.0) continue;
        if (!latest || ts > latest->first) latest = std::make_pair(ts, *close);
    }
    return latest ? std::optional<double>{latest->second} : std::nullopt;
}

inline double median_prior_4h_volume(const std::vector<cfss::liquidity::Bar4H>& bars) {
    if (bars.size() < 21U) return 0.0;
    std::vector<double> volumes;
    volumes.reserve(20U);
    for (std::size_t i = bars.size() - 21U; i < bars.size() - 1U; ++i)
        volumes.push_back(bars[i].volume_quote);
    std::sort(volumes.begin(), volumes.end());
    return (volumes[9U] + volumes[10U]) / 2.0;
}

inline Candidate build_lrt(const nlohmann::json& instrument,
                           const nlohmann::json& lfs,
                           const nlohmann::json& liquidity,
                           std::int64_t decision_time_ms) {
    Candidate result{};
    result.path = "PLAN_A_LRT";
    result.horizon = "30m-4h";
    result.decision_time_ms = decision_time_ms;
    result.reason = "NO_CONFIRMED_LIQUIDITY_SWEEP_RECLAIM";

    if (lfs.value("status", std::string{}) != "CALCULATED" ||
        lfs.value("component_coverage", nlohmann::json::object()).value("available_scores", 0) != 5 ||
        lfs.value("component_coverage", nlohmann::json::object()).value("required_scores", 0) != 5) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "LFS_5_OF_5_REQUIRED";
        return result;
    }
    const auto lfs_score = numeric(lfs, "score");
    if (!lfs_score || *lfs_score < 0.0 || *lfs_score > 1.0 ||
        liquidity.value("status", std::string{}) != "AVAILABLE" ||
        !liquidity.contains("zones") || !liquidity.at("zones").is_array()) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "LFS_OR_LIQUIDITY_INPUT_INVALID";
        return result;
    }
    const auto bars = cfss::liquidity::aggregate_4h(
        instrument.value("candles", nlohmann::json::array()), decision_time_ms);
    if (bars.size() < 21U) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "INSUFFICIENT_4H_BARS";
        return result;
    }
    const auto& last = bars.back();
    const double median_volume = median_prior_4h_volume(bars);
    if (median_volume <= 0.0) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "VOLUME_REFERENCE_UNAVAILABLE";
        return result;
    }
    const double volume_ratio = last.volume_quote / median_volume;
    result.score = lfs_score;
    result.data_class = lfs.value("data_class", std::string{"PROXY"});

    std::optional<nlohmann::json> long_sweep;
    std::optional<nlohmann::json> short_sweep;
    for (const auto& zone : liquidity.at("zones")) {
        if (zone.value("status", std::string{}) != "ACTIVE" ||
            zone.value("confirmed_at_ms", std::int64_t{0}) >= last.available_at_ms) continue;
        const auto low = numeric(zone, "low");
        const auto high = numeric(zone, "high");
        if (!low || !high || *low >= *high) continue;
        if (zone.value("side", std::string{}) == "DEMAND" &&
            last.low < *low && last.close > *high && volume_ratio >= 1.20) {
            if (!long_sweep || *high > long_sweep->at("high").get<double>())
                long_sweep = zone;
        }
        if (zone.value("side", std::string{}) == "SUPPLY" &&
            last.high > *high && last.close < *low && volume_ratio >= 1.20) {
            if (!short_sweep || *low < short_sweep->at("low").get<double>())
                short_sweep = zone;
        }
    }

    if (long_sweep && short_sweep) {
        result.status = "NO_QUALIFIED_SETUP";
        result.reason = "AMBIGUOUS_LONG_AND_SHORT_SWEEP";
        return result;
    }
    if (!long_sweep && !short_sweep) return result;

    const auto current_entry = latest_closed_hourly_close(instrument, decision_time_ms);
    if (!current_entry) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "LATEST_CLOSED_1H_ENTRY_REFERENCE_UNAVAILABLE";
        return result;
    }
    result.status = "CANDIDATE";
    result.direction = long_sweep ? "LONG" : "SHORT";
    result.entry_reference = *current_entry;
    if (long_sweep) {
        const auto sweep_low = last.low;
        result.invalidation_reference = sweep_low;
        if (liquidity.contains("nearest_resistance") && liquidity.at("nearest_resistance").is_object())
            result.target_reference = numeric(liquidity.at("nearest_resistance"), "low");
        result.hypothesis = "A closed 4H candle swept below an ACTIVE confirmed demand zone and reclaimed above its upper boundary; LFS=" +
            std::to_string(*lfs_score) + "; 4H volume_ratio=" + std::to_string(volume_ratio) +
            ". A 30m-4h liquidity reversion is testable.";
        result.falsification = "A subsequent closed 4H candle closes below the sweep low or the demand zone is invalidated.";
    } else {
        const auto sweep_high = last.high;
        result.invalidation_reference = sweep_high;
        if (liquidity.contains("nearest_support") && liquidity.at("nearest_support").is_object())
            result.target_reference = numeric(liquidity.at("nearest_support"), "high");
        result.hypothesis = "A closed 4H candle swept above an ACTIVE confirmed supply zone and closed below its lower boundary; LFS=" +
            std::to_string(*lfs_score) + "; 4H volume_ratio=" + std::to_string(volume_ratio) +
            ". A 30m-4h liquidity reversion is testable.";
        result.falsification = "A subsequent closed 4H candle closes above the sweep high or the supply zone is invalidated.";
    }
    result.reason = "CONFIRMED_SWEEP_RECLAIM_WITH_VOLUME";
    return result;
}

inline Candidate build_nmt(const nlohmann::json& instrument,
                           const nlohmann::json& nss,
                           const nlohmann::json& liquidity,
                           std::int64_t decision_time_ms) {
    Candidate result{};
    result.path = "PLAN_A_NMT";
    result.horizon = "1-7d";
    result.decision_time_ms = decision_time_ms;
    result.reason = "NO_TREND_BREAKOUT_WITH_VOLUME";

    if (liquidity.value("status", std::string{}) != "AVAILABLE" ||
        nss.value("status", std::string{}) == "UNAVAILABLE") {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "NSS_OR_PHASE_INPUT_UNAVAILABLE";
        return result;
    }
    const auto phase = liquidity.value("phase", std::string{"UNAVAILABLE"});
    const bool long_phase = phase == "UPTREND";
    const bool short_phase = phase == "DOWNTREND";
    if (!long_phase && !short_phase) {
        result.reason = "PHASE_NOT_DIRECTIONAL";
        return result;
    }
    const auto score = direction_score(nss, long_phase ? "nss_long" : "nss_short");
    if (!score || *score < 0.0 || *score > 1.0) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "NSS_DIRECTIONAL_SCORE_UNAVAILABLE";
        return result;
    }

    result.score = score;
    result.data_class = nss.value("data_class", std::string{"PROXY"});
    result.direction = long_phase ? "LONG" : "SHORT";

    const auto bars = cfss::liquidity::aggregate_4h(
        instrument.value("candles", nlohmann::json::array()), decision_time_ms);
    if (bars.size() < 21U) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "INSUFFICIENT_4H_BARS";
        return result;
    }
    const auto& last = bars.back();
    const double median_volume = median_prior_4h_volume(bars);
    if (median_volume <= 0.0) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "VOLUME_REFERENCE_UNAVAILABLE";
        return result;
    }
    const double volume_ratio = last.volume_quote / median_volume;
    double prior_high = -std::numeric_limits<double>::infinity();
    double prior_low = std::numeric_limits<double>::infinity();
    for (std::size_t i = bars.size() - 21U; i < bars.size() - 1U; ++i) {
        prior_high = std::max(prior_high, bars[i].high);
        prior_low = std::min(prior_low, bars[i].low);
    }
    const bool breakout = long_phase ? last.close > prior_high : last.close < prior_low;
    if (!breakout || volume_ratio < 1.20) return result;

    const auto current_entry = latest_closed_hourly_close(instrument, decision_time_ms);
    if (!current_entry) {
        result.status = "INSUFFICIENT_DATA";
        result.reason = "LATEST_CLOSED_1H_ENTRY_REFERENCE_UNAVAILABLE";
        return result;
    }
    result.status = "CANDIDATE";
    result.entry_reference = *current_entry;
    result.invalidation_reference = long_phase ? prior_high : prior_low;
    if (long_phase && liquidity.contains("nearest_resistance") && liquidity.at("nearest_resistance").is_object())
        result.target_reference = numeric(liquidity.at("nearest_resistance"), "low");
    if (short_phase && liquidity.contains("nearest_support") && liquidity.at("nearest_support").is_object())
        result.target_reference = numeric(liquidity.at("nearest_support"), "high");
    result.hypothesis = std::string{"A "} + phase + " structure has a 20-bar 4H breakout with volume_ratio=" +
        std::to_string(volume_ratio) + " and directional NSS=" + std::to_string(*score) +
        ". A 1-7d narrative-momentum continuation is testable using market-derived participation proxies.";
    result.falsification = long_phase
        ? "A subsequent 4H close returns below the 20-bar breakout level or the phase is no longer UPTREND."
        : "A subsequent 4H close returns above the 20-bar breakout level or the phase is no longer DOWNTREND.";
    result.reason = "DIRECTIONAL_PHASE_20_BAR_BREAKOUT_VOLUME_CONFIRMATION";
    return result;
}

inline Result evaluate(const std::string& symbol,
                       const nlohmann::json& instrument,
                       const nlohmann::json& lfs,
                       const nlohmann::json& nss,
                       const nlohmann::json& liquidity,
                       std::int64_t decision_time_ms) {
    Result result{};
    result.symbol = symbol;
    result.decision_time_ms = decision_time_ms;
    result.lfs_score = numeric(lfs, "score");
    result.nss_long_score = direction_score(nss, "nss_long");
    result.nss_short_score = direction_score(nss, "nss_short");
    const bool scores_ready = lfs.value("status", std::string{}) == "CALCULATED" &&
        result.lfs_score.has_value() && result.nss_long_score.has_value() &&
        result.nss_short_score.has_value();
    result.golden_rule_evaluated = scores_ready;
    result.golden_rule_veto = scores_ready && *result.lfs_score > 0.70 &&
        std::max(*result.nss_long_score, *result.nss_short_score) > 0.70;

    if (!scores_ready) {
        result.lrt.path = "PLAN_A_LRT";
        result.lrt.horizon = "30m-4h";
        result.lrt.decision_time_ms = decision_time_ms;
        result.lrt.status = "INSUFFICIENT_DATA";
        result.lrt.reason = "GOLDEN_RULE_INPUTS_REQUIRE_LFS_AND_BOTH_NSS_DIRECTIONS";
        result.nmt.path = "PLAN_A_NMT";
        result.nmt.horizon = "1-7d";
        result.nmt.decision_time_ms = decision_time_ms;
        result.nmt.status = "INSUFFICIENT_DATA";
        result.nmt.reason = "GOLDEN_RULE_INPUTS_REQUIRE_LFS_AND_BOTH_NSS_DIRECTIONS";
        return result;
    }

    result.lrt = build_lrt(instrument, lfs, liquidity, decision_time_ms);
    result.nmt = build_nmt(instrument, nss, liquidity, decision_time_ms);
    if (result.golden_rule_veto) {
        for (Candidate* candidate : {&result.lrt, &result.nmt}) {
            candidate->status = "GOLDEN_RULE_NO_TRADE";
            candidate->direction = "NONE";
            candidate->entry_reference.reset();
            candidate->invalidation_reference.reset();
            candidate->target_reference.reset();
            candidate->reason = "HARD_VETO_LFS_GT_0_70_AND_NSS_GT_0_70";
            candidate->hypothesis = "The simultaneous LFS/NSS threshold condition activates the mandatory no-trade veto.";
            candidate->falsification = "Not applicable: this is a deterministic policy veto, not a market hypothesis.";
        }
    }
    return result;
}

inline nlohmann::json candidate_json(const Candidate& candidate) {
    using json = nlohmann::json;
    return {
        {"path", candidate.path},
        {"status", candidate.status},
        {"direction", candidate.direction},
        {"score", candidate.score ? json(*candidate.score) : json(nullptr)},
        {"data_class", candidate.data_class},
        {"hypothesis", candidate.hypothesis},
        {"falsification", candidate.falsification},
        {"reason", candidate.reason},
        {"horizon", candidate.horizon},
        {"entry_reference", candidate.entry_reference ? json(*candidate.entry_reference) : json(nullptr)},
        {"invalidation_reference", candidate.invalidation_reference ? json(*candidate.invalidation_reference) : json(nullptr)},
        {"target_reference", candidate.target_reference ? json(*candidate.target_reference) : json(nullptr)},
        {"decision_time_ms", candidate.decision_time_ms},
        {"confidence_status", candidate.confidence_status},
        {"actionable", candidate.actionable}
    };
}

inline nlohmann::json to_json(const Result& result) {
    return {
        {"symbol", result.symbol},
        {"decision_time_ms", result.decision_time_ms},
        {"lfs_score", result.lfs_score ? nlohmann::json(*result.lfs_score) : nlohmann::json(nullptr)},
        {"nss_long_score", result.nss_long_score ? nlohmann::json(*result.nss_long_score) : nlohmann::json(nullptr)},
        {"nss_short_score", result.nss_short_score ? nlohmann::json(*result.nss_short_score) : nlohmann::json(nullptr)},
        {"golden_rule", {
            {"evaluated", result.golden_rule_evaluated},
            {"veto", result.golden_rule_veto},
            {"condition", "LFS > 0.70 AND max(NSS_LONG,NSS_SHORT) > 0.70"},
            {"decision", result.golden_rule_veto ? "NO_TRADE" : "NOT_TRIGGERED"}
        }},
        {"lrt", candidate_json(result.lrt)},
        {"nmt", candidate_json(result.nmt)}
    };
}

} // namespace cfss::engines
