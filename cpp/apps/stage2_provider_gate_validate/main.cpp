#include "cfss/hash.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using json = nlohmann::json;

std::string read_text(const char* path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("stage2_provider_report_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}

std::int64_t now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "Usage: stage2_provider_gate_validate <l1-report.json> <l2-status.json>\n";
        return 2;
    }
    try {
        const auto report = json::parse(read_text(argv[1]));
        if (report.value("artifact_type", std::string{}) != "cfss_stage2_provider_gate_v1" ||
            report.value("universe_count", 0) != 27 ||
            report.value("expected_probes", 0) != 54 ||
            report.value("signal_generation_enabled", true) != false ||
            !report.contains("contract_metadata") || !report.at("contract_metadata").is_object() ||
            !report.contains("results") || !report.at("results").is_array() ||
            report.at("results").size() != 54U) {
            throw std::runtime_error("stage2_l1_contract_invalid");
        }

        const bool metadata_verified =
            report.value("contract_metadata_status", std::string{"UNAVAILABLE"}) == "VERIFIED";
        std::set<std::string> symbols;
        if (metadata_verified) {
            if (report.at("contract_metadata").size() != 27U)
                throw std::runtime_error("stage2_contract_metadata_coverage_invalid");
            for (auto it = report.at("contract_metadata").begin();
                 it != report.at("contract_metadata").end(); ++it) {
                const auto& meta = it.value();
                if (meta.value("symbol", std::string{}) != it.key() ||
                    meta.value("contract_type", std::string{}) != "PERPETUAL" ||
                    meta.value("status", std::string{}) != "TRADING" ||
                    meta.value("quote_asset", std::string{}) != "USDT" ||
                    meta.value("margin_asset", std::string{}) != "USDT") {
                    throw std::runtime_error("stage2_contract_identity_invalid:" + it.key());
                }
                symbols.insert(it.key());
            }
        } else if (!report.at("contract_metadata").empty()) {
            throw std::runtime_error("stage2_unverified_metadata_must_not_be_presented_as_verified");
        }

        std::set<std::string> seen;
        std::size_t passed = 0U;
        for (const auto& row : report.at("results")) {
            const auto symbol = row.value("symbol", std::string{});
            const auto timeframe = row.value("timeframe", std::string{});
            if (symbol.empty() || (timeframe != "1D" && timeframe != "4H"))
                throw std::runtime_error("stage2_probe_identity_invalid");
            symbols.insert(symbol);
            if (!seen.insert(symbol + ":" + timeframe).second)
                throw std::runtime_error("stage2_duplicate_probe");
            if (row.value("status", std::string{}) == "PASS") {
                const auto age = row.value("staleness_ms", std::int64_t{-1});
                if (age < 0 || age > 32LL * 60LL * 60LL * 1000LL ||
                    row.value("provider", std::string{}) != "binance_vision" ||
                    row.value("data_class", std::string{}) != "DELAYED_HISTORICAL_ARCHIVE") {
                    throw std::runtime_error("stage2_probe_freshness_or_provider_invalid");
                }
                ++passed;
            }
        }
        if (symbols.size() != 27U || seen.size() != 54U ||
            passed != static_cast<std::size_t>(report.value("passed_probes", -1)) ||
            report.value("failed_probes", -1) != 54 - static_cast<int>(passed)) {
            throw std::runtime_error("stage2_probe_coverage_mismatch");
        }
        if (metadata_verified && report.at("contract_metadata").size() != symbols.size())
            throw std::runtime_error("stage2_contract_symbol_coverage_mismatch");

        const bool all_pass = metadata_verified && passed == 54U &&
            report.value("overall_status", std::string{}) == "PASS";
        std::vector<std::string> snapshot_parts;
        for (const auto& row : report.at("results")) {
            snapshot_parts.push_back(
                row.value("symbol", std::string{}) + ":" +
                row.value("timeframe", std::string{}) + ":" +
                row.value("status", std::string{}) + ":" +
                row.value("archive_sha256", row.value("reason", std::string{})));
        }
        std::sort(snapshot_parts.begin(), snapshot_parts.end());
        std::string scan_material = report.at("results").at(0).value("archive_date_utc", std::string{}) +
            ":" + report.value("contract_metadata_sha256", std::string{});
        for (const auto& part : snapshot_parts) scan_material += "|" + part;
        const auto scan_id = "scan-" + cfss::sha256_hex(scan_material).substr(0, 48);

        json instruments = json::array();
        for (const auto& symbol : symbols) {
            instruments.push_back({
                {"instrument_id", symbol}, {"symbol", symbol},
                {"provider_id", "binance_vision"},
                {"state", all_pass ? "NO_QUALIFIED_SETUP" : "MARKET_DATA_DEGRADED"},
                {"reason_code", all_pass ? "STAGE2_PROVIDER_GATE_ONLY_NO_STRATEGY" :
                    (metadata_verified ? "STAGE2_ARCHIVE_PROBE_FAILED" : "STAGE2_CONTRACT_METADATA_UNAVAILABLE")},
                {"data_quality", all_pass ? "REAL_ARCHIVE_DELAYED" : "PARTIAL_OR_UNAVAILABLE"},
                {"confidence_status", "NOT_CALIBRATED"},
                {"actionable", false}
            });
        }

        json artifact = {
            {"artifact_type", "cfss_l2_status_v1"},
            {"source_schema_version", "1.0.0"},
            {"source_run_id", report.value("run_id", std::string{"unknown-run"})},
            {"source_scan_id", scan_id},
            {"created_at_epoch_ms", now_ms()},
            {"stage", "Stage 2 Provider Gate"},
            {"signal_generation_enabled", false},
            {"provider_gate_status", all_pass ? "PASS" : "BLOCKED"},
            {"metadata_status", metadata_verified ? "VERIFIED" : "UNAVAILABLE"},
            {"passed_probes", passed}, {"expected_probes", 54},
            {"instruments", instruments}
        };
        cfss::add_artifact_hash(artifact);
        std::ofstream output(argv[2], std::ios::binary | std::ios::trunc);
        if (!output) throw std::runtime_error("stage2_l2_output_open_failed");
        output << artifact.dump(2) << '\n';
        std::cout << "STAGE2_CPP_VALIDATION=PASS\n"
                  << "CONTRACT_METADATA=" << (metadata_verified ? "VERIFIED" : "UNAVAILABLE") << '\n'
                  << "PROBES=" << passed << "/54\n"
                  << "PROVIDER_GATE=" << (all_pass ? "PASS" : "BLOCKED") << '\n'
                  << "SIGNAL_GENERATION=DISABLED\n";
        return all_pass ? 0 : 1;
    } catch (const std::exception& e) {
        std::cerr << "STAGE2_CPP_VALIDATION=REJECT:" << e.what() << '\n';
        return 2;
    }
}
