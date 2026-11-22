#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>

namespace cfss::backtest {
using Json=nlohmann::json;
struct Bar { std::int64_t ts{}; double open{},high{},low{},close{}; };
struct Candidate {
 std::string id,path,symbol,direction,parameter_hash,data_class;
 std::int64_t signal_ms{},registered_ms{};
 double entry{},stop{},target{};
 std::size_t max_bars{};
};
struct Costs { double entry_fee{},exit_fee{},entry_slippage{},exit_slippage{},funding_per_8h{}; };
struct Input { std::string dataset_id; double risk_fraction{}; Costs costs; std::map<std::string,std::vector<Bar>> bars; std::vector<Candidate> candidates; };
struct Trade { std::string id,path,symbol,outcome; std::int64_t entry_ms{},exit_ms{}; double gross_r{},net_r{},net_return{}; };
struct Metrics {
 std::size_t trades{},wins{},losses{},censored{};
 std::optional<double> win_rate,ci_low,ci_high,pf,expectancy_r,max_dd_pct,sharpe;
 std::string dsr{"UNAVAILABLE"},pbo{"UNAVAILABLE"},brier{"UNAVAILABLE"};
};
struct Fold { std::int64_t train_start{},test_start{},test_end{}; Metrics lrt,nmt; };
struct Report { std::string status{"ENGINEERING_REPORT_ONLY"},dataset_id,data_class{"UNKNOWN"}; std::vector<Fold> folds; Metrics lrt,nmt; };

inline std::int64_t add_months(std::int64_t ms,int count) {
 using namespace std::chrono;
 const sys_time<milliseconds> p{milliseconds{ms}};
 const auto day_floor=floor<days>(p); const auto tod=p-day_floor; const year_month_day ymd{day_floor};
 const year_month ym=ymd.year()/ymd.month()+months{count};
 const year_month_day_last last{ym/std::chrono::last};
 const unsigned d=std::min(unsigned(ymd.day()),unsigned(last.day()));
 return duration_cast<milliseconds>((sys_days{ym/std::chrono::day{d}}).time_since_epoch()+tod).count();
}
inline void validate(const Input& x) {
 if(x.dataset_id.empty()) throw std::invalid_argument("DATASET_ID_REQUIRED");
 if(!std::isfinite(x.risk_fraction)||x.risk_fraction<=0||x.risk_fraction>1.0) throw std::invalid_argument("RISK_FRACTION_INVALID");
 auto cost=[](double v){return std::isfinite(v)&&v>=0;};
 if(!cost(x.costs.entry_fee)||!cost(x.costs.exit_fee)||!cost(x.costs.entry_slippage)||!cost(x.costs.exit_slippage)||!cost(x.costs.funding_per_8h)||x.costs.entry_slippage>=1.0||x.costs.exit_slippage>=1.0) throw std::invalid_argument("COST_INPUT_INVALID");
 if(x.bars.empty()) throw std::invalid_argument("OHLCV_REQUIRED");
 for(const auto& [s,v]:x.bars) {
  if(s.empty()||v.size()<2) throw std::invalid_argument("BAR_SERIES_TOO_SHORT");
  std::int64_t prev=0;
  for(const auto& b:v) {
   if(b.ts<=prev||!std::isfinite(b.open)||!std::isfinite(b.high)||!std::isfinite(b.low)||!std::isfinite(b.close)||b.open<=0||b.low<=0||b.high<std::max(b.open,b.close)||b.low>std::min(b.open,b.close)||b.high<b.low) throw std::invalid_argument("BAR_ORDER_OR_OHLC_INVALID");
   prev=b.ts;
  }
 }
 std::set<std::string> ids;
 for(const auto& c:x.candidates) {
  if(c.id.empty()||!ids.insert(c.id).second) throw std::invalid_argument("CANDIDATE_ID_DUPLICATE");
  if(c.data_class!="REAL"&&c.data_class!="PROXY") throw std::invalid_argument("CANDIDATE_DATA_CLASS_INVALID");
  if((c.path!="PLAN_A_LRT"&&c.path!="PLAN_A_NMT")||(c.direction!="LONG"&&c.direction!="SHORT")) throw std::invalid_argument("PATH_OR_DIRECTION_INVALID");
  const bool hash_valid=c.parameter_hash.size()==64&&std::all_of(c.parameter_hash.begin(),c.parameter_hash.end(),[](unsigned char ch){return (ch>='0'&&ch<='9')||(ch>='a'&&ch<='f');});
  if(!x.bars.contains(c.symbol)||c.signal_ms<=0||c.registered_ms<=0||c.registered_ms>c.signal_ms||!hash_valid||c.max_bars==0||!std::isfinite(c.entry)||!std::isfinite(c.stop)||!std::isfinite(c.target)||c.entry<=0||c.stop<=0||c.target<=0) throw std::invalid_argument("CANDIDATE_CONTRACT_INVALID");
  const bool geometry=c.direction=="LONG"?(c.stop<c.entry&&c.target>c.entry):(c.target<c.entry&&c.stop>c.entry);
  if(!geometry) throw std::invalid_argument("RISK_GEOMETRY_INVALID");
 }
}
inline std::optional<Trade> simulate(const Input& x,const Candidate& c,std::int64_t end_ms) {
 const auto& bars=x.bars.at(c.symbol);
 const auto it=std::upper_bound(bars.begin(),bars.end(),c.signal_ms,[](std::int64_t t,const Bar& b){return t<b.ts;});
 if(it==bars.end()||it->ts>=end_ms) return std::nullopt;
 const bool lng=c.direction=="LONG";
 const double fill=it->open*(lng?1+x.costs.entry_slippage:1-x.costs.entry_slippage);
 // Fail closed: if the opening fill already crossed the candidate stop, do not simulate a trade.
 if((lng&&fill<=c.stop)||(!lng&&fill>=c.stop)) return std::nullopt;
 const double risk=std::abs(fill-c.stop); if(risk<=0||fill<=0) return std::nullopt;
 double exit=0; std::int64_t exit_ms=0; std::string outcome="TIME_EXIT"; std::size_t held=0;
 const auto available=static_cast<std::size_t>(std::distance(it,bars.end()));
 const auto count=std::min(c.max_bars,available);
 for(std::size_t i=0;i<count;++i) {
  const auto& b=*(it+static_cast<std::ptrdiff_t>(i)); if(b.ts>=end_ms) break;
  ++held; exit_ms=b.ts;
  const bool stop_hit=lng?b.low<=c.stop:b.high>=c.stop;
  const bool target_hit=lng?b.high>=c.target:b.low<=c.target;
  const bool stop_gap=lng?b.open<=c.stop:b.open>=c.stop;
  if(stop_hit) { exit=stop_gap?b.open:c.stop; outcome=stop_gap?"STOP_GAP":(target_hit?"AMBIGUOUS_STOP_FIRST":"STOP"); break; }
  if(target_hit) { exit=c.target; outcome="TARGET"; break; }
  if(i+1==c.max_bars) { exit=b.close; outcome="TIME_EXIT"; }
 }
 if(held==0||exit<=0) return std::nullopt;
 const double exit_fill=exit*(lng?1-x.costs.exit_slippage:1+x.costs.exit_slippage);
 const double gross=(lng?exit_fill-fill:fill-exit_fill)/fill;
 const double hours=std::max(0.0,double(exit_ms-it->ts)/3600000.0);
 const double funding=std::ceil(hours/8.0)*x.costs.funding_per_8h;
 const double net=gross-x.costs.entry_fee-x.costs.exit_fee-funding;
 const double unit_r=risk/fill;
 return Trade{c.id,c.path,c.symbol,outcome,it->ts,exit_ms,gross/unit_r,net/unit_r,net};
}
inline Metrics summarize(const std::vector<Trade>& trades,double risk_fraction) {
 Metrics m{}; m.trades=trades.size(); if(trades.empty()) return m;
 auto ordered=trades; std::sort(ordered.begin(),ordered.end(),[](const Trade& a,const Trade& b){return a.exit_ms<b.exit_ms;});
 double gp=0,gl=0,sum=0,equity=1,peak=1,dd=0; std::map<std::int64_t,double> daily;
 for(const auto& t:ordered) {
  if(t.net_r>0){++m.wins;gp+=t.net_r;} else if(t.net_r<0){++m.losses;gl+=std::abs(t.net_r);}
  sum+=t.net_r; equity*=std::max(0.0,1+t.net_r*risk_fraction); peak=std::max(peak,equity); if(peak>0) dd=std::max(dd,(peak-equity)/peak);
  daily[t.exit_ms/86400000LL]+=t.net_r*risk_fraction;
 }
 const double n=double(m.trades); m.win_rate=double(m.wins)/n;
 const double z=1.959963984540054,den=1+z*z/n,center=(*m.win_rate+z*z/(2*n))/den;
 const double margin=z*std::sqrt((*m.win_rate*(1-*m.win_rate)/n)+z*z/(4*n*n))/den;
 m.ci_low=std::max(0.0,center-margin); m.ci_high=std::min(1.0,center+margin);
 if(gl>0) { m.pf=gp/gl; }
 m.expectancy_r=sum/n; m.max_dd_pct=dd*100;
 if(daily.size()>1) {
  std::vector<double> v; const auto first_day=daily.begin()->first, last_day=daily.rbegin()->first;
  for(auto d=first_day;d<=last_day;++d)v.push_back(daily.contains(d)?daily.at(d):0.0);
  const double mean=std::accumulate(v.begin(),v.end(),0.0)/double(v.size()); double var=0;
  for(double a:v) { var+=(a-mean)*(a-mean); }
  var/=double(v.size()-1);
  if(var>0)m.sharpe=mean/std::sqrt(var)*std::sqrt(365.0);
 }
 return m;
}
inline Json metric_json(const Metrics& m) {
 return Json{{"trades",m.trades},{"wins",m.wins},{"losses",m.losses},{"censored",m.censored},
 {"win_rate",m.win_rate?Json(*m.win_rate):Json(nullptr)},
 {"win_rate_ci95_low",m.ci_low?Json(*m.ci_low):Json(nullptr)},
 {"win_rate_ci95_high",m.ci_high?Json(*m.ci_high):Json(nullptr)},
 {"net_profit_factor",m.pf?Json(*m.pf):Json(nullptr)},
 {"net_expectancy_r",m.expectancy_r?Json(*m.expectancy_r):Json(nullptr)},
 {"max_drawdown_pct",m.max_dd_pct?Json(*m.max_dd_pct):Json(nullptr)},
 {"sharpe_oos",m.sharpe?Json(*m.sharpe):Json(nullptr)},
 {"dsr_status",m.dsr},{"pbo_status",m.pbo},{"brier_status",m.brier}};
}
inline Report run(const Input& x) {
 validate(x); Report r{}; r.dataset_id=x.dataset_id;
 std::int64_t first=std::numeric_limits<std::int64_t>::max(),last=0;
 for(const auto& [s,v]:x.bars){(void)s;first=std::min(first,v.front().ts);last=std::max(last,v.back().ts);}
 std::vector<Trade> lrt_all,nmt_all; std::set<std::string> unique_assigned; std::size_t unique_lrt_censored=0,unique_nmt_censored=0;
 for(std::int64_t start=add_months(first,6);add_months(start,2)<=last;start=add_months(start,1)) {
  Fold f{}; f.train_start=add_months(start,-6); f.test_start=start; f.test_end=add_months(start,2);
  std::vector<Trade> lrt,nmt; std::size_t lrt_censored=0,nmt_censored=0;
  for(const auto& c:x.candidates) {
   if(c.signal_ms<start||c.signal_ms>=f.test_end||c.registered_ms>start) continue;
   const auto t=simulate(x,c,f.test_end);
   if(!t){if(c.path=="PLAN_A_LRT")++lrt_censored;else ++nmt_censored;if(unique_assigned.insert(c.id).second){if(c.path=="PLAN_A_LRT")++unique_lrt_censored;else ++unique_nmt_censored;}continue;}
   (c.path=="PLAN_A_LRT"?lrt:nmt).push_back(*t);
   if(unique_assigned.insert(c.id).second)(c.path=="PLAN_A_LRT"?lrt_all:nmt_all).push_back(*t);
  }
  f.lrt=summarize(lrt,x.risk_fraction); f.nmt=summarize(nmt,x.risk_fraction);
  f.lrt.censored=lrt_censored; f.nmt.censored=nmt_censored;
  r.folds.push_back(f);
 }
 r.lrt=summarize(lrt_all,x.risk_fraction); r.nmt=summarize(nmt_all,x.risk_fraction);
 r.lrt.censored=unique_lrt_censored; r.nmt.censored=unique_nmt_censored;
 bool any_real=false,any_proxy=false; for(const auto& c:x.candidates){any_real=any_real||c.data_class=="REAL";any_proxy=any_proxy||c.data_class=="PROXY";}
 r.data_class=any_proxy?(any_real?"MIXED_CANDIDATE_CLASSES":"PROXY_CANDIDATES"):(any_real?"REAL_CANDIDATE_CLASSES_BAR_PROVENANCE_UNVERIFIED":"NO_CANDIDATES");
 r.status="ENGINEERING_REPORT_ONLY";
 return r;
}
inline Json to_json(const Report& r) {
 Json folds=Json::array();
 for(const auto& f:r.folds) folds.push_back({{"train_start_ms",f.train_start},{"test_start_ms",f.test_start},{"test_end_ms",f.test_end},{"lrt",metric_json(f.lrt)},{"nmt",metric_json(f.nmt)}});
 return Json{{"schema_version","1.0.0"},{"artifact_type","cfss_plan_a_backtest_report_v1"},{"status",r.status},{"dataset_id",r.dataset_id},
 {"data_class",r.data_class},{"walk_forward",{{"train_months",6},{"test_months",2},{"step_months",1},{"chronological",true},{"overlapping_test_windows",true}}},
 {"lrt_unique_oos",metric_json(r.lrt)},{"nmt_unique_oos",metric_json(r.nmt)},
 {"baselines",{{"status","UNAVAILABLE"},{"ema_cross","UNAVAILABLE"},{"rsi","UNAVAILABLE"},{"buy_and_hold","UNAVAILABLE"}}},
 {"dsr_status","UNAVAILABLE"},{"pbo_status","UNAVAILABLE"},{"brier_status","UNAVAILABLE"},
 {"limitations",{"DSR requires registered trial distribution and effective trial count","PBO requires combinatorial cross-validation across frozen trials","Brier requires calibrated probabilities and resolved labels","EMA Cross, RSI and Buy-and-Hold baselines are not implemented in v1","Only pre-registered candidate events are evaluated; historical LFS/NSS signals are not reconstructed","Overlapping test folds are reported separately; unique OOS totals deduplicate candidate IDs"}},
 {"gate_status","NOT_EVALUATED_INCOMPLETE_EVIDENCE"},{"actionable",false},{"trade_execution_allowed",false}};
}
} // namespace cfss::backtest
