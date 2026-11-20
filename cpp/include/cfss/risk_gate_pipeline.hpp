#pragma once
#include "cfss/risk_gate.hpp"
#include "cfss/hash.hpp"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <numeric>
#include <iterator>
#include <set>
#include <vector>
#include <optional>
#include <stdexcept>
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

inline std::string normalize_direction(std::string direction) {
    if (direction == "BUY") return "LONG";
    if (direction == "SELL") return "SHORT";
    return direction;
}

struct CandidateKey {
    std::string symbol;
    std::string direction;
    bool operator<(const CandidateKey& other) const {
        return symbol < other.symbol || (symbol == other.symbol && direction < other.direction);
    }
};

inline std::map<std::int64_t, double> hourly_returns(const json& instrument,
                                                      std::int64_t decision_time_ms) {
    constexpr std::int64_t hour_ms = 3'600'000LL;
    constexpr std::int64_t lookback_ms = 90LL * 24LL * hour_ms;
    const auto cutoff = decision_time_ms - lookback_ms;
    std::map<std::int64_t, double> closes;
    if (!instrument.contains("candles") || !instrument.at("candles").is_array()) return {};
    for (const auto& candle : instrument.at("candles")) {
        if (!candle.is_object() || !candle.value("closed", false) ||
            !candle.contains("timestamp_ms") || !candle.at("timestamp_ms").is_number_integer() ||
            !has_number(candle, "close")) continue;
        const auto ts = candle.at("timestamp_ms").get<std::int64_t>();
        const double close = candle.at("close").get<double>();
        if (ts <= 0 || ts + hour_ms > decision_time_ms || close <= 0.0) continue;
        closes[ts] = close;
    }
    std::map<std::int64_t, double> returns;
    if (closes.size() < 2U) return returns;
    auto previous = closes.begin();
    for (auto current = std::next(previous); current != closes.end(); ++current) {
        if (current->first - previous->first == hour_ms && current->first >= cutoff) {
            const double value = std::log(current->second / previous->second);
            if (std::isfinite(value)) returns.emplace(current->first, value);
        }
        previous = current;
    }
    return returns;
}

inline std::optional<double> aligned_pearson(const std::map<std::int64_t, double>& left,
                                              const std::map<std::int64_t, double>& right) {
    std::vector<double> x, y;
    for (const auto& [timestamp, value] : left) {
        const auto it = right.find(timestamp);
        if (it == right.end()) continue;
        x.push_back(value);
        y.push_back(it->second);
    }
    if (x.size() < 50U) return std::nullopt;
    const double mx = std::accumulate(x.begin(), x.end(), 0.0) / static_cast<double>(x.size());
    const double my = std::accumulate(y.begin(), y.end(), 0.0) / static_cast<double>(y.size());
    double covariance = 0.0, vx = 0.0, vy = 0.0;
    for (std::size_t i = 0U; i < x.size(); ++i) {
        const double dx = x[i] - mx, dy = y[i] - my;
        covariance += dx * dy;
        vx += dx * dx;
        vy += dy * dy;
    }
    if (vx <= 0.0 || vy <= 0.0) return std::nullopt;
    const double correlation = covariance / std::sqrt(vx * vy);
    return std::isfinite(correlation) ? std::optional<double>{correlation} : std::nullopt;
}

struct CorrelationSummary {
    bool valid{true};
    std::map<CandidateKey, int> peer_counts;
};

inline CorrelationSummary candidate_correlations(const json& l1, const json& meta,
                                                  std::int64_t decision_time_ms) {
    std::set<CandidateKey> candidates;
    for (const auto& instrument : meta.at("instruments")) {
        const auto symbol = instrument.value("symbol", std::string{});
        for (const auto* key : {"lrt", "nmt"}) {
            const auto& engine = instrument.at(key);
            const auto status = engine.value("candidate_status", std::string{});
            const bool present = status == "CANDIDATE" || status == "EV_POSITIVE_RESEARCH_ONLY";
            if (!present) continue;
            const auto direction = normalize_direction(engine.value("direction", std::string{}));
            if (symbol.empty() || (direction != "LONG" && direction != "SHORT"))
                return {false, {}};
            candidates.insert({symbol, direction});
        }
    }
    CorrelationSummary summary{};
    if (candidates.size() < 2U) return summary;
    std::map<std::string, std::map<std::int64_t, double>> returns_by_symbol;
    for (const auto& candidate : candidates) {
        if (returns_by_symbol.contains(candidate.symbol)) continue;
        const auto* market = find_symbol(l1.at("instruments"), candidate.symbol, "unified_symbol");
        if (!market) return {false, {}};
        auto returns = hourly_returns(*market, decision_time_ms);
        if (returns.size() < 50U) return {false, {}};
        returns_by_symbol.emplace(candidate.symbol, std::move(returns));
    }
    for (auto left = candidates.begin(); left != candidates.end(); ++left) {
        auto right = std::next(left);
        for (; right != candidates.end(); ++right) {
            if (left->direction != right->direction || left->symbol == right->symbol) continue;
            const auto corr = aligned_pearson(returns_by_symbol.at(left->symbol),
                                              returns_by_symbol.at(right->symbol));
            if (!corr) return {false, {}};
            if (*corr > 0.70) {
                ++summary.peer_counts[*left];
                ++summary.peer_counts[*right];
            }
        }
    }
    return summary;
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
        risk_snapshot.at("daily_loss_pct").get<double>() >= 0.0 && risk_snapshot.at("daily_loss_pct").get<double>() <= 100.0 &&
        risk_snapshot.at("weekly_loss_pct").get<double>() >= 0.0 && risk_snapshot.at("weekly_loss_pct").get<double>() <= 100.0 &&
        risk_snapshot.at("portfolio_drawdown_pct").get<double>() >= 0.0 && risk_snapshot.at("portfolio_drawdown_pct").get<double>() <= 100.0 &&
        risk_snapshot.value("source_run_id", std::string{}) == run_id &&
        risk_snapshot.value("source_scan_id", std::string{}) == scan_id &&
        risk_snapshot.value("decision_time_ms", std::int64_t{0}) == decision_time;

    const auto correlations = candidate_correlations(l1, meta, decision_time);
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
            input.correlation_data_valid = !present || correlations.valid;
            const CandidateKey candidate_key{symbol, normalize_direction(engine.value("direction", std::string{}))};
            const auto peer_it = correlations.peer_counts.find(candidate_key);
            input.correlated_candidate_exposures = peer_it == correlations.peer_counts.end() ? 0 : peer_it->second;
            input.risk_snapshot_valid = snapshot_available;
            if (snapshot_available) {
                input.daily_loss_pct = risk_snapshot.at("daily_loss_pct").get<double>();
                input.weekly_loss_pct = risk_snapshot.at("weekly_loss_pct").get<double>();
                input.portfolio_drawdown_pct = risk_snapshot.at("portfolio_drawdown_pct").get<double>();
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
                    {"correlation_data_status", input.correlation_data_valid ? "AVAILABLE" : "UNAVAILABLE"},
                    {"correlated_candidate_exposures", input.correlated_candidate_exposures},
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
        {"correlation_data_status", correlations.valid ? "AVAILABLE" : "UNAVAILABLE"},
        {"summary", {{"candidate_count", candidates}, {"blocked_count", blocked},
                     {"manual_review_count", manual_review}, {"actionable_count", 0}}},
        {"actionable", false}, {"trade_execution_allowed", false},
        {"instruments", rows}
    };
}
} // namespace cfss::risk
