#include "cfss/shadow_risk_snapshot.hpp"
#include <cmath>
#include <iostream>
#include <string>

using json = nlohmann::json;

namespace {
int checks = 0;
int failures = 0;
void check(bool ok, const std::string& name) {
    ++checks;
    if (!ok) { ++failures; std::cerr << "FAIL: " << name << '\n'; }
}
json basis() {
    return {
        {"schema_version","1.0.0"},{"artifact_type","cfss_shadow_risk_basis_v1"},
        {"basis_id","daily-swing-shadow-v1"},{"basis_version",1},
        {"profile","DAILY_SWING"},{"basis_status","FROZEN"},
        {"initial_nav_units",100.0},{"risk_per_trade_pct",0.5},
        {"effective_from_ms",1},{"timezone","UTC"},
        {"daily_reset_rule","UTC_CALENDAR_DAY_00_00"},
        {"weekly_reset_rule","ISO_WEEK_MONDAY_00_00_UTC"},
        {"equity_method","INITIAL_NAV_PLUS_REALIZED_AND_MARKED_UNREALIZED_NET_PNL"},
        {"open_position_policy","MARK_TO_MARKET_WITH_FRESH_CLOSED_CANDLE_AND_COSTS"},
        {"cost_policy","REQUIRE_EXPLICIT_COST_STATUS_AND_PROVENANCE"},
        {"user_account_data_used",false}
    };
}
json outcome(const std::string& id, std::int64_t closed, double win_r, double loss_r) {
    const std::string hash(64,'a');
    return {
        {"signal_id",id},{"profile","DAILY_SWING"},{"path","PLAN_A_LRT"},
        {"regime","RANGE"},{"closed_at_ms",closed},{"raw_score",0.8},
        {"score_model_version","LFS_V2_PROXY"},{"win",win_r>0.0},
        {"win_r",win_r},{"loss_r",loss_r},{"fee_r",0.1},
        {"slippage_r",0.1},{"funding_r",0.0},{"data_class","PROXY"},
        {"cost_status","PROXY"},{"symbol","BTC/USDT:USDT"},{"direction","LONG"},
        {"entry_reference",100.0},{"entry_fill_reference",100.0},
        {"entry_fill_time_ms",closed-1'000LL},
        {"entry_model","NEXT_BAR_OPEN_PROXY"},{"execution_status","NOT_EXECUTED"},
        {"stop_reference",99.0},{"target_reference",102.0},{"exit_reference",101.0},
        {"decision_time_ms",closed-3'600'000LL},{"resolution","TARGET"},
        {"resolution_timeframe","15m"},{"source_scan_id","scan-1"},
        {"source_l1_sha256",hash},{"source_universe_status","VERIFIED"},
        {"outcome_kind","HYPOTHESIS_PROXY"},{"resolution_data_sha256",hash},
        {"resolution_bars",json::array({{{"timestamp_ms",closed-900'000LL},
            {"open",100.0},{"high",101.0},{"low",99.5},{"close",100.5}}})},
        {"cost_model_id","SHADOW_COST_PROXY_V1"},
        {"fee_rate_per_side",0.0004},{"fee_assumption_class","ASSUMED"},
        {"fee_assumption_ref","V18.2_G3_REFERENCE_FEE_0.04_PERCENT_ASSUMED_PER_SIDE"},
        {"slippage_rate_per_side",0.001},{"slippage_assumption_class","PROXY"},
        {"slippage_proxy_method","FIXED_RATE_NOT_MEASURED_FROM_ORDER_BOOK"},
        {"slippage_source_status","UNAVAILABLE_MARKET_IMPACT_MEASUREMENT"},
        {"funding_source","OKX_PUBLIC_FUNDING_HISTORY"},
        {"cost_source_run_id","run-1"},{"cost_source_scan_id","scan-1"},
        {"cost_source_l1_sha256",hash},{"cost_as_of_time_ms",closed}
    };
}
json ledger() {
    constexpr std::int64_t day=86'400'000LL;
    return {{"schema_version","1.0.0"},{"artifact_type","cfss_outcome_ledger_v1"},
        {"profile","DAILY_SWING"},{"ledger_status","AVAILABLE"},
        {"outcomes",json::array({outcome("signal-a",day+10'000,2.0,0.0),
                                 outcome("signal-b",day*2+10'000,0.0,1.0)})}};
}
json registry() {
    return {{"schema_version","1.0.0"},
        {"artifact_type","cfss_shadow_candidate_registry_v1"},
        {"candidates",json::array({
            {{"signal_id","signal-a"},{"state","RESOLVED"},{"entry_fill_reference",100.0}},
            {{"signal_id","signal-b"},{"state","RESOLVED"},{"entry_fill_reference",100.0}}
        })}};
}
}

int main() {
    constexpr std::int64_t day=86'400'000LL;
    check(cfss::shadow_risk::utc_week(3LL*day+1LL)==0LL,
          "ISO week includes Sunday before Monday reset");
    check(cfss::shadow_risk::utc_week(4LL*day+1LL)==1LL,
          "ISO week resets at Monday 00:00 UTC");
    auto b=basis(); auto l=ledger(); auto r=registry();
    auto s=cfss::shadow_risk::build_snapshot(b,l,r,"run-1","scan-1",day*2+20'000,0);
    check(s["status"]=="AVAILABLE","complete costed closed ledger creates snapshot");
    check(s["data_class"]=="PROXY","proxy costs remain explicitly labelled");
    check(s["user_account_data_used"]==false,"snapshot never uses user account data");
    check(std::abs(s["current_nav_units"].get<double>()-100.2946)<1e-8,
          "net R is compounded against frozen normalized shadow NAV");
    check(std::abs(s["portfolio_drawdown_pct"].get<double>()-0.6)<1e-8,
          "drawdown is measured from portfolio high-water mark");
    check(std::abs(s["daily_loss_pct"].get<double>()-0.6)<1e-8,
          "current UTC day loss is measured against day-start shadow NAV");
    check(s["weekly_loss_pct"].get<double>()==0.0,
          "profitable current ISO week has no weekly loss");

    auto overlapping=l;
    overlapping["outcomes"][1]["entry_fill_time_ms"] =
        overlapping["outcomes"][0]["entry_fill_time_ms"].get<std::int64_t>() + 500LL;
    auto blocked=cfss::shadow_risk::build_snapshot(b,overlapping,r,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="OVERLAPPING_SHADOW_OUTCOMES_ENTRY_NAV_UNAVAILABLE",
          "overlapping trades fail closed when entry NAV cannot be reconstructed");

    auto missing_entry_time=l;
    missing_entry_time["outcomes"][0].erase("entry_fill_time_ms");
    blocked=cfss::shadow_risk::build_snapshot(b,missing_entry_time,r,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="OUTCOME_TIME_OR_ID_INVALID",
          "missing entry-time provenance cannot be inferred");

    auto bad_ledger=l;
    bad_ledger["outcomes"][0]["cost_status"]="UNAVAILABLE";
    blocked=cfss::shadow_risk::build_snapshot(b,bad_ledger,r,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="OUTCOME_COST_OR_PROVENANCE_UNAVAILABLE",
          "unavailable costs fail closed rather than becoming zero");

    auto open_registry=r;
    open_registry["candidates"].push_back({
        {"signal_id","signal-open"},{"state","PENDING"},{"entry_fill_reference",100.0}});
    blocked=cfss::shadow_risk::build_snapshot(b,l,open_registry,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="UNACCOUNTED_FILLED_SHADOW_CANDIDATE",
          "any filled candidate without a resolved ledger outcome blocks the snapshot");

    auto rejected_filled_registry=r;
    rejected_filled_registry["candidates"][0]["state"]="REJECTED";
    blocked=cfss::shadow_risk::build_snapshot(
        b,l,rejected_filled_registry,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="UNACCOUNTED_FILLED_SHADOW_CANDIDATE",
          "a filled candidate cannot disappear from risk accounting by being marked REJECTED");

    auto missing_resolved_outcome_registry=r;
    missing_resolved_outcome_registry["candidates"].push_back({
        {"signal_id","signal-without-outcome"},{"state","RESOLVED"},{"entry_fill_reference",100.0}});
    blocked=cfss::shadow_risk::build_snapshot(
        b,l,missing_resolved_outcome_registry,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="RESOLVED_CANDIDATE_OUTCOME_MISSING",
          "resolved candidate without a ledger row fails closed");

    // افت روزانه/هفتگی حتی پس از بازیابی در همان دوره باید sticky بماند.
    auto recovery_ledger=ledger();
    recovery_ledger["outcomes"]=json::array({
        outcome("loss-before-recovery",day+10'000,0.0,10.0),
        outcome("win-after-recovery",day+20'000,10.0,0.0)
    });
    auto recovery_registry=registry();
    recovery_registry["candidates"][0]["signal_id"]="loss-before-recovery";
    recovery_registry["candidates"][1]["signal_id"]="win-after-recovery";
    auto recovered=cfss::shadow_risk::build_snapshot(
        b,recovery_ledger,recovery_registry,"run-1","scan-1",day+30'000,0);
    check(recovered["status"]=="AVAILABLE",
          "non-overlapping loss and recovery outcomes produce a valid snapshot");
    check(recovered["daily_loss_pct"].get<double>()>=5.0,
          "daily kill-switch breach remains visible after same-day recovery");
    check(recovered["weekly_loss_pct"].get<double>()>=5.0,
          "weekly loss remains visible after same-week recovery");

    auto unfrozen=b; unfrozen["basis_status"]="DRAFT";
    blocked=cfss::shadow_risk::build_snapshot(unfrozen,l,r,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="RISK_BASIS_INVALID_OR_NOT_FROZEN",
          "unfrozen risk basis is rejected");

    auto future=l; future["outcomes"][1]["closed_at_ms"]=day*3;
    blocked=cfss::shadow_risk::build_snapshot(b,future,r,"run-1","scan-1",day*2+20'000,0);
    check(blocked["status"]=="UNAVAILABLE" &&
          blocked["reason"]=="OUTCOME_TIME_OR_ID_INVALID",
          "future outcome is rejected");

    std::cout << (failures==0 ? "SHADOW_RISK_SNAPSHOT_TESTS_PASS: " :
                                  "SHADOW_RISK_SNAPSHOT_TESTS_FAIL: ")
              << failures << "/" << checks << " failed\n";
    return failures==0 ? 0 : 1;
}
