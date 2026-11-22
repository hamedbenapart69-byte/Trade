#include "cfss/stage1_btc_contract.hpp"

#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
using json = nlohmann::json;
constexpr std::int64_t HOUR = 3'600'000LL;
constexpr std::int64_t NOW = 1'800'000'000'000LL;
const std::string ARCHIVE = "stage1-unit-test-archive-bytes";

json sample_contract() {
    const auto start = ((NOW - 25LL * HOUR) / HOUR) * HOUR;
    json candles = json::array();
    for (std::int64_t i = 0; i < 24; ++i) {
        const auto ts = start + i * HOUR;
        candles.push_back({
            {"timestamp_ms", ts}, {"close_time_ms", ts + HOUR - 1},
            {"open", 100.0}, {"high", 105.0}, {"low", 99.0}, {"close", 103.0},
            {"volume", 1.25}, {"volume_quote", 128.75},
            {"taker_buy_base", 0.75}, {"taker_buy_quote", 77.25},
            {"price_currency", "USDT"}, {"volume_unit", "base_asset"},
            {"volume_base_currency", "BTC"}, {"volume_quote_currency", "USDT"},
            {"closed", true}, {"retrieved_at_utc", "2026-11-22T12:00:00Z"}
        });
    }
    const auto latest_close = candles.back().at("close_time_ms").get<std::int64_t>();
    return {
        {"schema_version", "1.0.0"},
        {"artifact_type", "cfss_stage1_btc_l1_v1"},
        {"run_id", "stage1-test-run"},
        {"scan_id", "scan-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        {"acquired_at_utc", "2026-11-22T12:00:00Z"},
        {"window", {{"timeframe", "1h"}, {"start_ms", start}, {"end_ms", latest_close}, {"closed_candles", 24}}},
        {"provider", {{"primary_provider_id", "binance_vision"}, {"data_class", "DAILY_ARCHIVE_DELAYED"},
                      {"realtime", false}, {"fallback_used", false}}},
        {"provenance", {{"sha256_verified", true}, {"source_files", json::array({
            {{"filename", "BTCUSDT-1h-2026-11-21.zip"},
             {"archive_url", "https://data.binance.vision/test.zip"},
             {"checksum_url", "https://data.binance.vision/test.zip.CHECKSUM"},
             {"sha256", cfss::sha256_hex(ARCHIVE)},
             {"checksum_file_sha256", std::string(64, 'a')},
             {"bytes", ARCHIVE.size()}, {"row_count", 24},
             {"first_timestamp_ms", start}, {"last_timestamp_ms", candles.back().at("timestamp_ms")}}
        })}}},
        {"freshness", {{"status", "DAILY_ARCHIVE_DELAYED"}, {"latest_candle_close_ms", latest_close},
                       {"staleness_ms", NOW - latest_close}, {"maximum_staleness_ms", 26LL * HOUR}}},
        {"instruments", json::array({
            {{"instrument_id", "BTCUSDT"}, {"unified_symbol", "BTC/USDT:USDT"},
             {"base", "BTC"}, {"quote", "USDT"}, {"settle", "USDT"},
             {"contract_type", "linear_perpetual"}, {"provider_id", "binance_vision"},
             {"timeframe", "1h"}, {"candles", candles}, {"funding", json::array()},
             {"open_interest", json::array()},
             {"availability", {{"ohlcv", "AVAILABLE"}, {"funding", "UNAVAILABLE"},
                               {"open_interest", "UNAVAILABLE"}}}}
        })},
        {"trading_decision", "NOT_IN_SCOPE"},
        {"signal_generation_enabled", false}
    };
}

void expect_reject(const std::string& name, const json& contract, std::int64_t now = NOW) {
    bool rejected = false;
    try {
        cfss::stage1::validate_btc_l1(contract, ARCHIVE, now);
    } catch (const std::exception&) {
        rejected = true;
    }
    if (!rejected) throw std::runtime_error("test_expected_rejection:" + name);
}

void expect_accept(const std::string& name, const json& contract) {
    cfss::stage1::validate_btc_l1(contract, ARCHIVE, NOW);
    std::cout << "PASS " << name << '\n';
}
}

int main() {
    try {
        auto valid = sample_contract();
        expect_accept("valid_24_closed_btc_candles", valid);
        cfss::stage1::validate_btc_l1(valid, ARCHIVE, NOW + 30'000LL);
        std::cout << "PASS python_cpp_clock_drift_under_5m\\n";

        auto bad_hash = valid;
        bad_hash["provenance"]["source_files"][0]["sha256"] = std::string(64, 'b');
        expect_reject("archive_sha256_mismatch", bad_hash);

        auto bad_schema = valid;
        bad_schema["schema_version"] = "2.0.0";
        expect_reject("unsupported_schema", bad_schema);

        auto wrong_symbol = valid;
        wrong_symbol["instruments"][0]["instrument_id"] = "ETHUSDT";
        expect_reject("wrong_instrument", wrong_symbol);

        auto short_series = valid;
        short_series["instruments"][0]["candles"].erase(0);
        expect_reject("less_than_24_candles", short_series);

        auto gap = valid;
        gap["instruments"][0]["candles"][10]["timestamp_ms"] =
            gap["instruments"][0]["candles"][10]["timestamp_ms"].get<std::int64_t>() + 3'600'000LL;
        expect_reject("candle_gap", gap);

        auto duplicate = valid;
        duplicate["instruments"][0]["candles"][10]["timestamp_ms"] =
            duplicate["instruments"][0]["candles"][9]["timestamp_ms"];
        expect_reject("duplicate_timestamp", duplicate);

        auto bad_ohlc = valid;
        bad_ohlc["instruments"][0]["candles"][4]["high"] = 101.0;
        expect_reject("invalid_ohlc_relationship", bad_ohlc);

        auto stale = valid;
        const auto latest_close = stale["freshness"]["latest_candle_close_ms"].get<std::int64_t>();
        const auto stale_now = latest_close + 26LL * HOUR;
        stale["freshness"]["staleness_ms"] = stale_now - latest_close;
        expect_reject("staleness_over_26h", stale, stale_now);

        auto future = valid;
        const auto future_now = future["instruments"][0]["candles"][23]["close_time_ms"].get<std::int64_t>() - 1;
        expect_reject("future_or_unclosed_candle", future, future_now);

        auto wrong_volume = valid;
        wrong_volume["instruments"][0]["candles"][0]["volume_unit"] = "contracts";
        expect_reject("volume_unit_mismatch", wrong_volume);

        auto signal_enabled = valid;
        signal_enabled["signal_generation_enabled"] = true;
        expect_reject("signal_generation_must_be_disabled", signal_enabled);

        auto l2 = cfss::stage1::build_no_signal_l2(valid, NOW);
        if (l2["instruments"][0]["state"] != "NO_QUALIFIED_SETUP" ||
            l2["instruments"][0]["actionable"] != false ||
            !cfss::verify_artifact_hash(l2)) {
            throw std::runtime_error("no_signal_l2_artifact_invalid");
        }
        std::cout << "PASS no_signal_l2_hash_and_state\n";
        std::cout << "STAGE1_CPP_TESTS=14_PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "STAGE1_CPP_TESTS=FAIL " << error.what() << '\n';
        return 1;
    }
}
