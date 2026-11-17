#include "cfss/http_utils.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/l1_contract.hpp"
#include "cfss/okx_provider.hpp"
#include "cfss/signal.hpp"
#include "cfss/telegram_l3.hpp"
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <iostream>
#include <limits>
#include <string>

namespace {
nlohmann::json sample_contract(std::int64_t now_ms) {
    const auto candle_ms = now_ms - 3'600'000;
    return {
        {"schema_version", "1.0.0"}, {"run_id", "test-run-001"},
        {"acquired_at_utc", "2026-11-17T12:00:00Z"},
        {"window", {{"timeframe", "1h"}, {"start_ms", now_ms - 7'200'000}, {"end_ms", now_ms}}},
        {"provider", {{"primary_provider_id", "okx"}, {"display_name", "OKX public REST"}, {"fallback_used", false}}},
        {"instruments", nlohmann::json::array({
            {
                {"instrument_id", "BTC-USDT-SWAP"}, {"unified_symbol", "BTC/USDT:USDT"},
                {"base", "BTC"}, {"quote", "USDT"}, {"settle", "USDT"},
                {"contract_type", "linear_perpetual"}, {"provider_id", "okx"}, {"timeframe", "1h"},
                {"candles", nlohmann::json::array({
                    {{"timestamp_ms", candle_ms}, {"open", 100.0}, {"high", 105.0},
                     {"low", 99.0}, {"close", 103.0}, {"volume", 10.0},
                     {"volume_unit", "contracts"}, {"volume_base", 0.1}, {"volume_base_currency", "BTC"},
                     {"volume_quote", 10.0}, {"volume_quote_currency", "USDT"},
                     {"closed", true}, {"retrieved_at_utc", "2026-11-17T12:00:00Z"}}
                })},
                {"funding", nlohmann::json::array({
                    {{"timestamp_ms", candle_ms}, {"funding_rate", nullptr}, {"mark_price", nullptr},
                     {"retrieved_at_utc", "2026-11-17T12:00:00Z"}}
                })},
                {"open_interest", nlohmann::json::array({
                    {{"timestamp_ms", candle_ms}, {"open_interest", 1000.0},
                     {"open_interest_unit", "contracts"}, {"open_interest_base", 0.1},
                     {"open_interest_base_currency", "BTC"}, {"open_interest_value_usd", nullptr},
                     {"open_interest_value_currency", "USD"}, {"retrieved_at_utc", "2026-11-17T12:00:00Z"}}
                })},
                {"availability", {{"ohlcv", "AVAILABLE"}, {"funding", "PARTIAL"},
                                  {"open_interest", "PARTIAL"}}}
            }
        })}
    };
}
}
int main() {
    const std::string input = std::string{"quote: \""} + '\n' + '\t';
    if (cfss::json_escape(input) != "quote: \\\"\\n\\t") {
        std::cerr << "JSON escaping test failed\n"; return EXIT_FAILURE;
    }
    const auto levels = cfss::calculate_long_levels(65000.0, 64000.0);
    if (levels.entry_price != 65000.0 || levels.stop_loss != 64000.0 ||
        levels.take_profit != 67000.0 || std::abs(levels.risk_reward - 2.0) > 1e-12 ||
        levels.used_fallback) {
        std::cerr << "Five-candle low LONG level calculation failed\n"; return EXIT_FAILURE;
    }
    const auto fallback = cfss::calculate_long_levels(65000.0, 0.0);
    if (std::abs(fallback.stop_loss - 64350.0) > 1e-9 ||
        std::abs(fallback.take_profit - 66300.0) > 1e-9 ||
        std::abs(fallback.risk_reward - 2.0) > 1e-12 || !fallback.used_fallback) {
        std::cerr << "Invalid stop 1% fallback calculation failed\n"; return EXIT_FAILURE;
    }

    nlohmann::json short_oi = nlohmann::json::array();
    for (std::int64_t i = 0; i < 99; ++i) {
        short_oi.push_back({{"timestamp_ms", 1'700'000'000'000LL + i * 3'600'000LL},
                            {"open_interest", 1000.0}});
    }
    nlohmann::json full_oi = nlohmann::json::array();
    for (std::int64_t i = 0; i < 720; ++i) {
        full_oi.push_back({{"timestamp_ms", 1'700'000'000'000LL + i * 3'600'000LL},
                           {"open_interest", 1000.0}});
    }
    if (cfss::okx::availability(short_oi, "open_interest", 29.0) != "PARTIAL" ||
        cfss::okx::availability(full_oi, "open_interest", 29.0) != "AVAILABLE" ||
        cfss::okx::availability(nlohmann::json::array(), "open_interest", 29.0) != "UNAVAILABLE") {
        std::cerr << "Open-interest 30-day coverage gate failed\n"; return EXIT_FAILURE;
    }

    const nlohmann::json valid_ticker = {{"last", "50000"}, {"volCcy24h", "250"}, {"vol24h", "250"}};
    const nlohmann::json ambiguous_ticker = {{"last", "50000"}, {"vol24h", "250"}};
    const auto turnover = cfss::okx::quote_turnover_usd(valid_ticker);
    if (!turnover || std::abs(*turnover - 12500000.0) > 1e-9 ||
        cfss::okx::quote_turnover_usd(ambiguous_ticker).has_value() ||
        !cfss::okx::passes_liquidity(10000000.01) ||
        cfss::okx::passes_liquidity(10000000.0) ||
        cfss::okx::passes_liquidity(std::numeric_limits<double>::quiet_NaN())) {
        std::cerr << "Quote-notional conversion or strict liquidity threshold failed\n"; return EXIT_FAILURE;
    }
    const nlohmann::json valid_contract = {
        {"state","live"},{"settleCcy","USDT"},{"ctType","linear"},{"ctValCcy","BTC"},
        {"ctVal","0.01"},{"ctMult","1"},{"tickSz","0.1"},{"lotSz","1"},
        {"minSz","1"},{"listTime","1600000000000"}
    };
    auto invalid_contract = valid_contract;
    invalid_contract["ctMult"] = "";
    if (!cfss::okx::valid_linear_usdt_contract(valid_contract,"BTC") ||
        cfss::okx::valid_linear_usdt_contract(invalid_contract,"BTC") ||
        cfss::okx::valid_linear_usdt_contract(valid_contract,"ETH")) {
        std::cerr << "Linear USDT perpetual contract metadata gate failed\n"; return EXIT_FAILURE;
    }

    const auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    const auto contract = sample_contract(now_ms);
    const auto artifact = cfss::build_l2_artifact(contract, now_ms);
    const auto atomic_test_dir = std::filesystem::temp_directory_path() /
        ("cfss-atomic-test-" + std::to_string(now_ms));
    const auto atomic_test_file = atomic_test_dir / "state.json";
    const std::string atomic_expected = std::string{R"({"status":"PENDING"})"} + "\n";
    cfss::write_file_atomic(atomic_test_file, atomic_expected);
    std::ifstream atomic_input(atomic_test_file, std::ios::binary);
    const std::string atomic_content{std::istreambuf_iterator<char>{atomic_input},
                                    std::istreambuf_iterator<char>{}};
    if (atomic_content != atomic_expected) {
        std::cerr << "Atomic state persistence content test failed\n";
        std::filesystem::remove_all(atomic_test_dir);
        return EXIT_FAILURE;
    }
    bool immutable_write_rejected = false;
    try { cfss::write_file_atomic(atomic_test_file, "overwrite", true); }
    catch (const std::runtime_error&) { immutable_write_rejected = true; }
    if (!immutable_write_rejected) {
        std::cerr << "Immutable artifact overwrite was not rejected\n";
        std::filesystem::remove_all(atomic_test_dir);
        return EXIT_FAILURE;
    }
    std::filesystem::remove_all(atomic_test_dir);
    auto hashed_artifact = artifact;
    cfss::add_artifact_hash(hashed_artifact);
    if (!cfss::verify_artifact_hash(hashed_artifact)) {
        std::cerr << "Immutable artifact SHA-256 verification failed\n"; return EXIT_FAILURE;
    }
    hashed_artifact["instruments"][0]["state"] = "BUY_NOW";
    if (cfss::verify_artifact_hash(hashed_artifact)) {
        std::cerr << "Tampered artifact passed SHA-256 verification\n"; return EXIT_FAILURE;
    }
    const auto& item = artifact.at("instruments").at(0);
    if (item.at("state") != "MARKET_DATA_DEGRADED" || item.at("actionable") != false ||
        item.at("confidence_status") != "NOT_CALIBRATED" || item.at("data_quality") != "PARTIAL" ||
        item.at("reason_code") != "FUNDING_DATA_DEGRADED") {
        std::cerr << "C10 partial-data safe-default state test failed\n"; return EXIT_FAILURE;
    }
    auto complete_contract = contract;
    complete_contract["instruments"][0]["funding"][0]["funding_rate"] = 0.0001;
    complete_contract["instruments"][0]["open_interest"][0]["open_interest_value_usd"] = 1000000.0;
    complete_contract["instruments"][0]["availability"]["funding"] = "AVAILABLE";
    complete_contract["instruments"][0]["availability"]["open_interest"] = "AVAILABLE";
    const auto complete_artifact = cfss::build_l2_artifact(complete_contract, now_ms());
    const auto& complete_item = complete_artifact.at("instruments").at(0);
    if (complete_item.at("state") != "NO_QUALIFIED_SETUP" || complete_item.at("actionable") != false ||
        complete_item.at("data_quality") != "REAL" ||
        complete_item.at("reason_code") != "NO_STRATEGY_ADMITTED") {
        std::cerr << "C10 full-data no-setup state test failed\n"; return EXIT_FAILURE;
    }
    auto duplicate = contract;
    duplicate["instruments"][0]["candles"].push_back(duplicate["instruments"][0]["candles"][0]);
    bool duplicate_rejected = false;
    try { (void)cfss::build_l2_artifact(duplicate, now_ms); }
    catch (const std::invalid_argument&) { duplicate_rejected = true; }
    if (!duplicate_rejected) {
        std::cerr << "Duplicate candle timestamps were not rejected\n"; return EXIT_FAILURE;
    }
    auto open_candle = contract;
    open_candle["instruments"][0]["candles"][0]["closed"] = false;
    bool open_rejected = false;
    try { (void)cfss::build_l2_artifact(open_candle, now_ms); }
    catch (const std::invalid_argument&) { open_rejected = true; }
    if (!open_rejected) {
        std::cerr << "Open candle was not rejected\n"; return EXIT_FAILURE;
    }
    auto not_perpetual = contract;
    not_perpetual["instruments"][0]["contract_type"] = "spot";
    bool identity_rejected = false;
    try { (void)cfss::build_l2_artifact(not_perpetual, now_ms); }
    catch (const std::invalid_argument&) { identity_rejected = true; }
    if (!identity_rejected) {
        std::cerr << "Non-perpetual contract was not rejected\n"; return EXIT_FAILURE;
    }
    auto non_finite = contract;
    non_finite["instruments"][0]["funding"][0]["funding_rate"] =
        std::numeric_limits<double>::infinity();
    bool non_finite_rejected = false;
    try { (void)cfss::build_l2_artifact(non_finite, now_ms); }
    catch (const std::invalid_argument&) { non_finite_rejected = true; }
    if (!non_finite_rejected) {
        std::cerr << "Non-finite funding value was not rejected\n"; return EXIT_FAILURE;
    }
    const nlohmann::json status_artifact = {
        {"artifact_type", "cfss_l2_status_v1"}, {"source_run_id", "run-test-01"},
        {"instruments", nlohmann::json::array({
            {{"symbol", "BTC/USDT:USDT"}, {"state", "NO_QUALIFIED_SETUP"}, {"actionable", false}},
            {{"symbol", "ETH/USDT:USDT"}, {"state", "MARKET_DATA_DEGRADED"}, {"actionable", false}}
        })}
    };
    const auto telegram_messages = cfss::telegram::build_status_messages(status_artifact, 20U);
    if (telegram_messages.size() != 1U ||
        telegram_messages[0].find("BTC/USDT:USDT") == std::string::npos ||
        telegram_messages[0].find("این پیام گزارش داده است") == std::string::npos) {
        std::cerr << "Telegram safe status message formatting failed\n"; return EXIT_FAILURE;
    }
    const auto delivered = cfss::telegram::classify_send_response(
        CURLE_OK, 200, R"({"ok":true,"result":{"message_id":77}})", "");
    const auto rate_limited = cfss::telegram::classify_send_response(
        CURLE_OK, 429, R"({"ok":false})", "");
    const auto server_error = cfss::telegram::classify_send_response(
        CURLE_OK, 503, "temporarily unavailable", "");
    const auto rejected = cfss::telegram::classify_send_response(
        CURLE_OK, 400, R"({"ok":false,"description":"bad request"})", "");
    const auto timeout = cfss::telegram::classify_send_response(
        CURLE_OPERATION_TIMEDOUT, 0, "", "timeout");
    const auto malformed = cfss::telegram::classify_send_response(
        CURLE_OK, 200, "not-json", "");
    if (delivered.status != "DELIVERED" || delivered.message_id != 77 ||
        rate_limited.status != "RETRYABLE_FAILURE" ||
        server_error.status != "RETRYABLE_FAILURE" ||
        rejected.status != "PERMANENT_FAILURE" ||
        timeout.status != "DELIVERY_UNKNOWN" ||
        malformed.status != "DELIVERY_UNKNOWN") {
        std::cerr << "Telegram HTTP outcome classification failed\n"; return EXIT_FAILURE;
    }
    if (!cfss::telegram::outbox_should_send(nlohmann::json{{"status", "PENDING"}, {"attempts", 0}}) ||
        !cfss::telegram::outbox_should_send(nlohmann::json{{"status", "RETRYABLE_FAILURE"}, {"attempts", 2}}) ||
        cfss::telegram::outbox_should_send(nlohmann::json{{"status", "RETRYABLE_FAILURE"}, {"attempts", 3}}) ||
        cfss::telegram::outbox_should_send(nlohmann::json{{"status", "DELIVERY_UNKNOWN"}, {"attempts", 1}})) {
        std::cerr << "Telegram bounded outbox retry policy failed\n"; return EXIT_FAILURE;
    }
    auto conditional_artifact = status_artifact;
    conditional_artifact["instruments"][0]["state"] = "CONDITIONAL_BUY";
    if (cfss::telegram::build_status_messages(conditional_artifact).empty()) {
        std::cerr << "Conditional C10 status was not delivered as a non-actionable report\n"; return EXIT_FAILURE;
    }
    if (cfss::telegram::reconcile_outbox_status("SENDING") != "DELIVERY_UNKNOWN" ||
        cfss::telegram::reconcile_outbox_status("DELIVERED") != "DELIVERED" ||
        cfss::telegram::reconcile_inbound_status("REPLY_SENDING") != "DELIVERY_UNKNOWN" ||
        cfss::telegram::reconcile_inbound_status("PROCESSED") != "PROCESSED") {
        std::cerr << "Telegram crash-recovery state reconciliation failed\n"; return EXIT_FAILURE;
    }
    const auto inbound_default = cfss::telegram::default_inbound_state();
    if (inbound_default.value("last_poll_status", std::string{}) != "NEVER_POLLED" ||
        inbound_default.value("poll_count", -1LL) != 0LL ||
        !inbound_default.at("processed_updates").is_object()) {
        std::cerr << "Telegram inbound poll evidence defaults failed\n"; return EXIT_FAILURE;
    }
    if (cfss::telegram::command_reply("/status").empty() ||
        cfss::telegram::command_reply("/help").empty() ||
        !cfss::telegram::command_reply("/unknown").empty()) {
        std::cerr << "Telegram inbound command allowlist failed\n"; return EXIT_FAILURE;
    }
    auto actionable_artifact = status_artifact;
    actionable_artifact["instruments"][0]["state"] = "BUY_NOW";
    actionable_artifact["instruments"][0]["actionable"] = true;
    bool actionable_blocked = false;
    try { (void)cfss::telegram::build_status_messages(actionable_artifact); }
    catch (const std::invalid_argument&) { actionable_blocked = true; }
    if (!actionable_blocked) {
        std::cerr << "Unvalidated actionable Telegram message was not blocked\n"; return EXIT_FAILURE;
    }
    std::cout << "L1/L2 contract, C10 safety and Telegram outbox tests passed\n";
    return EXIT_SUCCESS;
}
