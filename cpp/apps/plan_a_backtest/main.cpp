#include "cfss/backtest.hpp"
#include <fstream>
#include <iostream>
int main(int argc,char** argv){
 if(argc!=3){std::cerr<<"usage: plan_a_backtest <input.json> <output.json>\n";return 2;}
 try{
  std::ifstream in(argv[1]);if(!in)throw std::runtime_error("INPUT_OPEN_FAILED");
  const auto j=nlohmann::json::parse(in);cfss::backtest::Input x{};
  x.dataset_id=j.at("dataset_id").get<std::string>();x.risk_fraction=j.at("risk_fraction").get<double>();
  const auto& c=j.at("costs");x.costs={c.at("entry_fee_rate").get<double>(),c.at("exit_fee_rate").get<double>(),c.at("entry_slippage_rate").get<double>(),c.at("exit_slippage_rate").get<double>(),c.at("funding_cost_rate_per_8h").get<double>()};
  for(const auto& b:j.at("bars"))x.bars[b.at("symbol").get<std::string>()].push_back({b.at("timestamp_ms").get<std::int64_t>(),b.at("open").get<double>(),b.at("high").get<double>(),b.at("low").get<double>(),b.at("close").get<double>()});
  for(const auto& a:j.at("candidates"))x.candidates.push_back({a.at("candidate_id").get<std::string>(),a.at("path").get<std::string>(),a.at("symbol").get<std::string>(),a.at("direction").get<std::string>(),a.at("parameter_hash").get<std::string>(),a.at("data_class").get<std::string>(),a.at("signal_time_ms").get<std::int64_t>(),a.at("registered_at_ms").get<std::int64_t>(),a.at("entry_reference").get<double>(),a.at("stop").get<double>(),a.at("target").get<double>(),a.at("max_holding_bars").get<std::size_t>()});
  std::ofstream out(argv[2]);if(!out)throw std::runtime_error("OUTPUT_OPEN_FAILED");out<<cfss::backtest::to_json(cfss::backtest::run(x)).dump(2)<<'\n';if(!out.good())throw std::runtime_error("OUTPUT_WRITE_FAILED");return 0;
 }catch(const std::exception& e){std::cerr<<"PLAN_A_BACKTEST_FAILED: "<<e.what()<<'\n';return 1;}
}