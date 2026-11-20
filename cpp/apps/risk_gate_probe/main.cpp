#include "cfss/risk_gate_pipeline.hpp"
#include "cfss/atomic_file.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
json read_json(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed");
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid");
    return value;
}
std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}
void write_json(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}
}

int main(int argc, char** argv) {
    if (argc != 5 && argc != 6) {
        std::cerr << "usage: risk_gate_probe <l1.json> <liquidity.json> <meta-cognition.json> <output.json> [shadow-risk-snapshot.json]\n";
        return 2;
    }
    try {
        const std::filesystem::path l1_path{argv[1]};
        const std::filesystem::path liquidity_path{argv[2]};
        const std::filesystem::path meta_path{argv[3]};
        const std::filesystem::path output_path{argv[4]};
        const json snapshot = argc == 6 ? read_json(argv[5]) : json::object();
        const auto l1 = read_json(l1_path);
        const auto liquidity = read_json(liquidity_path);
        const auto meta = read_json(meta_path);
        const auto report = cfss::risk::build_report(
            l1, liquidity, meta, read_raw(l1_path), read_raw(liquidity_path), snapshot);
        write_json(output_path, report);
        const auto& summary = report.at("summary");
        std::cout << "STAGE7_RISK_GATE_STATUS=GENERATED"
                  << " CANDIDATES=" << summary.at("candidate_count")
                  << " BLOCKED=" << summary.at("blocked_count")
                  << " MANUAL_REVIEW=" << summary.at("manual_review_count")
                  << " ACTIONABLE=0"
                  << " RISK_SNAPSHOT=" << report.at("risk_snapshot_status") << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "STAGE7_RISK_GATE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
