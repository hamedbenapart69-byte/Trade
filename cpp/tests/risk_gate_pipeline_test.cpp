#include "cfss/risk_gate_pipeline.hpp"
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
json base_l1() {
    return {{"schema_version","1.0.0"},{"run_id","run-1"},{"scan_id","scan-1"},
        {"instruments",json::array({{{"unified_symbol","BTC/USDT:USDT"},
        {"liquidity_status","ELIGIBLE"},{"turnover_24h_usd",20000000.0},
        {"liquidity_threshold_usd",10000000.0}}})}};
}
json base_liquidity() {
    return {{"artifact_type","cfss_liquidity_phase_v1"},{"source_run_id","run-1"},
        {"source_scan_id","scan-1"},{"decision_time_ms",1000},
        {"instruments",json::array({{{"symbol","BTC/USDT:USDT"},
        {"status","AVAILABLE"},{"phase","RANGE"}}})}};
}
json base_meta() {
    const std::string l1_raw = "l1-fixture";
    const std::string liquidity_raw = "liquidity-fixture";
    json engine = {{"path","PLAN_A_LRT"},{"candidate_status","NO_QUALIFIED_SETUP"},
        {"actionable",false},{"data_class","PROXY"},{"confidence_status","NOT_CALIBRATED"},
        {"calibration",{{"status","NOT_CALIBRATED"}}},{"ev_status","NOT_CALCULATED"},
        {"ev_net",nullptr}};
    json nmt = engine; nmt["path"]="PLAN_A_NMT";
    return {{"artifact_type","cfss_meta_cognition_v1"},{"source_run_id","run-1"},
        {"source_scan_id","scan-1"},{"decision_time_ms",1000},
        {"l1_sha256",cfss::sha256_hex(l1_raw)},
        {"liquidity_report_sha256",cfss::sha256_hex(liquidity_raw)},
        {"instruments",json::array({{{"symbol","BTC/USDT:USDT"},
        {"golden_rule",{{"veto",false}}},
        {"lrt",engine},{"nmt",nmt}}})}};
}
json available_snapshot() {
    return {{"artifact_type","cfss_shadow_risk_snapshot_v1"},
        {"snapshot_scope","CFSS_SHADOW_PORTFOLIO_ONLY"},{"user_account_data_used",false},
        {"status","AVAILABLE"},{"source_run_id","run-1"},{"source_scan_id","scan-1"},
        {"decision_time_ms",1000},{"daily_loss_pct",1.0},{"weekly_loss_pct",2.0},
        {"portfolio_drawdown_pct",3.0},{"correlated_candidate_exposures",0}};
}
}

int main() {
    const std::string l1_raw="l1-fixture", liquidity_raw="liquidity-fixture";
    auto l1=base_l1(); auto liq=base_liquidity(); auto meta=base_meta();
    auto report=cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,json::object());
    check(report["summary"]["candidate_count"]==0,"no candidate is reported");
    check(report["instruments"][0]["engines"]["lrt"]["reason"]=="NO_QUALIFIED_CANDIDATE",
          "no candidate receives explicit no-candidate reason");
    check(report["trade_execution_allowed"]==false && report["actionable"]==false,
          "global execution and actionability remain disabled");

    meta["instruments"][0]["lrt"]["candidate_status"]="CANDIDATE";
    meta["instruments"][0]["lrt"]["data_class"]="PROXY";
    report=cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,json::object());
    check(report["instruments"][0]["engines"]["lrt"]["reason"]=="REAL_DATA_REQUIRED",
          "proxy candidate is blocked before downstream gates");
    check(report["summary"]["blocked_count"]==2,"all engine paths are counted");

    meta["instruments"][0]["lrt"]["data_class"]="REAL";
    meta["instruments"][0]["lrt"]["confidence_status"]="CALIBRATED";
    meta["instruments"][0]["lrt"]["calibration"]={{"status","CALIBRATED"},
        {"avg_fee_r",0.0004},{"avg_slippage_r",0.001},{"avg_funding_r",0.0}};
    meta["instruments"][0]["lrt"]["ev_status"]="CALCULATED";
    meta["instruments"][0]["lrt"]["ev_net"]=0.12;
    report=cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,json::object());
    check(report["instruments"][0]["engines"]["lrt"]["reason"]=="RISK_SNAPSHOT_INVALID_OR_MISSING",
          "missing shadow risk snapshot blocks an otherwise eligible candidate");

    auto snapshot=available_snapshot();
    report=cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,snapshot);
    check(report["instruments"][0]["engines"]["lrt"]["decision"]=="RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
          "complete internal shadow snapshot allows manual review only");
    check(report["summary"]["actionable_count"]==0 && report["trade_execution_allowed"]==false,
          "risk pass never authorizes action or execution");

    snapshot["user_account_data_used"]=true;
    report=cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,snapshot);
    check(report["instruments"][0]["engines"]["lrt"]["reason"]=="RISK_SNAPSHOT_INVALID_OR_MISSING",
          "user account data cannot be used as a risk snapshot");

    meta["l1_sha256"]="0000000000000000000000000000000000000000000000000000000000000000";
    bool provenance_rejected=false;
    try { (void)cfss::risk::build_report(l1,liq,meta,l1_raw,liquidity_raw,json::object()); }
    catch (const std::invalid_argument&) { provenance_rejected=true; }
    check(provenance_rejected,"provenance mismatch is rejected");

    std::cout << (failures==0 ? "STAGE7_PIPELINE_TESTS_PASS: " : "STAGE7_PIPELINE_TESTS_FAIL: ")
              << failures << "/" << checks << " failed\n";
    return failures==0 ? 0 : 1;
}
