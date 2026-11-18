#pragma once

#include "cfss/hash.hpp"

#include <cmath>
#include <cstdint>
#include <set>
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
        l1_15m.value("window", json::object()).value("end_ms", std::int64_t{0}) != current_time)
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
            old_candidate["entry_model"] = "NEXT_BAR_OPEN_PROXY";
            old_candidate["execution_status"] = "NOT_EXECUTED";
            old_candidate["state"] = "REJECTED";
            old_candidate["skip_reason"] = "LEGACY_CANDIDATE_QUARANTINED_AFTER_ENTRY_MODEL_CHANGE";
            ++rejected;
            continue;
        }
        if (old_candidate.value("source_universe_status", std::string{"UNVERIFIED"}) != "VERIFIED") {
            old_candidate["state"] = "REJECTED";
            old_candidate["skip_reason"] = "SOURCE_UNIVERSE_NOT_VERIFIED";
            ++rejected;
        }
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
            const auto material = path + "|" + symbol + "|" + direction + "|" +
                std::to_string(decision_time) + "|" + scan_id;
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
                {"hypothesis", candidate.at("hypothesis")}, {"falsification", candidate.at("falsification")},
                {"source_run_id", dual.at("source_run_id")}, {"source_scan_id", scan_id},
                {"source_l1_sha256", dual.at("l1_sha256")}, {"source_universe_status", "VERIFIED"},
                {"profile", "DAILY_SWING"},
                {"resolution_timeframe", path == "PLAN_A_LRT" ? "15m" : "1h"},
                {"entry_fill_reference", nullptr},
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
        const auto* instrument = find_instrument(is_lrt ? l1_15m : l1, symbol);
        if (!instrument || !instrument->contains("candles") || !instrument->at("candles").is_array()) {
            ++still_pending;
            continue;
        }
        const auto direction = candidate.value("direction", std::string{});
        const double entry_reference = required_number(candidate, "entry_reference");
        const double stop = required_number(candidate, "stop_reference");
        const double target = required_number(candidate, "target_reference");
        const auto decision = candidate.value("decision_time_ms", std::int64_t{0});
        const auto expiry = candidate.value("expiry_time_ms", std::int64_t{0});
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
            ++still_pending;
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
        ledger["outcomes"].push_back({
            {"signal_id", signal_id}, {"profile", "DAILY_SWING"},
            {"path", candidate.at("path")},
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
            {"source_scan_id", candidate.at("source_scan_id")},
            {"source_l1_sha256", candidate.at("source_l1_sha256")},
            {"source_universe_status", candidate.at("source_universe_status")},
            {"outcome_kind", "HYPOTHESIS_PROXY"}
        });
        candidate["state"] = "RESOLVED";
        candidate["resolution"] = resolution;
        candidate["closed_at_ms"] = close_time;
        candidate["gross_r"] = gross_r;
        ++resolved;
    }

    ledger["ledger_status"] = ledger["outcomes"].empty() ? "EMPTY" : "AVAILABLE";
    registry["updated_at_ms"] = current_time;
    registry["summary"] = {
        {"registered_this_run", registered}, {"resolved_this_run", resolved},
        {"pending_count", still_pending}, {"rejected_this_run", rejected},
        {"total_candidates", registry["candidates"].size()},
        {"total_outcomes", ledger["outcomes"].size()}
    };
    return {{"registry", registry}, {"ledger", ledger}};
}
} // namespace cfss::shadow
