#pragma once
#include <cmath>
#include <optional>
#include <string>
namespace cfss::risk {
struct Input {
 bool candidate_present{false}, candidate_actionable{false}, golden_rule_veto{false};
 bool data_real{false}, liquidity_ok{false}, calibration_valid{false};
 std::optional<double> net_ev_r;
 bool costs_complete{false}, risk_snapshot_valid{false};
 std::optional<double> daily_loss_pct, weekly_loss_pct, portfolio_drawdown_pct;
 int correlated_open_exposures{};
};
struct Decision { std::string status{"BLOCKED"}, reason{"RISK_INPUTS_UNAVAILABLE"}; bool manual_review_required{true}, trade_execution_allowed{false}; };
inline bool valid_pct(const std::optional<double>& v){return v&&std::isfinite(*v)&&*v>=0&&*v<=100;}
inline Decision evaluate(const Input& i){
 Decision d;
 if(i.golden_rule_veto){d.reason="GOLDEN_RULE_HARD_VETO";return d;}
 if(!i.candidate_present){d.reason="NO_QUALIFIED_CANDIDATE";return d;}
 if(i.candidate_actionable){d.reason="UPSTREAM_ACTIONABILITY_FORBIDDEN";return d;}
 if(!i.data_real){d.reason="REAL_DATA_REQUIRED";return d;}
 if(!i.liquidity_ok){d.reason="LIQUIDITY_GATE_NOT_PASSED";return d;}
 if(!i.calibration_valid){d.reason="CALIBRATION_NOT_VALID";return d;}
 if(!i.net_ev_r||!std::isfinite(*i.net_ev_r)){d.reason="NET_EV_UNAVAILABLE";return d;}
 if(*i.net_ev_r<=0){d.reason="NET_EV_NON_POSITIVE";return d;}
 if(!i.costs_complete){d.reason="COSTS_INCOMPLETE";return d;}
 if(!i.risk_snapshot_valid||!valid_pct(i.daily_loss_pct)||!valid_pct(i.weekly_loss_pct)||!valid_pct(i.portfolio_drawdown_pct)||i.correlated_open_exposures<0){d.reason="RISK_SNAPSHOT_INVALID_OR_MISSING";return d;}
 if(*i.daily_loss_pct>=5){d.reason="G7_DAILY_KILL_SWITCH_5_PERCENT";return d;}
 if(*i.weekly_loss_pct>=10){d.reason="G7_WEEKLY_KILL_SWITCH_10_PERCENT";return d;}
 if(*i.portfolio_drawdown_pct>20){d.reason="PORTFOLIO_DRAWDOWN_OVER_20_PERCENT";return d;}
 if(i.correlated_open_exposures>=3){d.reason="G5_CORRELATED_EXPOSURE_CAP";return d;}
 d.status="RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY"; d.reason="ALL_RISK_CHECKS_PASSED_NO_EXECUTION_AUTHORIZATION"; return d;
}
}
