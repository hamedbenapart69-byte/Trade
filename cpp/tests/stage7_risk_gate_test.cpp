#include "cfss/risk_gate.hpp"
#include <cassert>
#include <iostream>
using namespace cfss::risk;
Input ready(){Input x;x.candidate_present=true;x.data_real=true;x.liquidity_ok=true;x.calibration_valid=true;x.net_ev_r=.15;x.costs_complete=true;x.risk_snapshot_valid=true;x.daily_loss_pct=1.;x.weekly_loss_pct=2.;x.portfolio_drawdown_pct=10.;x.correlated_open_exposures=1;return x;}
int main(){
 auto x=evaluate(Input{});assert(x.reason=="NO_QUALIFIED_CANDIDATE");
 x=ready();x.golden_rule_veto=true;assert(evaluate(x).reason=="GOLDEN_RULE_HARD_VETO");
 x=ready();x.candidate_actionable=true;assert(evaluate(x).reason=="UPSTREAM_ACTIONABILITY_FORBIDDEN");
 x=ready();x.calibration_valid=false;assert(evaluate(x).reason=="CALIBRATION_NOT_VALID");
 x=ready();x.net_ev_r=0.;assert(evaluate(x).reason=="NET_EV_NON_POSITIVE");
 x=ready();x.costs_complete=false;assert(evaluate(x).reason=="COSTS_INCOMPLETE");
 x=ready();x.daily_loss_pct=5.;assert(evaluate(x).reason=="G7_DAILY_KILL_SWITCH_5_PERCENT");
 x=ready();x.weekly_loss_pct=10.;assert(evaluate(x).reason=="G7_WEEKLY_KILL_SWITCH_10_PERCENT");
 x=ready();x.portfolio_drawdown_pct=20.1;assert(evaluate(x).reason=="PORTFOLIO_DRAWDOWN_OVER_20_PERCENT");
 x=ready();x.correlated_open_exposures=3;assert(evaluate(x).reason=="G5_CORRELATED_EXPOSURE_CAP");
 x=ready();x.risk_snapshot_valid=false;assert(evaluate(x).reason=="RISK_SNAPSHOT_INVALID_OR_MISSING");
 x=ready();x.data_real=false;assert(evaluate(x).reason=="REAL_DATA_REQUIRED");
 x=ready();x.liquidity_ok=false;assert(evaluate(x).reason=="LIQUIDITY_GATE_NOT_PASSED");
 x=ready();auto d=evaluate(x);assert(d.status=="RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY"&&!d.trade_execution_allowed&&d.manual_review_required);
 stdcout<<"STAGE7_RISK_GATE_TESTS_PASS\n";
}