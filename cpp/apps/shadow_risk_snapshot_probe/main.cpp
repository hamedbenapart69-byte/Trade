#include "cfss/shadow_risk_snapshot.hpp"
#include "cfss/atomic_file.hpp"

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
    if (argc != 9) {
        std::cerr << "usage: shadow_risk_snapshot_probe <basis.json> <ledger.json> <registry.json> <run_id> <scan_id> <decision_time_ms> <correlated_exposures> <output.json>\n";
        return 2;
    }
    try {
        const auto basis = read_json_or_empty(argv[1]);
        const auto ledger = read_json_required(argv[2]);
        const auto registry = read_json_required(argv[3]);
        const auto decision_time = std::stoll(argv[6]);
        const auto correlated = std::stoi(argv[7]);
        const auto snapshot = cfss::shadow_risk::build_snapshot(
            basis, ledger, registry, argv[4], argv[5], decision_time, correlated);
        cfss::write_file_atomic(argv[8], snapshot.dump(2) + "\n", true);
        std::cout << "SHADOW_RISK_SNAPSHOT_STATUS=" << snapshot.value("status", std::string{"UNAVAILABLE"})
                  << " REASON=" << snapshot.value("reason", std::string{"NONE"})
                  << " DATA_CLASS=" << snapshot.value("data_class", std::string{"UNAVAILABLE"}) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "SHADOW_RISK_SNAPSHOT_ERROR=" << error.what() << '\n';
        return 1;
    }
}
