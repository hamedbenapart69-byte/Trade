#include "cfss/backtest.hpp"
#include <iostream>
#include <stdexcept>
using namespace cfss::backtest;
static void require(bool ok,const char* msg){if(!ok)throw std::runtime_error(msg);}
int main(){
 try{
  Input x{};x.dataset_id="synthetic-fixture-not-market-evidence";x.risk_fraction=0.01;x.costs={0.0004,0.0004,0.0002,0.0002,0.0001};
  const std::int64_t t0=1735689600000LL;std::vector<Bar> b;
  for(int i=0;i<280;++i)b.push_back({t0+std::int64_t(i)*86400000LL,100,100.5,99.5,100});
  b[182].high=111;b[182].close=110;b[202].high=111;b[202].low=94;
  x.bars["BTC-USDT-SWAP"]=b;
  x.candidates.push_back({"lrt-001","PLAN_A_LRT","BTC-USDT-SWAP","LONG",std::string(64,'a'),"REAL",t0+181LL*86400000LL,t0+100LL*86400000LL,100,95,110,3});
  x.candidates.push_back({"nmt-001","PLAN_A_NMT","BTC-USDT-SWAP","LONG",std::string(64,'b'),"REAL",t0+201LL*86400000LL,t0+120LL*86400000LL,100,95,110,3});
  x.candidates.push_back({"nmt-overlap-censored","PLAN_A_NMT","BTC-USDT-SWAP","LONG",std::string(64,'c'),"REAL",t0+230LL*86400000LL,t0+100LL*86400000LL,100,95,110,30});
  b[245].high=111; b[245].close=110;
  Input short_data{}; short_data.dataset_id="short-history-censor-fixture"; short_data.risk_fraction=0.01; short_data.costs=x.costs; short_data.bars["BTC-USDT-SWAP"]={{t0,100,100.5,99.5,100},{t0+86400000LL,100,100.5,99.5,100}}; Candidate short_candidate{"short-history","PLAN_A_LRT","BTC-USDT-SWAP","LONG",std::string(64,'d'),"REAL",t0,t0,100,95,110,3}; auto censored_short=simulate(short_data,short_candidate,t0+10LL*86400000LL); require(!censored_short.has_value(),"insufficient end-of-data bars censor trade instead of shortening holding period");
  const auto r=run(x);require(!r.folds.empty(),"walk-forward folds");require(r.lrt.trades==1,"LRT isolation");require(r.nmt.trades==1,"NMT isolation");require(r.nmt.censored==1,"unique OOS candidate censored in its first eligible fold is not promoted from a later overlapping fold");
  require(r.lrt.wins==1,"target is win");require(r.nmt.losses==1,"ambiguous bar stop-first");
  auto invalid_risk=x; invalid_risk.risk_fraction=1.01; bool risk_rejected=false; try{run(invalid_risk);}catch(const std::invalid_argument&){risk_rejected=true;}require(risk_rejected,"risk fraction above 100% is rejected");
  const auto j=to_json(r);require(j["baselines"]["status"]=="UNAVAILABLE","no fabricated baselines");
  require(j["gate_status"]=="NOT_EVALUATED_INCOMPLETE_EVIDENCE","fixture cannot pass Gate A");
  require(!j["actionable"].get<bool>()&&!j["trade_execution_allowed"].get<bool>(),"manual only");
  std::cout<<"STAGE8_PLAN_A_BACKTEST_TESTS_PASS\n";return 0;
 }catch(const std::exception& e){std::cerr<<"STAGE8_PLAN_A_BACKTEST_TESTS_FAIL: "<<e.what()<<'\n';return 1;}
}