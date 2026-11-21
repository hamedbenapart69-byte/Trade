#pragma once

#include "cfss/hash.hpp"
#include "cfss/shadow_outcomes.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::shadow_risk {
using json = nlohmann::json;

inline bool finite_number(const json& value, const char* key) {
    return value.is_object() && value.contains(key) && value.at(key).is_number() &&
           std::isfinite(value.at(key).get<double>());
}

inline std::int64_t utc_day(std::int64_t timestamp_ms) {
    constexpr std::int64_t day_ms = 86'400'000LL;
    return timestamp_ms / day_ms;
}

inline std::int64_t utc_week(std::int64_t timestamp_ms) {
    constexpr std::int64_t monday_offset_days = 3LL; // 1970-01-01 was Thursday.
    const auto day = utc_day(timestamp_ms);
    return (day + monday_offset_days) / 7LL;
}

inline json unavailable(const std::string& reason, const json& basis,
                        const json& ledger, const json& registry,
                        const std::string& source_run_id, const std::string& source_scan_id,
                        std::int64_t decision_time_ms) {
    return {
        {"artifact_type", "cfss_shadow_risk_snapshot_v1"},
        {"snapshot_scope", "CFSS_SHADOW_PORTFOLIO_ONLY"},
        {"user_account_data_used", false},
        {"status", "UNAVAILABLE"},
        {"data_class", "PROXY"},
        {"reason", reason},
        {"source_run_id", source_run_id},
        {"source_scan_id", source_scan_id},
        {"decision_time_ms", decision_time_ms},
        {"risk_basis_sha256", cfss::sha256_hex(basis.dump())},
        {"ledger_sha256", cfss::sha256_hex(ledger.dump())},
        {"registry_sha256", cfss::sha256_hex(registry.dump())}
    };
}

// محاسبه فقط از دفتر Shadow پایدار؛ هیچ داده‌ای از حساب واقعی کاربر خوانده نمی‌شود.
inline json build_snapshot(const json& basis, const json& ledger,
                           const json& registry, const std::string& source_run_id,
                           const std::string& source_scan_id, std::int64_t decision_time_ms,
                           int correlated_candidate_exposures) {
    const auto fail = [&](const std::string& reason) {
        return unavailable(reason, basis, ledger, registry, source_run_id, source_scan_id, decision_time_ms);
    };
    if (decision_time_ms <= 0 || source_run_id.empty() || source_scan_id.empty())
        return fail("RISK_SNAPSHOT_INPUT_INVALID");
    if (correlated_candidate_exposures < 0)
        return fail("CORRELATION_DATA_UNAVAILABLE");

    if (basis.value("artifact_type", std::string{}) != "cfss_shadow_risk_basis_v1" ||
        basis.value("schema_version", std::string{}) != "1.0.0" ||
        basis.value("basis_status", std::string{}) != "FROZEN" ||
        basis.value("user_account_data_used", true) ||
        basis.value("timezone", std::string{}) != "UTC" ||
        basis.value("daily_reset_rule", std::string{}) != "UTC_CALENDAR_DAY_00_00" ||
        basis.value("weekly_reset_rule", std::string{}) != "ISO_WEEK_MONDAY_00_00_UTC" ||
        basis.value("equity_method", std::string{}) !=
            "INITIAL_NAV_PLUS_REALIZED_AND_MARKED_UNREALIZED_NET_PNL" ||
        basis.value("open_position_policy", std::string{}) !=
            "MARK_TO_MARKET_WITH_FRESH_CLOSED_CANDLE_AND_COSTS" ||
        basis.value("cost_policy", std::string{}) !=
            "REQUIRE_EXPLICIT_COST_STATUS_AND_PROVENANCE" ||
        basis.value("effective_from_ms", std::int64_t{0}) <= 0 ||
        basis.value("effective_from_ms", std::int64_t{0}) > decision_time_ms ||
        !finite_number(basis, "initial_nav_units") ||
        basis.at("initial_nav_units").get<double>() <= 0.0 ||
        !finite_number(basis, "risk_per_trade_pct") ||
        basis.at("risk_per_trade_pct").get<double>() <= 0.0 ||
        basis.at("risk_per_trade_pct").get<double>() > 100.0 ||
        basis.value("basis_id", std::string{}).empty() ||
        basis.value("basis_version", 0) < 1)
        return fail("RISK_BASIS_INVALID_OR_NOT_FROZEN");

    if (ledger.value("artifact_type", std::string{}) != "cfss_outcome_ledger_v1" ||
        ledger.value("ledger_status", std::string{}) != "AVAILABLE" ||
        ledger.value("profile", std::string{}) != basis.value("profile", std::string{}) ||
        !ledger.contains("outcomes") || !ledger.at("outcomes").is_array() ||
        ledger.at("outcomes").empty())
        return fail("COSTED_OUTCOME_LEDGER_UNAVAILABLE");

    if (registry.value("artifact_type", std::string{}) !=
            "cfss_shadow_candidate_registry_v1" ||
        !registry.contains("candidates") || !registry.at("candidates").is_array())
        return fail("SHADOW_CANDIDATE_REGISTRY_UNAVAILABLE");

    // هر fill باید دقیقاً یک outcome بسته و قابل‌ردیابی داشته باشد؛ state به‌تنهایی کافی نیست.
    std::map<std::string, const json*> candidate_by_id;
    std::set<std::string> resolved_candidate_ids;
    for (const auto& candidate : registry.at("candidates")) {
        const auto signal_id = candidate.value("signal_id", std::string{});
        const auto state = candidate.value("state", std::string{});
        if (signal_id.empty() || !candidate_by_id.emplace(signal_id, &candidate).second)
            return fail("SHADOW_CANDIDATE_ID_INVALID_OR_DUPLICATE");
        const bool has_fill = candidate.contains("entry_fill_reference") &&
            candidate.at("entry_fill_reference").is_number() &&
            std::isfinite(candidate.at("entry_fill_reference").get<double>()) &&
            candidate.at("entry_fill_reference").get<double>() > 0.0;
        if (has_fill && state != "RESOLVED")
            return fail("UNACCOUNTED_FILLED_SHADOW_CANDIDATE");
        if (state == "RESOLVED") {
            if (!has_fill) return fail("RESOLVED_CANDIDATE_FILL_MISSING");
            resolved_candidate_ids.insert(signal_id);
        }
    }

    struct Event {
        std::int64_t entry_at_ms{};
        std::int64_t closed_at_ms{};
        std::string signal_id;
        double net_r{};
    };
    std::vector<Event> events;
    std::set<std::string> ids;
    for (const auto& outcome : ledger.at("outcomes")) {
        const auto closed = outcome.value("closed_at_ms", std::int64_t{0});
        const auto entry_at = outcome.value("entry_fill_time_ms", std::int64_t{0});
        const auto signal_id = outcome.value("signal_id", std::string{});
        const auto candidate_it = candidate_by_id.find(signal_id);
        if (entry_at < basis.at("effective_from_ms").get<std::int64_t>() ||
            entry_at <= 0 || closed < entry_at || closed > decision_time_ms ||
            signal_id.empty() || candidate_it == candidate_by_id.end() ||
            !ids.insert(signal_id).second)
            return fail("OUTCOME_TIME_OR_ID_INVALID");

        const auto& candidate = *candidate_it->second;
        if (candidate.value("state", std::string{}) != "RESOLVED")
            return fail("OUTCOME_CANDIDATE_STATE_MISMATCH");
        const auto same_price = [](const json& left, const json& right) {
            if (!left.is_number() || !right.is_number()) return false;
            const double a = left.get<double>();
            const double b = right.get<double>();
            return std::isfinite(a) && std::isfinite(b) &&
                std::abs(a - b) <= std::max(1e-10, std::abs(a) * 1e-9);
        };
        if (candidate.value("symbol", std::string{}) != outcome.value("symbol", std::string{}) ||
            candidate.value("direction", std::string{}) != outcome.value("direction", std::string{}) ||
            candidate.value("profile", std::string{}) != outcome.value("profile", std::string{}) ||
            !same_price(candidate.value("entry_fill_reference", json{}),
                        outcome.value("entry_fill_reference", json{})) ||
            !same_price(candidate.value("stop_reference", json{}),
                        outcome.value("stop_reference", json{})))
            return fail("OUTCOME_CANDIDATE_FIELD_MISMATCH");
        if (candidate.contains("entry_fill_time_ms") &&
            !candidate.at("entry_fill_time_ms").is_null() &&
            (!candidate.at("entry_fill_time_ms").is_number_integer() ||
             candidate.at("entry_fill_time_ms").get<std::int64_t>() != entry_at))
            return fail("OUTCOME_CANDIDATE_FILL_TIME_MISMATCH");
        if (outcome.value("execution_status", std::string{}) != "NOT_EXECUTED" ||
            outcome.value("outcome_kind", std::string{}) != "HYPOTHESIS_PROXY" ||
            outcome.value("profile", std::string{}) != basis.value("profile", std::string{}) ||
            outcome.value("cost_status", std::string{}) != "PROXY" ||
            !cfss::shadow::valid_cost_provenance(outcome))
            return fail("OUTCOME_COST_OR_PROVENANCE_UNAVAILABLE");
        for (const auto* key : {"win_r", "loss_r", "fee_r", "slippage_r", "funding_r"}) {
            if (!finite_number(outcome, key)) return fail("OUTCOME_COST_COMPONENT_INVALID");
        }
        const double net_r = outcome.at("win_r").get<double>() -
            outcome.at("loss_r").get<double>() -
            outcome.at("fee_r").get<double>() -
            outcome.at("slippage_r").get<double>() -
            outcome.at("funding_r").get<double>();
        if (!std::isfinite(net_r)) return fail("OUTCOME_NET_R_NONFINITE");
        events.push_back({entry_at, closed, signal_id, net_r});
    }
    for (const auto& signal_id : resolved_candidate_ids) {
        if (!ids.contains(signal_id))
            return fail("RESOLVED_CANDIDATE_OUTCOME_MISSING");
    }

    // بدون NAV در لحظهٔ ورود، معاملات هم‌پوشان قابل ارزش‌گذاری صحیح نیستند.
    // فقط توالی‌های غیرهم‌پوشان اجازهٔ بازسازی NAV از دفتر بسته‌شده را می‌دهند؛ این مقدار جایگزین mark-to-market درون‌معامله‌ای نیست.
    auto intervals = events;
    std::sort(intervals.begin(), intervals.end(), [](const Event& left, const Event& right) {
        if (left.entry_at_ms != right.entry_at_ms)
            return left.entry_at_ms < right.entry_at_ms;
        return left.closed_at_ms < right.closed_at_ms;
    });
    std::int64_t latest_close = 0;
    for (const auto& event : intervals) {
        if (event.entry_at_ms < latest_close)
            return fail("OVERLAPPING_SHADOW_OUTCOMES_ENTRY_NAV_UNAVAILABLE");
        latest_close = std::max(latest_close, event.closed_at_ms);
    }

    std::sort(events.begin(), events.end(), [](const Event& left, const Event& right) {
        if (left.closed_at_ms != right.closed_at_ms)
            return left.closed_at_ms < right.closed_at_ms;
        return left.signal_id < right.signal_id;
    });

    double nav = basis.at("initial_nav_units").get<double>();
    double high_water = nav;
    double max_portfolio_drawdown_pct = 0.0;
    double day_start_nav = nav;
    double week_start_nav = nav;
    double max_daily_loss_pct = 0.0;
    double max_weekly_loss_pct = 0.0;
    std::int64_t active_day = -1;
    std::int64_t active_week = -1;
    std::size_t i = 0U;
    while (i < events.size()) {
        const auto day = utc_day(events[i].closed_at_ms);
        const auto week = utc_week(events[i].closed_at_ms);
        if (day != active_day) {
            active_day = day;
            day_start_nav = nav;
            max_daily_loss_pct = 0.0;
        }
        if (week != active_week) {
            active_week = week;
            week_start_nav = nav;
            max_weekly_loss_pct = 0.0;
        }

        // معاملات هم‌زمان با NAV یکسان پیش از رویداد محاسبه می‌شوند.
        const double pre_event_nav = nav;
        double aggregate_r = 0.0;
        std::size_t j = i;
        while (j < events.size() && events[j].closed_at_ms == events[i].closed_at_ms) {
            aggregate_r += events[j].net_r;
            ++j;
        }
        const double pnl = pre_event_nav *
            (basis.at("risk_per_trade_pct").get<double>() / 100.0) * aggregate_r;
        nav += pnl;
        if (!std::isfinite(nav) || nav <= 0.0) return fail("SHADOW_NAV_NONPOSITIVE");
        high_water = std::max(high_water, nav);
        max_portfolio_drawdown_pct = std::max(max_portfolio_drawdown_pct,
            std::max(0.0, (high_water - nav) / high_water * 100.0));
        // عبور از حد زیان درون‌دوره‌ای تا پایان همان روز/هفته باقی می‌ماند؛ بازیابی بعدی آن را پاک نمی‌کند.
        max_daily_loss_pct = std::max(max_daily_loss_pct,
            std::max(0.0, (day_start_nav - nav) / day_start_nav * 100.0));
        max_weekly_loss_pct = std::max(max_weekly_loss_pct,
            std::max(0.0, (week_start_nav - nav) / week_start_nav * 100.0));
        i = j;
    }

    if (active_day != utc_day(decision_time_ms)) {
        day_start_nav = nav;
        max_daily_loss_pct = 0.0;
    }
    if (active_week != utc_week(decision_time_ms)) {
        week_start_nav = nav;
        max_weekly_loss_pct = 0.0;
    }

    // زیان روزانه/هفتگی، بیشترین افت مشاهده‌شده از NAV ابتدای دوره است، نه فقط مقدار نهایی پس از بازیابی.
    const double daily_loss = max_daily_loss_pct;
    const double weekly_loss = max_weekly_loss_pct;
    const double drawdown = max_portfolio_drawdown_pct;
    if (!std::isfinite(daily_loss) || !std::isfinite(weekly_loss) ||
        !std::isfinite(drawdown))
        return fail("RISK_METRIC_NONFINITE");

    return {
        {"artifact_type", "cfss_shadow_risk_snapshot_v1"},
        {"snapshot_scope", "CFSS_SHADOW_PORTFOLIO_ONLY"},
        {"user_account_data_used", false},
        {"status", "AVAILABLE"},
        {"data_class", "PROXY"},
        {"basis_id", basis.at("basis_id")},
        {"basis_version", basis.at("basis_version")},
        {"risk_basis_sha256", cfss::sha256_hex(basis.dump())},
        {"ledger_sha256", cfss::sha256_hex(ledger.dump())},
        {"registry_sha256", cfss::sha256_hex(registry.dump())},
        {"source_run_id", source_run_id},
        {"source_scan_id", source_scan_id},
        {"decision_time_ms", decision_time_ms},
        {"initial_nav_units", basis.at("initial_nav_units")},
        {"current_nav_units", nav},
        {"daily_loss_pct", daily_loss},
        {"weekly_loss_pct", weekly_loss},
        {"portfolio_drawdown_pct", drawdown},
        {"correlated_candidate_exposures", correlated_candidate_exposures},
        {"resolved_outcome_count", events.size()},
        {"cost_status", "PROXY"},
        {"open_position_status", "NO_FILLED_OPEN_POSITIONS"}
    };
}
} // namespace cfss::shadow_risk
