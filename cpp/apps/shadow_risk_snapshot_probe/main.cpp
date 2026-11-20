#include "cfss/risk_gate_pipeline.hpp"
#include "cfss/shadow_risk_snapshot.hpp"
#include "cfss/atomic_file.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
json read_json_or_empty(const std::filesystem::path& path) {
    if (!std::filesystem::exists(path)) return json::object();
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed");
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid");
    return value;
}
json read_json_required(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("required_input_open_failed");
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid");
    return value;
}
}

int main(int argc, char** argv) {
    if (argc != 7) {
        std::cerr << "usage: shadow_risk_snapshot_probe <basis.json> <ledger.json> <registry.json> <l1.json> <meta-cognition.json> <output.json>\n";
        return 2;
    }
    try {
        const auto basis = read_json_or_empty(argv[1]);
        const auto ledger = read_json_required(argv[2]);
        const auto registry = read_json_required(argv[3]);
        const auto l1 = read_json_required(argv[4]);
        const auto meta = read_json_required(argv[5]);
        const auto decision_time = meta.value("decision_time_ms", std::int64_t{0});
        const auto run_id = meta.value("source_run_id", std::string{});
        const auto scan_id = meta.value("source_scan_id", std::string{});

        const auto correlations = cfss::risk::candidate_correlations(l1, meta, decision_time);
        int correlated_exposures = correlations.valid ? 0 : -1;
        if (correlations.valid) {
            for (const auto& [candidate, count] : correlations.peer_counts) {
                (void)candidate;
                correlated_exposures = std::max(correlated_exposures, count);
            }
        }
        const auto snapshot = cfss::shadow_risk::build_snapshot(
            basis, ledger, registry, run_id, scan_id, decision_time, correlated_exposures);
        cfss::write_file_atomic(argv[6], snapshot.dump(2) + "\n", true);
        std::cout << "SHADOW_RISK_SNAPSHOT_STATUS=" << snapshot.value("status", std::string{"UNAVAILABLE"})
                  << " REASON=" << snapshot.value("reason", std::string{"NONE"})
                  << " DATA_CLASS=" << snapshot.value("data_class", std::string{"UNAVAILABLE"}) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "SHADOW_RISK_SNAPSHOT_ERROR=" << error.what() << '\n';
        return 1;
    }
}
