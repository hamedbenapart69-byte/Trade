#include "cfss/l1_contract.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/okx_provider.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <set>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {
using json = nlohmann::json;

std::int64_t now_epoch_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

void write_json(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}

std::string csv_escape(const std::string& value) {
    if (value.find_first_of(",\"\n\r") == std::string::npos) return value;
    std::string escaped = "\"";
    for (const char ch : value) {
        if (ch == '"') escaped += "\"\"";
        else escaped += ch;
    }
    escaped += "\"";
    return escaped;
}

json artifact_entry(const std::filesystem::path& path, const std::string& raw,
                    bool retained_in_workflow, int retention_days,
                    bool retained_in_signals) {
    return {
        {"path", path.generic_string()}, {"sha256", cfss::sha256_hex(raw)},
        {"bytes", raw.size()}, {"retained_in_workflow_artifacts", retained_in_workflow},
        {"retention_days", retention_days}, {"retained_in_signals_branch", retained_in_signals}
    };
}

json build_run_manifest(const json& contract, const json& artifact,
                        const json& artifact_manifest, int symbols, int years,
                        const std::string& l1_raw) {
    const json config = {
        {"symbol_target", symbols}, {"years", years}, {"timeframe", "1h"},
        {"liquidity_threshold_usd", 10000000.0}, {"ohlcv_closed_bars_only", true}
    };
    bool all_real = true;
    json errors = json::array();
    for (const auto& item : artifact.at("instruments")) {
        if (item.value("data_quality", std::string{}) != "REAL") all_real = false;
    }
    for (const auto& item : contract.at("instruments")) {
        for (const auto& error : item.at("errors"))
            errors.push_back(item.at("instrument_id").get<std::string>() + ":" + error.get<std::string>());
    }
    for (const auto& provider : contract.at("provider_health").at("providers")) {
        if (provider.value("fallback_status", std::string{}) == "UNAVAILABLE")
            errors.push_back(provider.at("provider_id").get<std::string>() + ":" +
                             provider.value("fallback_reason", std::string{"fallback_unavailable"}));
    }

    const char* commit = std::getenv("GITHUB_SHA");
    const char* branch = std::getenv("GITHUB_REF_NAME");
    const char* build_id = std::getenv("CFSS_BUILD_ID");
    const auto now_text = cfss::okx::utc_iso(now_epoch_ms());
    auto retry_summary = cfss::okx::request_metrics();
    retry_summary["telegram_send_attempts_total_for_scan"] = 0;
    retry_summary["telegram_retry_attempts_total_for_scan"] = 0;
    retry_summary["telegram_inbound_polls"] = 0;

    return {
        {"run_id", contract.at("run_id")}, {"scan_id", contract.at("scan_id")},
        {"run_timestamp_utc", contract.at("acquired_at_utc")},
        {"repository_commit", commit ? std::string{commit} : std::string{"UNKNOWN"}},
        {"branch", branch ? std::string{branch} : std::string{"UNKNOWN"}},
        {"document_version", "V18.2"},
        {"compiler_id", "GCC"}, {"compiler_version", __VERSION__},
        {"build_id", build_id ? std::string{build_id} : std::string{"UNAVAILABLE"}},
        {"configuration_version", "1.0.0"},
        {"configuration_hash", cfss::sha256_hex(config.dump())},
        {"dataset_version", contract.at("schema_version")},
        {"dataset_hash", cfss::sha256_hex(l1_raw)},
        {"provider_status", contract.at("provider_health")},
        {"profile", {{"symbol_target", symbols}, {"selected_symbols", contract.at("instruments").size()},
                     {"years", years}, {"timeframe", "1h"}, {"liquidity_threshold_usd", 10000000.0}}},
        {"path_statuses", {{"A", "NOT_STARTED"}, {"B", "NOT_STARTED"}, {"C", "NOT_STARTED"}, {"H", "NOT_STARTED"}}},
        {"generator_statuses", {{"H1", "NOT_STARTED"}, {"H2", "NOT_STARTED"}, {"H3", "NOT_STARTED"},
                                {"H4", "NOT_STARTED"}, {"H5", "NOT_STARTED"}, {"H6", "NOT_STARTED"}, {"H7", "NOT_STARTED"}}},
        {"run_status", all_real ? "L1_L2_PASS" : "DATA_DEGRADED"},
        {"start_time_utc", contract.at("acquired_at_utc")}, {"end_time_utc", now_text},
        {"error_summary", errors}, {"retry_summary", retry_summary},
        {"artifact_manifest", artifact_manifest},
        {"telegram_send_status", "NOT_ATTEMPTED"},
        {"telegram_receive_test_status", "NOT_REQUESTED"},
        {"telegram_message_ids", json::array()},
        {"telegram_last_update_id", 0}
    };
}

int run_collect(int symbols, int years, const std::filesystem::path& l1_path,
                const std::filesystem::path& l2_path,
                const std::optional<std::filesystem::path>& crypto_universe_cache_path,
                const std::optional<std::filesystem::path>& market_data_cache_path,
                const std::optional<std::filesystem::path>& pending_symbols_path) {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
        throw std::runtime_error("curl_global_init_failed");
    try {
        std::optional<json> cached_crypto_universe;
        if (crypto_universe_cache_path && std::filesystem::exists(*crypto_universe_cache_path)) {
            std::ifstream cache_input(*crypto_universe_cache_path, std::ios::binary);
            if (!cache_input) throw std::runtime_error("crypto_universe_cache_open_failed");
            cached_crypto_universe = json::parse(cache_input);
        }
        std::optional<json> cached_market_data;
        if (market_data_cache_path && std::filesystem::exists(*market_data_cache_path)) {
            try {
                std::ifstream market_cache_input(*market_data_cache_path, std::ios::binary);
                if (!market_cache_input) throw std::runtime_error("market_data_cache_open_failed");
                cached_market_data = json::parse(market_cache_input);
                const auto policy = cached_market_data->value("cache_policy", json::object());
                const bool valid_cache =
                    cached_market_data->is_object() &&
                    cached_market_data->value("schema_version", std::string{}) == "1.0.0" &&
                    cached_market_data->value("cache_contract_version", std::string{}) == "1.0.0" &&
                    cached_market_data->value("provider", json::object())
                        .value("primary_provider_id", std::string{}) == "okx" &&
                    policy.value("venue", std::string{}) == "OKX" &&
                    policy.value("market_type", std::string{}) == "LINEAR_PERPETUAL" &&
                    policy.value("window_policy", std::string{}) == "ROLLING_2Y_OHLCV_30D_DERIVATIVES" &&
                    policy.value("normalization_schema_version", std::string{}) == "1.0.0" &&
                    policy.value("timeframes", json::object()) ==
                        json{{"candles", "1H"}, {"funding", "8H"}, {"open_interest", "1H"}} &&
                    cached_market_data->contains("cache_entries") &&
                    cached_market_data->at("cache_entries").is_object() &&
                    cached_market_data->contains("instruments") &&
                    cached_market_data->at("instruments").is_array();
                if (!valid_cache) {
                    std::cerr << "MARKET_CACHE_MISS reason=cache_contract_mismatch\n";
                    cached_market_data.reset();
                }
            } catch (const std::exception& error) {
                std::cerr << "MARKET_CACHE_MISS reason=" << error.what() << '\n';
                cached_market_data.reset();
            }
        }
        std::set<std::string> required_symbols;
        if (pending_symbols_path && std::filesystem::exists(*pending_symbols_path)) {
            std::ifstream pending_input(*pending_symbols_path, std::ios::binary);
            if (!pending_input) throw std::runtime_error("pending_symbols_open_failed");
            const auto pending_json = json::parse(pending_input);
            if (!pending_json.is_array()) throw std::runtime_error("pending_symbols_must_be_array");
            for (const auto& value : pending_json) {
                if (!value.is_string()) continue;
                const auto unified = value.get<std::string>();
                const auto slash = unified.find('/');
                const auto base = cfss::okx::uppercase_symbol(
                    slash == std::string::npos ? unified : unified.substr(0U, slash));
                if (!base.empty()) required_symbols.insert(base);
            }
        }
        const auto contract = cfss::okx::collect(symbols, years, cached_crypto_universe,
                                                  cached_market_data, required_symbols,
                                                  market_data_cache_path);
        const std::string l1_raw = contract.dump(2) + "\n";
        cfss::write_file_atomic(l1_path, l1_raw, true);

        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        const std::string l2_raw = artifact.dump(2) + "\n";
        const auto evidence_dir = l1_path.parent_path().empty() ? std::filesystem::path{"."} : l1_path.parent_path();
        cfss::write_file_atomic(l2_path, l2_raw, true);

        const auto provider_path = evidence_dir / "provider-health.v1.json";
        const auto fear_path = evidence_dir / "fear-greed.v1.json";
        const auto crypto_universe_path = evidence_dir / "crypto-universe.v1.json";
        const auto signals_path = evidence_dir / "signals.json";
        const auto history_path = evidence_dir / "history.csv";
        const auto performance_path = evidence_dir / "performance.json";
        const auto coverage_path = evidence_dir / "coverage.json";
        const auto system_path = evidence_dir / "system_status.json";
        const auto manifest_path = evidence_dir / "run-manifest.v1.json";

        const std::string provider_raw = contract.at("provider_health").dump(2) + "\n";
        const std::string fear_raw = contract.at("fear_greed").dump(2) + "\n";
        const std::string crypto_universe_raw = contract.at("crypto_universe").dump(2) + "\n";
        write_json(provider_path, contract.at("provider_health"));
        write_json(fear_path, contract.at("fear_greed"));
        write_json(crypto_universe_path, contract.at("crypto_universe"));

        bool any_degraded = false;
        json signals = json::array();
        json status_report = json::array();
        for (const auto& item : artifact.at("instruments")) {
            status_report.push_back(item);
            if (item.value("state", std::string{}) == "MARKET_DATA_DEGRADED") any_degraded = true;
        }
        const auto generated_at = cfss::okx::utc_iso(now_epoch_ms());
        const std::string report_status = any_degraded ? "MARKET_DATA_DEGRADED" : "NO_QUALIFIED_SETUP";
        const json signals_json = {
            {"schema_version", "1.0.0"}, {"run_id", contract.at("run_id")},
            {"scan_id", contract.at("scan_id")}, {"generated_at_utc", generated_at},
            {"report_status", report_status}, {"signal_count", signals.size()},
            {"signals", signals}, {"status_report_count", status_report.size()},
            {"status_report", status_report},
            {"note", "Stage 1 has no admitted strategy engine; an empty signals array is intentional and is not a BUY or SELL recommendation."}
        };
        const std::string signals_raw = signals_json.dump(2) + "\n";
        write_json(signals_path, signals_json);

        json coverage_rows = json::array();
        std::size_t full_count = 0U, partial_count = 0U, unavailable_count = 0U;
        for (const auto& item : contract.at("instruments")) {
            const auto& availability = item.at("availability");
            const bool all_available = availability.value("ohlcv", std::string{}) == "AVAILABLE" &&
                                       availability.value("funding", std::string{}) == "AVAILABLE" &&
                                       availability.value("open_interest", std::string{}) == "AVAILABLE";
            const bool any_unavailable = availability.value("ohlcv", std::string{}) == "UNAVAILABLE" ||
                                         availability.value("funding", std::string{}) == "UNAVAILABLE" ||
                                         availability.value("open_interest", std::string{}) == "UNAVAILABLE";
            if (all_available) ++full_count;
            else if (any_unavailable) ++unavailable_count;
            else ++partial_count;
            coverage_rows.push_back({
                {"instrument_id", item.at("instrument_id")}, {"symbol", item.at("unified_symbol")},
                {"availability", availability}, {"coverage", item.at("coverage")}, {"errors", item.at("errors")}
            });
        }
        const json coverage_json = {
            {"schema_version", "1.0.0"}, {"run_id", contract.at("run_id")},
            {"scan_id", contract.at("scan_id")}, {"generated_at_utc", generated_at},
            {"universe", contract.at("universe")},
            {"summary", {{"fully_available_count", full_count}, {"partial_count", partial_count},
                         {"unavailable_count", unavailable_count}, {"selected_count", coverage_rows.size()}}},
            {"instruments", coverage_rows}
        };
        const std::string coverage_raw = coverage_json.dump(2) + "\n";
        write_json(coverage_path, coverage_json);

        const json performance_json = {
            {"schema_version", "1.0.0"}, {"run_id", contract.at("run_id")},
            {"scan_id", contract.at("scan_id")}, {"generated_at_utc", generated_at},
            {"status", "NOT_CALCULATED"}, {"trade_count", 0},
            {"metrics", {{"win_rate", nullptr}, {"profit_factor", nullptr}, {"sharpe", nullptr},
                         {"max_drawdown", nullptr}, {"expectancy", nullptr}}},
            {"reason", "NO_STRATEGY_ENGINE_OR_EXECUTED_TRADES_IN_STAGE_1"}
        };
        const std::string performance_raw = performance_json.dump(2) + "\n";
        write_json(performance_path, performance_json);

        const json path_statuses = {{"A", "NOT_STARTED"}, {"B", "NOT_STARTED"}, {"C", "NOT_STARTED"}, {"H", "NOT_STARTED"}};
        const json generator_statuses = {{"H1", "NOT_STARTED"}, {"H2", "NOT_STARTED"}, {"H3", "NOT_STARTED"},
                                              {"H4", "NOT_STARTED"}, {"H5", "NOT_STARTED"}, {"H6", "NOT_STARTED"}, {"H7", "NOT_STARTED"}};
        bool all_real = true;
        for (const auto& item : artifact.at("instruments"))
            if (item.value("data_quality", std::string{}) != "REAL") all_real = false;
        const std::string run_status = all_real ? "L1_L2_PASS" : "DATA_DEGRADED";
        json system_errors = json::array();
        for (const auto& item : contract.at("instruments"))
            for (const auto& error : item.at("errors"))
                system_errors.push_back(item.at("instrument_id").get<std::string>() + ":" + error.get<std::string>());
        for (const auto& provider : contract.at("provider_health").at("providers"))
            if (provider.value("fallback_status", std::string{}) == "UNAVAILABLE")
                system_errors.push_back(provider.at("provider_id").get<std::string>() + ":" +
                                         provider.value("fallback_reason", std::string{"fallback_unavailable"}));
        const json system_status_json = {
            {"schema_version", "1.0.0"}, {"run_id", contract.at("run_id")},
            {"scan_id", contract.at("scan_id")}, {"generated_at_utc", generated_at},
            {"run_status", run_status}, {"provider_status", contract.at("provider_health")},
            {"path_statuses", path_statuses}, {"generator_statuses", generator_statuses},
            {"telegram_send_status", "NOT_ATTEMPTED"},
            {"telegram_receive_test_status", "NOT_REQUESTED"},
            {"telegram_message_ids", json::array()}, {"telegram_last_update_id", 0},
            {"error_summary", system_errors}
        };
        const std::string system_raw = system_status_json.dump(2) + "\n";
        write_json(system_path, system_status_json);

        std::string history_raw = "timestamp_utc,run_id,scan_id,instrument_id,symbol,state,reason_code,data_quality,confidence_status,actionable,latest_candle_timestamp_ms\n";
        for (const auto& item : artifact.at("instruments")) {
            history_raw += csv_escape(generated_at) + "," +
                csv_escape(contract.at("run_id").get<std::string>()) + "," +
                csv_escape(contract.at("scan_id").get<std::string>()) + "," +
                csv_escape(item.at("instrument_id").get<std::string>()) + "," +
                csv_escape(item.at("symbol").get<std::string>()) + "," +
                csv_escape(item.at("state").get<std::string>()) + "," +
                csv_escape(item.at("reason_code").get<std::string>()) + "," +
                csv_escape(item.at("data_quality").get<std::string>()) + "," +
                csv_escape(item.at("confidence_status").get<std::string>()) + "," +
                (item.at("actionable").get<bool>() ? "true" : "false") + "," +
                std::to_string(item.at("latest_candle_timestamp_ms").get<std::int64_t>()) + "\n";
        }
        cfss::write_file_atomic(history_path, history_raw, true);

        const char* event_name = std::getenv("GITHUB_EVENT_NAME");
        const bool persist_signals = event_name && std::string{event_name} != "pull_request";
        const bool retain_full_evidence = false;
        const bool retain_non_l1_workflow = false;
        const int full_retention_days = 0;
        json artifact_manifest = {
            {"l1_market_data", artifact_entry(l1_path, l1_raw, retain_full_evidence, retain_full_evidence ? 1 : 0, false)},
            {"l2_status", artifact_entry(l2_path, l2_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"provider_health", artifact_entry(provider_path, provider_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"fear_greed", artifact_entry(fear_path, fear_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"crypto_universe", artifact_entry(crypto_universe_path, crypto_universe_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"signals", artifact_entry(signals_path, signals_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"history", artifact_entry(history_path, history_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"performance", artifact_entry(performance_path, performance_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"coverage", artifact_entry(coverage_path, coverage_raw, retain_non_l1_workflow, full_retention_days, persist_signals)},
            {"system_status", artifact_entry(system_path, system_raw, retain_non_l1_workflow, full_retention_days, persist_signals)}
        };
        const auto manifest = build_run_manifest(contract, artifact, artifact_manifest, symbols, years, l1_raw);
        write_json(manifest_path, manifest);

        std::cout << "CPP_L1_COLLECTED provider=okx symbols=" << contract.at("instruments").size()
                  << " crypto_universe=VERIFIED source=coinpaprika"
                  << " run_id=" << contract.at("run_id") << '\n';
        std::cout << "L2_ARTIFACT_CREATED instruments=" << artifact.at("instruments").size() << '\n';
        std::cout << "REQUIRED_ARTIFACTS_CREATED signals.json history.csv performance.json coverage.json system_status.json run-manifest.v1.json\n";
        curl_global_cleanup();
        return EXIT_SUCCESS;
    } catch (...) {
        curl_global_cleanup();
        throw;
    }
}
}

int main(int argc, char** argv) {
    try {
        if ((argc >= 6 && argc <= 9) && std::string{argv[1]} == "--collect-okx") {
            const std::optional<std::filesystem::path> universe_cache_path =
                argc >= 7 ? std::optional<std::filesystem::path>{argv[6]} : std::nullopt;
            const std::optional<std::filesystem::path> market_cache_path =
                argc >= 8 ? std::optional<std::filesystem::path>{argv[7]} : std::nullopt;
            const std::optional<std::filesystem::path> pending_symbols_path =
                argc == 9 ? std::optional<std::filesystem::path>{argv[8]} : std::nullopt;
            return run_collect(std::stoi(argv[2]), std::stoi(argv[3]), argv[4], argv[5],
                                universe_cache_path, market_cache_path, pending_symbols_path);
        }
        if (argc != 3) {
            std::cerr << "Usage: market_pipeline <l1-contract.json> <l2-artifact.json>\n"
                      << "   or: market_pipeline --collect-okx <non-BTC symbols:1..100 plus BTC> <years:1..2> <l1.json> <l2.json> [crypto-universe-cache.json] [market-data-cache.json] [pending-symbols.json]\n";
            return EXIT_FAILURE;
        }
        const std::filesystem::path input_path{argv[1]};
        const std::filesystem::path output_path{argv[2]};
        std::ifstream input(input_path, std::ios::binary);
        if (!input) throw std::runtime_error("l1_contract_open_failed");
        const std::string raw{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
        const auto contract = nlohmann::json::parse(raw);
        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        write_json(output_path, artifact);
        std::cout << "L2_ARTIFACT_CREATED run_id=" << contract.at("run_id")
                  << " instruments=" << artifact.at("instruments").size() << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "PIPELINE_REJECTED: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
