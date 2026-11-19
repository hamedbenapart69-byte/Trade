#include "cfss/liquidity_phase.hpp"
#include "cfss/hash.hpp"
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
    if (!input) throw std::runtime_error("l1_input_open_failed");
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("l1_root_invalid");
    return value;
}

std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("l1_hash_input_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: liquidity_phase_probe <l1-market-data.json> <liquidity-phase.json>\n";
        return 2;
    }
    try {
        const auto l1_path = std::filesystem::path{argv[1]};
        const auto l1 = read_json(l1_path);
        if (!l1.contains("instruments") || !l1.at("instruments").is_array() ||
            !l1.contains("window") || !l1.at("window").contains("end_ms"))
            throw std::runtime_error("l1_contract_incomplete");
        const auto decision_time = l1.at("window").at("end_ms").get<std::int64_t>();
        json instruments = json::array();
        bool all_available = true;
        for (const auto& instrument : l1.at("instruments")) {
            const auto symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            const auto result = cfss::liquidity::calculate(
                symbol, instrument.value("candles", json::array()), decision_time);
            const auto item = cfss::liquidity::to_json(result);
            if (item.value("status", std::string{}) != "AVAILABLE") all_available = false;
            std::cout << symbol
                      << " LIQUIDITY_STATUS=" << item.value("status", std::string{"UNAVAILABLE"})
                      << " PHASE=" << item.value("phase", std::string{"UNAVAILABLE"})
                      << " ZONES=" << item.at("zones").size() << '\n';
            instruments.push_back(item);
        }
        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_liquidity_phase_v1"},
            {"algorithm_version", "LIQUIDITY_PHASE_V1"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"decision_time_ms", decision_time},
            {"l1_sha256", cfss::sha256_hex(read_raw(l1_path))},
            {"status", all_available ? "AVAILABLE" : "PARTIAL_OR_UNAVAILABLE"},
            {"method_class", "RULE_BASED_PROXY"},
            {"actionable", false},
            {"instruments", instruments}
        };
        cfss::write_file_atomic(argv[2], output.dump(2) + "\n", true);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "LIQUIDITY_PHASE_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
