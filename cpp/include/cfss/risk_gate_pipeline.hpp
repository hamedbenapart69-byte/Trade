#pragma once
#include "cfss/risk_gate.hpp"
#include "cfss/hash.hpp"
#include <nlohmann/json.hpp>
#include <cstdint>
#include <optional>
#include <string>

namespace cfss::risk {
using json = nlohmann::json;

inline const json* find_symbol(const json& rows, const std::string& symbol,
                               const std::string& key) {
    if (!rows.is_array()) return nullptr;
    for (const auto& row : rows)
        if (row.value(key, std::string{}) == symbol) return &row;
    return nullptr;
}

inline bool has_number(const json& value, const char* key) {
    return value.is_object() && value.contains(key) && value.at(key).is_number() &&
           std::isfinite(value.at(key).get<double>());
}

inline json build_report(const json& l1, const json& liquidity, const json& meta,
                         const std::string& l1_raw, const std::string& liquidity_raw,
                         const json& risk_snapshot) {
    if (l1.value("schema_version", std::string{}) != "1.0.0" ||
        liquidity.value("artifact_type", std::string{}) != "cfss_liquidity_phase_v1" ||
        meta.value("artifact_type", std::string{}) != "cfss_meta_cognition_v1")
        throw std::invalid_argument("STAGE7_INPUT_ARTIFACT_TYPE_INVALID");

    const auto run_id = meta.value("source_run_id", std::string{});
    const auto scan_id = meta.value("source_scan_id", std::string{});
    const auto decision_time = meta.value("decision_time_ms", std::int64_t{0});
    if (run_id.empty() || scan_id.empty() || decision_time <= 0 ||
        l1.value("run_id", std::string{}) != run_id ||
        l1.value("scan_id", std::string{}) != scan_id ||
        liquidity.value("source_run_id", std::string{}) != run_id ||
        liquidity.value("source_scan_id", std::string{}) != scan_id ||
        liquidity.value("decision_time_ms", std::int64_t{0}) != decision_time ||
        meta.value("l1_sha256", std::string{}) != cfss::sha256_hex(l1_raw) ||
        meta.value("liquidity_report_sha256", std::string{}) != cfss::sha256_hex(liquidity_raw))
        throw std::invalid_argument("STAGE7_PROVENANCE_MISMATCH");

    const bool snapshot_available =
        risk_snapshot.is_object() &&
        risk_snapshot.value("artifact_type", std::string{}) == "cfss_shadow_risk_snapshot_v1" &&
        risk_snapshot.value("snapshot_scope", std::string{}) == "CFSS_SHADOW_PORTFOLIO_ONLY" &&
        risk_snapshot.value("user_account_data_used", true) == false &&
        risk_snapshot.value("status", std::string{}) == "AVAILABLE" &&
        has_number(risk_snapshot, "daily_loss_pct") &&
        has_number(risk_snapshot, "weekly_loss_pct") &&
        has_number(risk_snapshot, "portfolio_drawdown_pct") &&
        risk_snapshot.contains("correlated_candidate_exposures") &&
        risk_snapshot.at("correlated_candidate_exposures").is_number_integer() &&
        risk_snapshot.at("correlated_candidate_exposures").get<int>() >= 0 &&
        risk_snapshot.value("source_run_id", std::string{}) == run_id &&
        risk_snapshot.value("source_scan_id", std::string{}) == scan_id &&
        risk_snapshot.value("decision_time_ms", std::int64_t{0}) == decision_time;

    json rows = json::array();
    std::size_t candidates = 0U, blocked = 0U, manual_review = 0U;
    for (const auto& instrument : meta.at("instruments")) {
        const auto symbol = instrument.value("symbol", std::string{});
        const auto* market = find_symbol(l1.at("instruments"), symbol, "unified_symbol");
        const auto* phase = find_symbol(liquidity.at("instruments"), symbol, "symbol");
        const bool market_liquid =
            market && market->value("liquidity_status", std::string{}) == "ELIGIBLE" &&
            has_number(*market, "turnover_24h_usd") &&
            has_number(*market, "liquidity_threshold_usd") &&
            market->at("turnover_24h_usd").get<double>() >=
                market->at("liquidity_threshold_usd").get<double>();
        const bool phase_available = phase &&
            phase->value("status", std::string{}) == "AVAILABLE" &&
            phase->value("phase", std::string{}) != "UNAVAILABLE";

        json engine_rows = json::object();
        for (const auto* key : {"lrt", "nmt"}) {
            const auto& engine = instrument.at(key);
            const auto status = engine.value("candidate_status", std::string{});
            const bool present = status == "CANDIDATE" ||
                                 status == "EV_POSITIVE_RESEARCH_ONLY";
            if (present) ++candidates;
            Input input{};
            input.candidate_present = present;
            input.candidate_actionable = engine.value("actionable", true);
            input.golden_rule_veto = instrument.value("golden_rule", json::object())
                .value("veto", true);
            input.data_real = engine.value("data_class", std::string{}) == "REAL";
            input.liquidity_ok = market_liquid && phase_available;
            input.calibration_valid =
                engine.value("confidence_status", std::string{}) == "CALIBRATED" &&
                engine.value("calibration", json::object()).value("status", std::string{}) == "CALIBRATED";
            if (has_number(engine, "ev_net"))
                input.net_ev_r = engine.at("ev_net").get<double>();
            const auto calibration = engine.value("calibration", json::object());
            input.costs_complete = has_number(calibration, "avg_fee_r") &&
                has_number(calibration, "avg_slippage_r") &&
                has_number(calibration, "avg_funding_r") &&
                engine.value("ev_status", std::string{}) == "CALCULATED";
            input.risk_snapshot_valid = snapshot_available;
            if (snapshot_available) {
                input.daily_loss_pct = risk_snapshot.at("daily_loss_pct").get<double>();
                input.weekly_loss_pct = risk_snapshot.at("weekly_loss_pct").get<double>();
                input.portfolio_drawdown_pct = risk_snapshot.at("portfolio_drawdown_pct").get<double>();
                input.correlated_open_exposures =
                    risk_snapshot.at("correlated_candidate_exposures").get<int>();
            }
            const auto decision = evaluate(input);
            if (decision.status == "BLOCKED") ++blocked;
            else ++manual_review;
            engine_rows[key] = {
                {"path", engine.value("path", std::string{"UNKNOWN"})},
                {"candidate_status", status.empty() ? "UNAVAILABLE" : status},
                {"decision", decision.status}, {"reason", decision.reason},
                {"manual_review_required", decision.manual_review_required},
                {"trade_execution_allowed", false},
                {"inputs", {
                    {"candidate_present", input.candidate_present},
                    {"golden_rule_veto", input.golden_rule_veto},
                    {"data_class", engine.value("data_class", std::string{"UNAVAILABLE"})},
                    {"liquidity_ok", input.liquidity_ok},
                    {"calibration_valid", input.calibration_valid},
                    {"net_ev_r", input.net_ev_r ? json(*input.net_ev_r) : json(nullptr)},
                    {"costs_complete", input.costs_complete},
                    {"shadow_risk_snapshot_status", snapshot_available ? "AVAILABLE" : "UNAVAILABLE"}
                }}
            };
        }
        rows.push_back({{"symbol", symbol}, {"golden_rule_veto",
            instrument.value("golden_rule", json::object()).value("veto", true)},
            {"engines", engine_rows}});
    }

    return {
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_stage7_risk_gate_v1"},
        {"source_run_id", run_id}, {"source_scan_id", scan_id},
        {"decision_time_ms", decision_time},
        {"l1_sha256", cfss::sha256_hex(l1_raw)},
        {"liquidity_report_sha256", cfss::sha256_hex(liquidity_raw)},
        {"meta_cognition_sha256", cfss::sha256_hex(meta.dump())},
        {"snapshot_scope", "CFSS_SHADOW_PORTFOLIO_ONLY"},
        {"user_account_data_used", false},
        {"risk_snapshot_status", snapshot_available ? "AVAILABLE" : "UNAVAILABLE"},
        {"summary", {{"candidate_count", candidates}, {"blocked_count", blocked},
                     {"manual_review_count", manual_review}, {"actionable_count", 0}}},
        {"actionable", false}, {"trade_execution_allowed", false},
        {"instruments", rows}
    };
}
} // namespace cfss::risk
