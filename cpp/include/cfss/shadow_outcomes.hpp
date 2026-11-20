#pragma once

#include "cfss/hash.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>
#include <utility>
#include <vector>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

namespace cfss::shadow {
using json = nlohmann::json;
constexpr std::int64_t kOneHourMs = 3'600'000LL;

inline const json* find_instrument(const json& l1, const std::string& symbol) {
    if (!l1.contains("instruments") || !l1.at("instruments").is_array()) return nullptr;
    for (const auto& item : l1.at("instruments")) {
        if (item.value("unified_symbol", std::string{}) == symbol ||
            item.value("symbol", std::string{}) == symbol) return &item;
    }
    return nullptr;
}

inline const json* find_phase(const json& liquidity, const std::string& symbol) {
    if (!liquidity.contains("instruments") || !liquidity.at("instruments").is_array()) return nullptr;
    for (const auto& item : liquidity.at("instruments"))
        if (item.value("symbol", std::string{}) == symbol) return &item;
    return nullptr;
}

inline double required_number(const json& value, const char* key) {
    if (!value.contains(key) || !value.at(key).is_number())
        throw std::runtime_error(std::string{"shadow_candidate_missing_numeric:"} + key);
    const double result = value.at(key).get<double>();
    if (!std::isfinite(result)) throw std::runtime_error(std::string{"shadow_candidate_nonfinite:"} + key);
    return result;
}

constexpr double kShadowFeeRatePerSide = 0.0004;
constexpr double kShadowSlippageRatePerSide = 0.0010;
constexpr std::int64_t kFundingCoverageToleranceMs = 8LL * kOneHourMs;

struct ShadowCostResult {
    bool available{false};
    double fee_r{};
    double slippage_r{};
    double funding_r{};
};

inline ShadowCostResult calculate_shadow_costs(
    const json& instrument,
    const std::string& direction,
    double entry_fill,
    double stop,
    std::int64_t entry_time_ms,
    std::int64_t close_time_ms) {
    ShadowCostResult result{};
    if ((direction != "LONG" && direction != "SHORT") ||
        !std::isfinite(entry_fill) || entry_fill <= 0.0 ||
        !std::isfinite(stop) || stop <= 0.0 ||
        entry_time_ms <= 0 || close_time_ms < entry_time_ms)
        return result;

    const double risk_fraction = std::abs(entry_fill - stop) / entry_fill;
    if (!std::isfinite(risk_fraction) || risk_fraction <= 1e-9) return result;

    const auto availability = instrument.value("availability", json::object());
    if (availability.value("funding", std::string{"UNAVAILABLE"}) != "AVAILABLE" ||
        !instrument.contains("funding") || !instrument.at("funding").is_array() ||
        instrument.at("funding").empty())
        return result;

    std::int64_t first_time = std::numeric_limits<std::int64_t>::max();
    std::int64_t last_time = 0;
    std::int64_t previous_time = 0;
    std::vector<std::int64_t> funding_gaps;
    double signed_funding_sum = 0.0;
    for (const auto& row : instrument.at("funding")) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer() ||
            !row.contains("funding_rate") || !row.at("funding_rate").is_number())
            return result;
        const auto timestamp = row.at("timestamp_ms").get<std::int64_t>();
        const double rate = row.at("funding_rate").get<double>();
        if (timestamp <= 0 || !std::isfinite(rate) || timestamp < previous_time)
            return result;
        if (previous_time > 0 && timestamp > previous_time)
            funding_gaps.push_back(timestamp - previous_time);
        previous_time = timestamp;
        first_time = std::min(first_time, timestamp);
        last_time = std::max(last_time, timestamp);
        if (timestamp >= entry_time_ms && timestamp <= close_time_ms)
            signed_funding_sum += rate * (direction == "LONG" ? 1.0 : -1.0);
    }

    if (funding_gaps.empty()) return result;
    std::sort(funding_gaps.begin(), funding_gaps.end());
    const auto expected_interval_ms = std::min(
        funding_gaps[funding_gaps.size() / 2U], kFundingCoverageToleranceMs);
    const auto maximum_gap_ms = std::min(
        kFundingCoverageToleranceMs, expected_interval_ms + expected_interval_ms / 2);

    // شکاف بزرگ‌تر از یک‌ونیم دوره، پوشش ناقص است و هزینه funding نباید صفر فرض شود.
    if (first_time > entry_time_ms ||
        last_time + expected_interval_ms < close_time_ms ||
        std::any_of(funding_gaps.begin(), funding_gaps.end(),
            [maximum_gap_ms](std::int64_t gap) { return gap > maximum_gap_ms; }))
        return result;

    result.fee_r = (2.0 * kShadowFeeRatePerSide) / risk_fraction;
    result.slippage_r = (2.0 * kShadowSlippageRatePerSide) / risk_fraction;
    result.funding_r = signed_funding_sum / risk_fraction;
    result.available = std::isfinite(result.fee_r) &&
        std::isfinite(result.slippage_r) && std::isfinite(result.funding_r) &&
        result.fee_r >= 0.0 && result.slippage_r >= 0.0;
    return result;
}

inline void apply_shadow_costs(
    json& outcome,
    const json& instrument,
    const std::string& source_run_id,
    const std::string& source_scan_id,
    const std::string& source_l1_sha256,
    std::int64_t cost_as_of_time_ms) {
    const bool valid_hash = source_l1_sha256.size() == 64U &&
        std::all_of(source_l1_sha256.begin(), source_l1_sha256.end(), [](unsigned char c) {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        });
    if (source_run_id.empty() || source_scan_id.empty() || !valid_hash) return;

    const auto direction = outcome.value("direction", std::string{});
    const auto entry = outcome.value("entry_fill_reference", json{});
    const auto stop = outcome.value("stop_reference", json{});
    const auto decision = outcome.value("decision_time_ms", std::int64_t{0});
    const auto closed = outcome.value("closed_at_ms", std::int64_t{0});
    std::int64_t entry_time = decision;
    if (outcome.contains("resolution_bars") && outcome.at("resolution_bars").is_array() &&
        !outcome.at("resolution_bars").empty())
        entry_time = outcome.at("resolution_bars").front().value("timestamp_ms", decision);

    if (!entry.is_number() || !stop.is_number()) return;
    const auto costs = calculate_shadow_costs(
        instrument, direction, entry.get<double>(), stop.get<double>(), entry_time, closed);
    if (!costs.available) return;

    outcome["fee_r"] = costs.fee_r;
    outcome["slippage_r"] = costs.slippage_r;
    outcome["funding_r"] = costs.funding_r;
    outcome["cost_status"] = "PROXY";
    outcome["cost_model_id"] = "SHADOW_COST_PROXY_V1";
    outcome["fee_rate_per_side"] = kShadowFeeRatePerSide;
    outcome["fee_assumption_class"] = "ASSUMED";
    outcome["fee_assumption_ref"] = "OWNER_ENGINEERING_DECISION_2026-11-20";
    outcome["slippage_rate_per_side"] = kShadowSlippageRatePerSide;
    outcome["slippage_assumption_class"] = "PROXY";
    outcome["slippage_proxy_method"] = "FIXED_RATE_NOT_MEASURED_FROM_ORDER_BOOK";
    outcome["slippage_source_status"] = "UNAVAILABLE_MARKET_IMPACT_MEASUREMENT";
    outcome["funding_source"] = "OKX_PUBLIC_FUNDING_HISTORY";
    outcome["cost_source_run_id"] = source_run_id;
    outcome["cost_source_scan_id"] = source_scan_id;
    outcome["cost_source_l1_sha256"] = source_l1_sha256;
    outcome["cost_as_of_time_ms"] = cost_as_of_time_ms;
}

inline bool valid_cost_provenance(const json& outcome) {
    const auto status = outcome.value("cost_status", std::string{"UNAVAILABLE"});
    const auto is_null_or_missing = [&outcome](const char* key) {
        return !outcome.contains(key) || outcome.at(key).is_null();
    };
    if (status == "UNAVAILABLE") {
        return is_null_or_missing("fee_r") &&
            is_null_or_missing("slippage_r") &&
            is_null_or_missing("funding_r");
    }
    if (status != "PROXY") return false; // REAL costs are not implemented in this stage.
    const auto finite_number = [&outcome](const char* key) {
        return outcome.contains(key) && outcome.at(key).is_number() &&
            std::isfinite(outcome.at(key).get<double>());
    };
    const auto nonempty_string = [&outcome](const char* key) {
        return outcome.contains(key) && outcome.at(key).is_string() &&
            !outcome.at(key).get<std::string>().empty();
    };
    const auto hash = outcome.value("cost_source_l1_sha256", std::string{});
    const bool valid_hash = hash.size() == 64U &&
        std::all_of(hash.begin(), hash.end(), [](unsigned char ch) {
            return (ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f');
        });
    return finite_number("fee_r") && outcome.at("fee_r").get<double>() >= 0.0 &&
        finite_number("slippage_r") && outcome.at("slippage_r").get<double>() >= 0.0 &&
        finite_number("funding_r") &&
        finite_number("fee_rate_per_side") &&
        std::abs(outcome.at("fee_rate_per_side").get<double>() - kShadowFeeRatePerSide) < 1e-12 &&
        outcome.value("fee_assumption_class", std::string{}) == "ASSUMED" &&
        outcome.value("fee_assumption_ref", std::string{}) == "OWNER_ENGINEERING_DECISION_2026-11-20" &&
        finite_number("slippage_rate_per_side") &&
        std::abs(outcome.at("slippage_rate_per_side").get<double>() - kShadowSlippageRatePerSide) < 1e-12 &&
        outcome.value("slippage_assumption_class", std::string{}) == "PROXY" &&
        outcome.value("slippage_proxy_method", std::string{}) == "FIXED_RATE_NOT_MEASURED_FROM_ORDER_BOOK" &&
        outcome.value("slippage_source_status", std::string{}) == "UNAVAILABLE_MARKET_IMPACT_MEASUREMENT" &&
        outcome.value("cost_model_id", std::string{}) == "SHADOW_COST_PROXY_V1" &&
        outcome.value("funding_source", std::string{}) == "OKX_PUBLIC_FUNDING_HISTORY" &&
        nonempty_string("cost_source_run_id") && nonempty_string("cost_source_scan_id") &&
        valid_hash && outcome.contains("cost_as_of_time_ms") &&
        outcome.at("cost_as_of_time_ms").is_number_integer() &&
        outcome.at("cost_as_of_time_ms").get<std::int64_t>() >=
            outcome.value("closed_at_ms", std::int64_t{0});
}

inline json empty_registry() {
    return {
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_shadow_candidate_registry_v1"},
        {"candidates", json::array()}
    };
}

inline json empty_ledger() {
    return {
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_outcome_ledger_v1"},
        {"profile", "DAILY_SWING"},
        {"ledger_status", "EMPTY"},
        {"outcomes", json::array()}
    };
}

inline json process(const json& l1, const json& l1_15m, const json& dual, const json& liquidity,
                    json registry, json ledger) {
    if (l1.value("schema_version", std::string{}) != "1.0.0" ||
        l1_15m.value("artifact_type", std::string{}) != "cfss_intraday_15m_market_data_v1" ||
        dual.value("artifact_type", std::string{}) != "cfss_dual_engine_report_v1" ||
        liquidity.value("artifact_type", std::string{}) != "cfss_liquidity_phase_v1")
        throw std::runtime_error("shadow_input_artifact_type_mismatch");
    if (l1.value("window", json::object()).value("timeframe", std::string{}) != "1h")
        throw std::runtime_error("shadow_resolver_requires_1h_closed_candles");

    const auto decision_time = dual.value("decision_time_ms", std::int64_t{0});
    const auto current_time = l1.value("window", json::object()).value("end_ms", std::int64_t{0});
    if (decision_time <= 0 || current_time < decision_time ||
        dual.value("source_run_id", std::string{}) != l1.value("run_id", std::string{}) ||
        dual.value("source_scan_id", std::string{}) != l1.value("scan_id", std::string{}) ||
        liquidity.value("source_run_id", std::string{}) != dual.value("source_run_id", std::string{}) ||
        liquidity.value("source_scan_id", std::string{}) != dual.value("source_scan_id", std::string{}) ||
        liquidity.value("decision_time_ms", std::int64_t{0}) != decision_time ||
        liquidity.value("l1_sha256", std::string{}) != dual.value("l1_sha256", std::string{}) ||
        l1_15m.value("source_run_id", std::string{}) != dual.value("source_run_id", std::string{}) ||
        l1_15m.value("source_scan_id", std::string{}) != dual.value("source_scan_id", std::string{}) ||
        l1_15m.value("source_l1_sha256", std::string{}) != dual.value("l1_sha256", std::string{}) ||
        l1_15m.value("window", json::object()).value("timeframe", std::string{}) != "15m" ||
        l1_15m.value("window", json::object()).value("end_ms", std::int64_t{0}) != current_time ||
        !l1_15m.contains("instruments") || !l1_15m.at("instruments").is_array() ||
        l1_15m.value("candles_sha256", std::string{}).size() != 64U ||
        cfss::sha256_hex(l1_15m.at("instruments").dump()) !=
            l1_15m.value("candles_sha256", std::string{}))
        throw std::runtime_error("shadow_cross_artifact_provenance_mismatch");

    if (registry.is_null() || registry.empty()) registry = empty_registry();
    if (ledger.is_null() || ledger.empty()) ledger = empty_ledger();
    if (registry.value("artifact_type", std::string{}) != "cfss_shadow_candidate_registry_v1" ||
        !registry.contains("candidates") || !registry.at("candidates").is_array() ||
        ledger.value("artifact_type", std::string{}) != "cfss_outcome_ledger_v1" ||
        ledger.value("profile", std::string{}) != "DAILY_SWING" ||
        !ledger.contains("outcomes") || !ledger.at("outcomes").is_array())
        throw std::runtime_error("shadow_state_artifact_invalid");

    const bool universe_verified = l1.contains("crypto_universe") &&
        l1.at("crypto_universe").value("status", std::string{}) == "VERIFIED" &&
        l1.at("crypto_universe").value("provider_id", std::string{}) == "coinpaprika";
    std::size_t registered = 0U;
    std::size_t rejected = 0U;
    for (auto& old_candidate : registry["candidates"]) {
        if (old_candidate.value("state", std::string{}) != "PENDING") continue;
        const auto old_path = old_candidate.value("path", std::string{});
        if (!old_candidate.contains("score_model_version")) {
            old_candidate["score_model_version"] =
                old_path == "PLAN_A_LRT" ? "LFS_V2_PROXY" : "NSS_V2_PROXY";
        }
        const bool universe_unverified =
            old_candidate.value("source_universe_status", std::string{"UNVERIFIED"}) != "VERIFIED";
        const bool legacy_entry_contract =
            !old_candidate.contains("profile") ||
            !old_candidate.contains("entry_model") ||
            !old_candidate.contains("execution_status") ||
            !old_candidate.contains("entry_fill_reference");
        if (legacy_entry_contract) {
            old_candidate["profile"] = "DAILY_SWING";
            old_candidate["resolution_timeframe"] =
                old_path == "PLAN_A_LRT" ? "15m" : "1h";
            old_candidate["entry_fill_reference"] = nullptr;
            old_candidate["entry_fill_time_ms"] = nullptr;
            old_candidate["entry_model"] = "NEXT_BAR_OPEN_PROXY";
            old_candidate["execution_status"] = "NOT_EXECUTED";
            old_candidate["state"] = "REJECTED";
            old_candidate["skip_reason"] = universe_unverified
                ? "SOURCE_UNIVERSE_NOT_VERIFIED"
                : "LEGACY_CANDIDATE_QUARANTINED_AFTER_ENTRY_MODEL_CHANGE";
            ++rejected;
            continue;
        }
        if (universe_unverified) {
            old_candidate["state"] = "REJECTED";
            old_candidate["skip_reason"] = "SOURCE_UNIVERSE_NOT_VERIFIED";
            ++rejected;
        }
    }

    for (auto& old_outcome : ledger["outcomes"]) {
        if (!old_outcome.contains("score_model_version")) {
            const auto old_path = old_outcome.value("path", std::string{});
            old_outcome["score_model_version"] =
                old_path == "PLAN_A_LRT" ? "LFS_V2_PROXY" : "NSS_V2_PROXY";
        }
    }

    // بک‌فیل هزینه‌های نتایج قبلی؛ هزینه ناموجود هرگز صفر فرض نمی‌شود.
    std::size_t cost_backfilled = 0U;
    for (auto& old_outcome : ledger["outcomes"]) {
        if (old_outcome.value("cost_status", std::string{"UNAVAILABLE"}) != "UNAVAILABLE")
            continue;
        const auto symbol = old_outcome.value("symbol", std::string{});
        const auto* instrument = find_instrument(l1, symbol);
        if (!instrument) continue;
        apply_shadow_costs(old_outcome, *instrument,
            l1.value("run_id", std::string{}),
            l1.value("scan_id", std::string{}),
            dual.value("l1_sha256", std::string{}), current_time);
        if (old_outcome.value("cost_status", std::string{}) == "PROXY")
            ++cost_backfilled;
    }

    std::set<std::string> known_ids;
    for (const auto& item : registry.at("candidates"))
        known_ids.insert(item.value("signal_id", std::string{}));
    for (const auto& item : ledger.at("outcomes"))
        known_ids.insert(item.value("signal_id", std::string{}));

    for (const auto& instrument : dual.at("instruments")) {
        const auto symbol = instrument.value("symbol", std::string{});
        const auto* phase = find_phase(liquidity, symbol);
        if (symbol.empty() || !phase) continue;
        const auto regime = phase->value("phase", std::string{"UNKNOWN"});
        for (const auto* key : {"lrt", "nmt"}) {
            const auto& candidate = instrument.at(key);
            if (candidate.value("status", std::string{}) != "CANDIDATE") continue;
            if (!universe_verified) {
                ++rejected;
                continue;
            }
            const auto path = candidate.value("path", std::string{});
            const auto direction = candidate.value("direction", std::string{});
            const auto candidate_data_class = candidate.value("data_class", std::string{"UNAVAILABLE"});
            if (candidate_data_class != "REAL" && candidate_data_class != "PROXY") {
                ++rejected;
                continue;
            }
            if (!candidate.contains("score") || !candidate.at("score").is_number() ||
                !candidate.contains("entry_reference") || !candidate.at("entry_reference").is_number() ||
                !candidate.contains("invalidation_reference") || !candidate.at("invalidation_reference").is_number() ||
                !candidate.contains("target_reference") || !candidate.at("target_reference").is_number()) {
                ++rejected;
                continue;
            }
            const auto score = required_number(candidate, "score");
            const auto entry = required_number(candidate, "entry_reference");
            const auto stop = required_number(candidate, "invalidation_reference");
            const auto target = required_number(candidate, "target_reference");
            const auto candidate_time = candidate.value("decision_time_ms", std::int64_t{0});
            const bool levels_valid = direction == "LONG"
                ? stop < entry && entry < target
                : direction == "SHORT" && target < entry && entry < stop;
            if ((path != "PLAN_A_LRT" && path != "PLAN_A_NMT") ||
                (direction != "LONG" && direction != "SHORT") ||
                !levels_valid || candidate_time != decision_time ||
                score < 0.0 || score > 1.0 ||
                candidate.value("hypothesis", std::string{}).empty() ||
                candidate.value("falsification", std::string{}).empty()) {
                ++rejected;
                continue;
            }

            const auto horizon = path == "PLAN_A_LRT" ? 4LL * kOneHourMs : 7LL * 24LL * kOneHourMs;
            const auto scan_id = dual.value("source_scan_id", std::string{});
            const auto material = std::string{"DAILY_SWING|"} + path + "|" + symbol + "|" +
                direction + "|" + std::to_string(decision_time) + "|" + scan_id;
            const auto signal_id = cfss::sha256_hex(material);
            if (known_ids.contains(signal_id)) continue;

            bool active_duplicate = false;
            for (const auto& old : registry.at("candidates")) {
                if (old.value("state", std::string{}) == "PENDING" &&
                    old.value("path", std::string{}) == path &&
                    old.value("symbol", std::string{}) == symbol &&
                    old.value("direction", std::string{}) == direction) {
                    active_duplicate = true;
                    break;
                }
            }
            if (active_duplicate) continue;

            registry["candidates"].push_back({
                {"signal_id", signal_id}, {"path", path}, {"symbol", symbol},
                {"direction", direction}, {"regime", regime},
                {"decision_time_ms", decision_time}, {"expiry_time_ms", decision_time + horizon},
                {"entry_reference", entry}, {"stop_reference", stop}, {"target_reference", target},
                {"raw_score", score}, {"data_class", candidate_data_class},
                {"score_model_version", path == "PLAN_A_LRT" ? "LFS_V2_PROXY" : "NSS_V2_PROXY"},
                {"hypothesis", candidate.at("hypothesis")}, {"falsification", candidate.at("falsification")},
                {"source_run_id", dual.at("source_run_id")}, {"source_scan_id", scan_id},
                {"source_l1_sha256", dual.at("l1_sha256")}, {"source_universe_status", "VERIFIED"},
                {"profile", "DAILY_SWING"},
                {"resolution_timeframe", path == "PLAN_A_LRT" ? "15m" : "1h"},
                {"entry_fill_reference", nullptr}, {"entry_fill_time_ms", nullptr},
                {"entry_model", "NEXT_BAR_OPEN_PROXY"},
                {"execution_status", "NOT_EXECUTED"},
                {"state", "PENDING"}, {"resolution", nullptr}, {"closed_at_ms", nullptr},
                {"gross_r", nullptr}, {"skip_reason", nullptr}
            });
            known_ids.insert(signal_id);
            ++registered;
        }
    }

    std::size_t resolved = 0U;
    std::size_t still_pending = 0U;
    for (auto& candidate : registry["candidates"]) {
        if (candidate.value("state", std::string{}) != "PENDING") continue;
        const auto symbol = candidate.value("symbol", std::string{});
        const auto path = candidate.value("path", std::string{});
        const bool is_lrt = path == "PLAN_A_LRT";
        const auto decision = candidate.value("decision_time_ms", std::int64_t{0});
        const auto expiry = candidate.value("expiry_time_ms", std::int64_t{0});
        const auto* instrument = find_instrument(is_lrt ? l1_15m : l1, symbol);
        if (!instrument || !instrument->contains("candles") ||
            !instrument->at("candles").is_array() || instrument->at("candles").empty()) {
            if (current_time >= expiry) {
                candidate["state"] = "REJECTED";
                candidate["skip_reason"] = "RESOLUTION_DATA_UNAVAILABLE_AT_EXPIRY";
                ++rejected;
            } else {
                ++still_pending;
            }
            continue;
        }
        const auto direction = candidate.value("direction", std::string{});
        const double entry_reference = required_number(candidate, "entry_reference");
        const double stop = required_number(candidate, "stop_reference");
        const double target = required_number(candidate, "target_reference");
        const std::int64_t bar_ms = is_lrt ? 900'000LL : kOneHourMs;
        if (candidate.value("resolution_timeframe", std::string{}) != (is_lrt ? "15m" : "1h") ||
            expiry <= decision) {
            candidate["state"] = "REJECTED";
            candidate["skip_reason"] = "INVALID_RESOLUTION_TIMEFRAME_OR_HORIZON";
            ++rejected;
            continue;
        }

        bool closed = false;
        bool data_gap = false;
        bool entry_checked = false;
        double entry_fill = 0.0;
        double exit_price = 0.0;
        std::int64_t close_time = 0;
        std::int64_t expected_next_bar_ms = decision;
        const json* last_contiguous_bar = nullptr;
        std::string resolution;
        json resolution_bars = json::array();
        const auto& candles = instrument->at("candles");
        for (const auto& candle : candles) {
            if (!candle.value("closed", false)) continue;
            const auto ts = candle.value("timestamp_ms", std::int64_t{0});
            if (ts < decision) continue;
            if (ts >= expiry) break;
            const auto bar_close_time = ts + bar_ms;
            if (bar_close_time > current_time) break;
            if (ts != expected_next_bar_ms) {
                data_gap = true;
                break;
            }
            expected_next_bar_ms = bar_close_time;
            last_contiguous_bar = &candle;
            const double open = required_number(candle, "open");
            const double high = required_number(candle, "high");
            const double low = required_number(candle, "low");
            const double close = required_number(candle, "close");
            resolution_bars.push_back({
                {"timestamp_ms", ts}, {"open", open}, {"high", high},
                {"low", low}, {"close", close}
            });
            if (!entry_checked) {
                entry_checked = true;
                if ((direction == "LONG" && open <= stop) ||
                    (direction == "SHORT" && open >= stop)) {
                    candidate["state"] = "REJECTED";
                    candidate["skip_reason"] = "INVALIDATED_BEFORE_PROXY_ENTRY";
                    ++rejected;
                    break;
                }
                if ((direction == "LONG" && open >= target) ||
                    (direction == "SHORT" && open <= target)) {
                    candidate["state"] = "MISSED_ENTRY";
                    candidate["skip_reason"] = "TARGET_GAPPED_BEFORE_PROXY_ENTRY";
                    ++rejected;
                    break;
                }
                entry_fill = open;
                candidate["entry_fill_reference"] = entry_fill;
                candidate["entry_fill_time_ms"] = ts;
            }
            const double risk = std::abs(entry_fill - stop);
            if (risk <= 0.0) {
                candidate["state"] = "REJECTED";
                candidate["skip_reason"] = "INVALID_PROXY_FILL_RISK";
                ++rejected;
                break;
            }
            const bool stop_hit = direction == "LONG" ? low <= stop : high >= stop;
            const bool target_hit = direction == "LONG" ? high >= target : low <= target;
            if (stop_hit) {
                exit_price = stop;
                close_time = bar_close_time;
                resolution = target_hit ? "STOP_FIRST_SAME_BAR_AMBIGUITY" : "STOP";
                closed = true;
                break;
            }
            if (target_hit) {
                exit_price = target;
                close_time = bar_close_time;
                resolution = "TARGET";
                closed = true;
                break;
            }
        }

        if (candidate.value("state", std::string{}) == "REJECTED" ||
            candidate.value("state", std::string{}) == "MISSED_ENTRY") continue;
        if (data_gap) {
            if (current_time >= expiry) {
                candidate["state"] = "REJECTED";
                candidate["skip_reason"] = "FUTURE_DATA_GAP_OR_INCOMPLETE_COVERAGE";
                ++rejected;
            } else {
                ++still_pending;
            }
            continue;
        }
        if (!entry_checked) {
            if (current_time >= expiry) {
                candidate["state"] = "REJECTED";
                candidate["skip_reason"] = "NO_FUTURE_ENTRY_BAR_BEFORE_EXPIRY";
                ++rejected;
            } else {
                ++still_pending;
            }
            continue;
        }
        if (!closed && current_time >= expiry && expected_next_bar_ms < expiry) {
            candidate["state"] = "REJECTED";
            candidate["skip_reason"] = "FUTURE_DATA_COVERAGE_DID_NOT_REACH_EXPIRY";
            ++rejected;
            continue;
        }
        if (!closed && current_time >= expiry && expected_next_bar_ms >= expiry &&
            last_contiguous_bar != nullptr) {
            exit_price = required_number(*last_contiguous_bar, "close");
            close_time = expected_next_bar_ms;
            resolution = "TIME_EXPIRY";
            closed = true;
        }

        if (!closed) {
            ++still_pending;
            continue;
        }
        const double risk = std::abs(entry_fill - stop);
        const double sign = direction == "LONG" ? 1.0 : -1.0;
        const double gross_r = ((exit_price - entry_fill) * sign) / risk;
        const bool win = gross_r > 0.0;
        const auto signal_id = candidate.at("signal_id").get<std::string>();
        json outcome = {
            {"signal_id", signal_id}, {"profile", "DAILY_SWING"},
            {"path", candidate.at("path")},
            {"score_model_version", candidate.at("score_model_version")},
            {"regime", candidate.at("regime")}, {"closed_at_ms", close_time},
            {"raw_score", candidate.at("raw_score")}, {"win", win},
            {"win_r", win ? gross_r : 0.0}, {"loss_r", win ? 0.0 : std::abs(gross_r)},
            {"fee_r", nullptr}, {"slippage_r", nullptr}, {"funding_r", nullptr},
            {"data_class", candidate.at("data_class")}, {"cost_status", "UNAVAILABLE"},
            {"symbol", symbol}, {"direction", direction}, {"entry_reference", entry_reference},
            {"entry_fill_reference", entry_fill}, {"entry_model", "NEXT_BAR_OPEN_PROXY"},
            {"execution_status", "NOT_EXECUTED"},
            {"stop_reference", stop}, {"target_reference", target}, {"exit_reference", exit_price},
            {"decision_time_ms", decision}, {"resolution", resolution},
            {"resolution_timeframe", is_lrt ? "15m" : "1h"},
            {"resolution_data_sha256", is_lrt
                ? l1_15m.at("candles_sha256")
                : dual.at("l1_sha256")},
            {"resolution_bars", resolution_bars},
            {"source_scan_id", candidate.at("source_scan_id")},
            {"source_l1_sha256", candidate.at("source_l1_sha256")},
            {"source_universe_status", candidate.at("source_universe_status")},
            {"outcome_kind", "HYPOTHESIS_PROXY"}
        };
        const auto* cost_instrument = find_instrument(l1, symbol);
        if (cost_instrument)
            apply_shadow_costs(outcome, *cost_instrument,
                l1.value("run_id", std::string{}),
                l1.value("scan_id", std::string{}),
                dual.value("l1_sha256", std::string{}), current_time);
        ledger["outcomes"].push_back(std::move(outcome));
        candidate["state"] = "RESOLVED";
        candidate["resolution"] = resolution;
        candidate["closed_at_ms"] = close_time;
        candidate["gross_r"] = gross_r;
        ++resolved;
    }

    for (const auto& outcome : ledger["outcomes"]) {
        if (!valid_cost_provenance(outcome))
            throw std::runtime_error("shadow_outcome_cost_provenance_invalid");
    }

    ledger["ledger_status"] = ledger["outcomes"].empty() ? "EMPTY" : "AVAILABLE";
    ledger["cost_backfilled_this_run"] = cost_backfilled;
    ledger["cost_model"] = {
        {"id", "SHADOW_COST_PROXY_V1"},
        {"data_class", "PROXY"},
        {"fee_rate_per_side", kShadowFeeRatePerSide},
        {"slippage_rate_per_side", kShadowSlippageRatePerSide},
        {"funding_source", "OKX_PUBLIC_FUNDING_HISTORY"},
        {"funding_coverage_tolerance_hours", 8}
    };
    registry["updated_at_ms"] = current_time;
    registry["summary"] = {
        {"registered_this_run", registered}, {"resolved_this_run", resolved},
        {"pending_count", still_pending}, {"rejected_this_run", rejected},
        {"total_candidates", registry["candidates"].size()},
    };
    return {{"registry", registry}, {"ledger", ledger}};
}
} // namespace cfss::shadow
