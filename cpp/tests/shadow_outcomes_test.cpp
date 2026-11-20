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
        {"crypto_universe", {{"status", "VERIFIED"}, {"provider_id", "coinpaprika"}}},
        {"instruments", {{
            {"unified_symbol", "BTC/USDT:USDT"},
            {"candles", candles}
        }}}
    };
}

nlohmann::json fixture_l1_with_funding(nlohmann::json l1) {
    auto& instrument = l1["instruments"][0];
    instrument["availability"] = {{"funding", "AVAILABLE"}};
    instrument["coverage"] = {{"funding_coverage_days", 30.0}};
    instrument["funding"] = nlohmann::json::array({
        {{"timestamp_ms", 3'600'000LL}, {"funding_rate", 0.0001}},
        {{"timestamp_ms", 7'200'000LL}, {"funding_rate", 0.0001}}
    });
    return l1;
}

nlohmann::json fixture_l1_15m(std::initializer_list<nlohmann::json> candles,
                              std::int64_t end_ms) {
    const nlohmann::json instruments = nlohmann::json::array({
        {
            {"instrument_id", "BTC-USDT-SWAP"},
            {"unified_symbol", "BTC/USDT:USDT"},
            {"timeframe", "15m"},
            {"data_quality", "REAL"},
            {"error", nullptr},
            {"candles", candles}
        }
    });
    return {
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_intraday_15m_market_data_v1"},
        {"source_run_id", "run-1"}, {"source_scan_id", "scan-1"},
        {"source_l1_sha256", std::string(64, 'a')},
        {"candles_sha256", cfss::sha256_hex(instruments.dump())},
        {"decision_time_ms", 3'600'000LL},
        {"window", {{"timeframe", "15m"}, {"end_ms", end_ms}}},
        {"provider_id", "okx"},
        {"status", "AVAILABLE"},
        {"instruments", instruments}
    };
}

nlohmann::json fixture_dual(
    const nlohmann::json& lrt,
    const nlohmann::json& nmt = nlohmann::json{{"status", "NO_QUALIFIED_SETUP"}}) {
    return {
        {"artifact_type", "cfss_dual_engine_report_v1"},
        {"source_run_id", "run-1"}, {"source_scan_id", "scan-1"},
        {"decision_time_ms", 3'600'000LL}, {"l1_sha256", std::string(64, 'a')},
        {"instruments", {{
            {"symbol", "BTC/USDT:USDT"}, {"lrt", lrt},
            {"nmt", nmt}
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

nlohmann::json candle(std::int64_t ts, double high, double low, double close,
                       double open = 100.0) {
    return {
        {"timestamp_ms", ts}, {"open", open}, {"high", high}, {"low", low}, {"close", close},
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
        target_l1, fixture_l1_15m({
            candle(3'600'000LL, 101.0, 99.0, 100.5),
            candle(4'500'000LL, 105.0, 99.5, 104.0)
        }, 10'800'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
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
    require(target_row.at("profile") == "DAILY_SWING" &&
            target_row.at("score_model_version") == "LFS_V2_PROXY" &&
            target.at("registry").at("candidates").front().at("score_model_version") == "LFS_V2_PROXY" &&
            target_row.at("entry_fill_reference") == 100.0 &&
            target_row.at("entry_model") == "NEXT_BAR_OPEN_PROXY" &&
            target_row.at("execution_status") == "NOT_EXECUTED" &&
            target_row.at("outcome_kind") == "HYPOTHESIS_PROXY" &&
            target_row.at("resolution_timeframe") == "15m" &&
            target_row.at("resolution_data_sha256").get<std::string>().size() == 64U &&
            target_row.at("resolution_bars").size() == 2U,
            "LRT outcome retains profile, 15m source fingerprint and exact resolution bars");

    const auto costed_l1 = fixture_l1_with_funding(target_l1);
    const auto costed_target = cfss::shadow::process(
        costed_l1, fixture_l1_15m({
            candle(3'600'000LL, 101.0, 99.0, 100.5),
            candle(4'500'000LL, 105.0, 99.5, 104.0)
        }, 10'800'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    const auto& costed_row = costed_target.at("ledger").at("outcomes").front();
    require(costed_row.at("cost_status") == "PROXY" &&
            costed_row.at("cost_model_id") == "SHADOW_COST_PROXY_V1" &&
            std::abs(costed_row.at("fee_r").get<double>() - 0.04) < 1e-9 &&
            std::abs(costed_row.at("slippage_r").get<double>() - 0.10) < 1e-9 &&
            std::abs(costed_row.at("funding_r").get<double>() - 0.005) < 1e-9,
            "proxy costs use explicit fee, conservative slippage and signed real funding in R");

    const auto short_costs = cfss::shadow::calculate_shadow_costs(
        costed_l1.at("instruments").front(), "SHORT", 100.0, 102.0,
        3'600'000LL, 5'400'000LL);
    require(short_costs.available && short_costs.funding_r < 0.0,
            "positive funding is a credit, not a cost, for a short position");

    auto backfill_ledger = target.at("ledger");
    const auto backfilled = cfss::shadow::process(
        costed_l1, fixture_l1_15m({}, 10'800'000LL),
        fixture_dual({{"status", "NO_QUALIFIED_SETUP"}}), liquidity,
        target.at("registry"), backfill_ledger);
    const auto& backfilled_row = backfilled.at("ledger").at("outcomes").front();
    require(backfilled_row.at("cost_status") == "PROXY" &&
            backfilled.at("ledger").at("cost_backfilled_this_run") == 1U &&
            backfilled_row.contains("cost_source_l1_sha256"),
            "legacy unresolved cost rows are backfilled with traceable current funding provenance");

    auto legacy_ledger = target.at("ledger");
    legacy_ledger["outcomes"][0].erase("score_model_version");
    const auto migrated_ledger = cfss::shadow::process(
        fixture_l1({}, 18'000'000LL), fixture_l1_15m({}, 18'000'000LL),
        fixture_dual({{"status", "NO_QUALIFIED_SETUP"}}), liquidity,
        target.at("registry"), legacy_ledger);
    require(migrated_ledger.at("ledger").at("outcomes").front().at("score_model_version") ==
                "LFS_V2_PROXY",
            "legacy closed outcomes are assigned their original path-specific score model version");

    const auto nmt_outcome = cfss::shadow::process(
        fixture_l1({
            candle(3'600'000LL, 105.0, 99.0, 104.0),
            candle(7'200'000LL, 103.0, 99.5, 102.0)
        }, 10'800'000LL),
        fixture_l1_15m({}, 10'800'000LL),
        fixture_dual({{"status", "NO_QUALIFIED_SETUP"}},
                     candidate("PLAN_A_NMT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(nmt_outcome.at("ledger").at("outcomes").size() == 1U &&
            nmt_outcome.at("ledger").at("outcomes").front().at("score_model_version") == "NSS_V2_PROXY" &&
            nmt_outcome.at("ledger").at("outcomes").front().at("resolution_timeframe") == "1h",
            "NMT outcome resolution uses completed 1h candles, independently of LRT 15m");

    const auto ambiguous_l1 = fixture_l1({
        candle(3'600'000LL, 105.0, 97.0, 101.0)
    }, 7'200'000LL);
    const auto ambiguous = cfss::shadow::process(
        ambiguous_l1, fixture_l1_15m({candle(3'600'000LL, 105.0, 97.0, 101.0)}, 7'200'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(ambiguous.at("ledger").at("outcomes").front().at("resolution") ==
                "STOP_FIRST_SAME_BAR_AMBIGUITY" &&
            !ambiguous.at("ledger").at("outcomes").front().at("win").get<bool>(),
            "same-bar stop and target ambiguity resolves adversely");

    const auto no_future_l1 = fixture_l1({
        candle(0LL, 105.0, 97.0, 100.0)
    }, 3'600'000LL);
    const auto no_future = cfss::shadow::process(
        no_future_l1, fixture_l1_15m({candle(2'700'000LL, 105.0, 97.0, 100.0)}, 3'600'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(no_future.at("ledger").at("outcomes").empty() &&
            no_future.at("registry").at("candidates").front().at("state") == "PENDING",
            "pre-decision candles cannot resolve a candidate");

    const auto gap_l1 = fixture_l1({
        candle(3'600'000LL, 101.0, 99.0, 100.5),
        candle(10'800'000LL, 105.0, 99.5, 104.0)
    }, 14'400'000LL);
    const auto gap_result = cfss::shadow::process(
        gap_l1, fixture_l1_15m({
            candle(3'600'000LL, 101.0, 99.0, 100.5),
            candle(5'400'000LL, 105.0, 99.5, 104.0)
        }, 14'400'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(gap_result.at("ledger").at("outcomes").empty() &&
            gap_result.at("registry").at("candidates").front().at("state") == "PENDING",
            "missing hourly candles block outcome resolution instead of assuming no barrier hit");

    const auto expired_gap_l1 = fixture_l1({
        candle(3'600'000LL, 101.0, 99.0, 100.5),
        candle(10'800'000LL, 105.0, 99.5, 104.0)
    }, 18'000'000LL);
    const auto expired_gap = cfss::shadow::process(
        expired_gap_l1, fixture_l1_15m({
            candle(3'600'000LL, 101.0, 99.0, 100.5),
            candle(5'400'000LL, 105.0, 99.5, 104.0)
        }, 18'000'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(expired_gap.at("ledger").at("outcomes").empty() &&
            expired_gap.at("registry").at("candidates").front().at("state") == "REJECTED" &&
            expired_gap.at("registry").at("candidates").front().at("skip_reason") ==
                "FUTURE_DATA_GAP_OR_INCOMPLETE_COVERAGE",
            "expired candidate with missing future candles is rejected, not converted to an outcome");

    auto legacy_registry = cfss::shadow::empty_registry();
    legacy_registry["candidates"].push_back({
        {"signal_id", std::string(64, 'b')}, {"state", "PENDING"},
        {"path", "PLAN_A_NMT"}, {"symbol", "MMT/USDT:USDT"}, {"direction", "LONG"}
    });
    const auto quarantined = cfss::shadow::process(
        no_future_l1, fixture_l1_15m({candle(2'700'000LL, 105.0, 97.0, 100.0)}, 3'600'000LL),
        fixture_dual({{"status", "NO_QUALIFIED_SETUP"}}), liquidity,
        legacy_registry, cfss::shadow::empty_ledger());
    require(quarantined.at("registry").at("candidates").front().at("state") == "REJECTED" &&
            quarantined.at("registry").at("candidates").front().at("skip_reason") ==
                "SOURCE_UNIVERSE_NOT_VERIFIED",
            "legacy pending candidates without crypto-universe provenance are quarantined");

    const auto missed_entry = cfss::shadow::process(
        target_l1, fixture_l1_15m({candle(3'600'000LL, 106.0, 104.5, 105.0, 105.0)}, 10'800'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(missed_entry.at("ledger").at("outcomes").empty() &&
            missed_entry.at("registry").at("candidates").front().at("state") == "MISSED_ENTRY",
            "target gap before proxy entry is recorded as missed, never as a filled win");

    const auto invalidated_entry = cfss::shadow::process(
        target_l1, fixture_l1_15m({candle(3'600'000LL, 99.0, 96.0, 97.0, 97.0)}, 10'800'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(invalidated_entry.at("ledger").at("outcomes").empty() &&
            invalidated_entry.at("registry").at("candidates").front().at("state") == "REJECTED",
            "stop gap before proxy entry is rejected without a fabricated trade");

    const auto unavailable_15m = cfss::shadow::process(
        fixture_l1({}, 18'000'000LL),
        fixture_l1_15m({}, 18'000'000LL),
        fixture_dual(candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0)),
        liquidity, cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(unavailable_15m.at("ledger").at("outcomes").empty() &&
            unavailable_15m.at("registry").at("candidates").front().at("state") == "REJECTED" &&
            unavailable_15m.at("registry").at("candidates").front().at("skip_reason") ==
                "RESOLUTION_DATA_UNAVAILABLE_AT_EXPIRY",
            "expired LRT candidate without 15m resolution data is rejected, not left pending");

    auto missing_target = candidate("PLAN_A_LRT", "LONG", 100.0, 98.0, 104.0);
    missing_target["target_reference"] = nullptr;
    const auto rejected = cfss::shadow::process(
        no_future_l1, fixture_l1_15m({candle(2'700'000LL, 105.0, 97.0, 100.0)}, 3'600'000LL),
        fixture_dual(missing_target), liquidity,
        cfss::shadow::empty_registry(), cfss::shadow::empty_ledger());
    require(rejected.at("registry").at("candidates").empty() &&
            rejected.at("registry").at("summary").at("rejected_this_run") == 1,
            "candidate without a real target level is rejected without fabricated levels");

    std::cout << "SHADOW_OUTCOME_TESTS_PASS\n";
    return 0;
}
