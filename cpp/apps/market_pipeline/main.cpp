#include "cfss/l1_contract.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/okx_provider.hpp"

#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

namespace {
std::int64_t now_epoch_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
void write_json(const std::filesystem::path& path, const nlohmann::json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}
nlohmann::json build_run_manifest(const nlohmann::json& contract, const nlohmann::json& artifact,
                                   const std::filesystem::path& l1_path,
                                   const std::filesystem::path& l2_path,
                                   int symbols, int years,
                                   const std::string& l1_raw, const std::string& l2_raw) {
    const nlohmann::json config = {
        {"symbol_target", symbols}, {"years", years}, {"timeframe", "1h"},
        {"liquidity_threshold_usd", 10000000.0}, {"ohlcv_closed_bars_only", true}
    };
    const auto evidence_dir = l1_path.parent_path().empty() ? std::filesystem::path{"."} : l1_path.parent_path();
    const std::string provider_raw = contract.at("provider_health").dump(2) + "\n";
    const std::string fear_raw = contract.at("fear_greed").dump(2) + "\n";
    bool all_real = true;
    nlohmann::json errors = nlohmann::json::array();
    for (const auto& item : artifact.at("instruments")) {
        if (item.value("data_quality", std::string{}) != "REAL") all_real = false;
    }
    for (const auto& item : contract.at("instruments")) {
        for (const auto& error : item.at("errors")) errors.push_back(item.at("instrument_id").get<std::string>() + ":" + error.get<std::string>());
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
        {"artifact_manifest", {
            {"l1_market_data", {{"path", l1_path.generic_string()}, {"sha256", cfss::sha256_hex(l1_raw)}, {"bytes", l1_raw.size()}}},
            {"l2_status", {{"path", l2_path.generic_string()}, {"sha256", cfss::sha256_hex(l2_raw)}, {"bytes", l2_raw.size()}}},
            {"provider_health", {{"path", (evidence_dir / "provider-health.v1.json").generic_string()},
                                 {"sha256", cfss::sha256_hex(provider_raw)}, {"bytes", provider_raw.size()}}},
            {"fear_greed", {{"path", (evidence_dir / "fear-greed.v1.json").generic_string()},
                            {"sha256", cfss::sha256_hex(fear_raw)}, {"bytes", fear_raw.size()}}}
        }},
        {"telegram_send_status", "NOT_ATTEMPTED"},
        {"telegram_receive_test_status", "NOT_REQUESTED"},
        {"telegram_message_ids", nlohmann::json::array()},
        {"telegram_last_update_id", 0}
    };
}

int run_collect(int symbols, int years, const std::filesystem::path& l1_path,
                const std::filesystem::path& l2_path) {
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK)
        throw std::runtime_error("curl_global_init_failed");
    try {
        const auto contract = cfss::okx::collect(symbols, years);
        const std::string l1_raw = contract.dump(2) + "\n";
        cfss::write_file_atomic(l1_path, l1_raw, true);
        const auto evidence_dir = l1_path.parent_path().empty() ? std::filesystem::path{"."} : l1_path.parent_path();
        write_json(evidence_dir / "provider-health.v1.json", contract.at("provider_health"));
        write_json(evidence_dir / "fear-greed.v1.json", contract.at("fear_greed"));
        auto artifact = cfss::build_l2_artifact(contract, now_epoch_ms());
        cfss::add_artifact_hash(artifact);
        const std::string l2_raw = artifact.dump(2) + "\n";
        cfss::write_file_atomic(l2_path, l2_raw, true);
        const auto manifest = build_run_manifest(contract, artifact, l1_path, l2_path,
                                                 symbols, years, l1_raw, l2_raw);
        write_json(evidence_dir / "run-manifest.v1.json", manifest);
        std::cout << "CPP_L1_COLLECTED provider=okx symbols=" << contract.at("instruments").size()
                  << " run_id=" << contract.at("run_id") << '\n';
        std::cout << "L2_ARTIFACT_CREATED instruments=" << artifact.at("instruments").size() << '\n';
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
        if (argc == 6 && std::string{argv[1]} == "--collect-okx") {
            return run_collect(std::stoi(argv[2]), std::stoi(argv[3]), argv[4], argv[5]);
        }
        if (argc != 3) {
            std::cerr << "Usage: market_pipeline <l1-contract.json> <l2-artifact.json>\n"
                      << "   or: market_pipeline --collect-okx <symbols:1..100> <years:1..2> <l1.json> <l2.json>\n";
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
