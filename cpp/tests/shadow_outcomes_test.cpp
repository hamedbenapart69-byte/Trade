#include "cfss/shadow_outcomes.hpp"

#include <cstdlib>
#include <iostream>

namespace {
void require(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

nlohmann::json candidate(const char* path, const char* direction,
                         double entry, double stop, double target) {
    return {
        {"path", path}, {"status", "CANDIDATE"}, {"direction", direction},
        {"score", 0.8}, {"data_class", "PROXY"},
        {"hypothesis", "A registered causal hypothesis."},
        {"falsification", "A registered invalidation condition."},
        {"entry_reference", entry}, {"invalidation_reference", stop},
        {"target_reference", target}, {"decision_time_ms", 3'600'000LL}
    };
}

nlohmann::json fixture_l1(std::initializer_list<nlohmann::json> candles,
                          std::int64_t end_ms) {
    return {
        {"schema_version", "1.0.0"}, {"run_id", "run-1"}, {"scan_id", "scan-1"},
        {"window", {{"timeframe", "1h"}, {"end_ms", end_ms}}},
        {"instruments", {{
            {"unified_symbol", "BTC/USDT:USDT"},
            {"candles", candles}
        }}}
    };
}

nlohmann::json fixture_dual(const nlohmann::json& lrt) {
    return {
        {"artifact_type", "cfss_dual_engine_report_v1"},
        {"source_run_id", "run-1"}, {"source_scan_id", "scan-1"},
        {"decision_time_ms", 3'600'000LL}, {"l1_sha256", std::string(64, 'a')},
        {"instruments", {{
            {"symbol", "BTC/USDT:USDT"}, {"lrt", lrt},
            {"nmt", {{"status", "NO_QUALIFIED_SETUP"}}}
        }}}
    };
}

nlohmann::json fixture_liquidity() {
    return {
        {"artifact_type", "cfss_liquidity_phase_v1"},
        {"source_run_id", "run-1"}, {"source_scan_id", "scan-1"},
        {"decision_time_ms", 3'600'000LL}, {"l1_sha256", std::string(64, 'a')},
        {"instruments", {{{"symbol", "BTC/USDT:USDT"}, {"phase", "UPTREND"}}}}
    };
}

nlohmann::json candle(std::int64_t ts, double high, double low, double close) {
    return {
        {"timestamp_ms", ts}, {"high", high}, {"low", low}, {"close", close},
        {"closed", true}
    };
}
}

int main() {
    const auto liquidity = fixture_liquidity();

    const auto target_l1 = fixture_l1({
        candle(3'600'000LL, 101.0, 99.0, 100.5),
        candle(7'200'000LL, 105.0, 99.5, 104.0)
    }, 10'800'000LL);
    const auto target = cfss::shadow::process(
        target_l1, fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(target.at("ledger").at("outcomes").size() == 1U,
            "future target hit creates one closed shadow outcome");
    const auto& target_row = target.at("ledger").at("outcomes").front();
    require(target_row.at("resolution") == "TARGET" &&
            target_row.at("win").get<bool>() &&
            std::abs(target_row.at("win_r").get<double>() - 2.0) < 1e-9,
            "target resolution uses gross R against the original stop distance");
    require(target_row.at("fee_r").is_null() &&
            target_row.at("slippage_r").is_null() &&
            target_row.at("funding_r").is_null() &&
            target_row.at("cost_status") == "UNAVAILABLE",
            "missing costs remain explicitly unavailable, never fabricated");

    const auto ambiguous_l1 = fixture_l1({
        candle(3'600'000LL, 105.0, 97.0, 101.0)
    }, 7'200'000LL);
    const auto ambiguous = cfss::shadow::process(
        ambiguous_l1, fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(ambiguous.at("ledger").at("outcomes").front().at("resolution") ==
                "STOP_FIRST_SAME_BAR_AMBIGUITY" &&
            !ambiguous.at("ledger").at("outcomes").front().at("win").get<bool>(),
            "same-bar stop and target ambiguity resolves adversely");

    const auto no_future_l1 = fixture_l1({
        candle(0LL, 105.0, 97.0, 100.0)
    }, 3'600'000LL);
    const auto no_future = cfss::shadow::process(
        no_future_l1, fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(no_future.at("ledger").at("outcomes").empty() &&
            no_future.at("registry").at("candidates").front().at("state") == "PENDING",
            "pre-decision candles cannot resolve a candidate");

    const auto gap_l1 = fixture_l1({
        candle(3'600'000LL, 101.0, 99.0, 100.5),
        candle(10'800'000LL, 105.0, 99.5, 104.0)
    }, 14'400'000LL);
    const auto gap_result = cfss::shadow::process(
        gap_l1, fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(gap_result.at("ledger").at("outcomes").empty() &&
            gap_result.at("registry").at("candidates").front().at("state") == "PENDING",
            "missing hourly candles block outcome resolution instead of assuming no barrier hit");

    auto missing_target = candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0);
    missing_target["target_reference"] = nullptr;
    const auto rejected = cfss::shadow::process(
        no_future_l1, fixture_dual(missing_target), liquidity,
        cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(rejected.at("registry").at("candidates").empty() &&
            rejected.at("registry").at("summary").at("rejected_this_run") == 1,
            "candidate without a real target level is rejected without fabricated levels");

    std::cout << "SHADOW_OUTCOME_TESTS_PASS\n";
    return 0;
}
