#include "cfss/nss_v2.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {
json read_json(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed:" + path.string());
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid:" + path.string());
    return value;
}

std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed:" + path.string());
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}

json component_json(const cfss::nss::V2Component& component) {
    return {
        {"id", component.id},
        {"score", component.score ? json(*component.score) : json(nullptr)},
        {"data_class", component.data_class},
        {"available_at_ms", component.available_at_ms},
        {"definition_id", component.definition_id},
        {"reason", component.reason}
    };
}

json direction_json(const cfss::nss::V2DirectionResult& result) {
    json components = json::array();
    for (const auto& component : result.components) components.push_back(component_json(component));
    return {
        {"direction", result.direction},
        {"status", result.status},
        {"score", result.score ? json(*result.score) : json(nullptr)},
        {"data_class", result.data_class},
        {"component_coverage", {
            {"available_scores", 5U - result.missing_count},
            {"required_scores", 5}
        }},
        {"missing_count", result.missing_count},
        {"components", components},
        {"actionable", false},
        {"confidence_status", "NOT_CALIBRATED"}
    };
}
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: nss_v2_probe <l1-market-data.json> <nss-basis.json> <nss-v2.json>\n";
        return 2;
    }
    try {
        const auto l1_path = std::filesystem::path{argv[1]};
        const auto basis_path = std::filesystem::path{argv[2]};
        const auto l1 = read_json(l1_path);
        const auto basis = read_json(basis_path);
        if (basis.value("artifact_type", std::string{}) != "cfss_nss_basis_v1")
            throw std::runtime_error("basis_artifact_type_invalid");
        if (!l1.contains("instruments") || !l1.at("instruments").is_array() ||
            !basis.contains("instruments") || !basis.at("instruments").is_array() ||
            !l1.contains("window") || !l1.at("window").contains("end_ms"))
            throw std::runtime_error("input_contract_incomplete");
        if (l1.value("run_id", std::string{}) != basis.value("source_run_id", std::string{}))
            throw std::runtime_error("basis_l1_run_id_mismatch");
        const auto decision_time = l1.at("window").at("end_ms").get<std::int64_t>();

        json output_instruments = json::array();
        bool all_calculated = true;
        for (const auto& instrument : l1.at("instruments")) {
            const auto symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            const json* basis_instrument = nullptr;
            for (const auto& item : basis.at("instruments")) {
                if (item.value("symbol", std::string{}) == symbol) {
                    basis_instrument = &item;
                    break;
                }
            }
            const json empty_basis = json::object();
            const auto results = cfss::nss::calculate_v2(
                instrument, basis_instrument ? *basis_instrument : empty_basis, decision_time);
            const auto long_result = direction_json(results[0]);
            const auto short_result = direction_json(results[1]);
            const bool calculated = long_result.at("status") == "CALCULATED" &&
                                    short_result.at("status") == "CALCULATED";
            if (!calculated) all_calculated = false;
            output_instruments.push_back({
                {"symbol", symbol},
                {"status", calculated ? "CALCULATED" : "UNAVAILABLE"},
                {"version", "NSS_V2_PROXY"},
                {"data_class", calculated ? "PROXY" : "UNAVAILABLE"},
                {"nss_long", long_result},
                {"nss_short", short_result},
                {"actionable", false},
                {"confidence_status", "NOT_CALIBRATED"}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_nss_v2_proxy"},
            {"version", "NSS_V2_PROXY"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"decision_time_ms", decision_time},
            {"l1_sha256", cfss::sha256_hex(read_raw(l1_path))},
            {"basis_sha256", cfss::sha256_hex(read_raw(basis_path))},
            {"status", all_calculated ? "CALCULATED" : "PARTIAL_OR_UNAVAILABLE"},
            {"reason", "V2 uses explicit directional z-score/sigmoid proxy transforms; all outputs remain research-only and NOT_CALIBRATED."},
            {"instruments", output_instruments}
        };
        cfss::write_file_atomic(argv[3], output.dump(2) + "\n", true);
        for (const auto& item : output_instruments) {
            std::cout << item.at("symbol").get<std::string>()
                      << " NSS_V2_STATUS=" << item.at("status").get<std::string>()
                      << " LONG=" << item.at("nss_long").value("score", json(nullptr))
                      << " SHORT=" << item.at("nss_short").value("score", json(nullptr))
                      << " DATA_CLASS=" << item.at("data_class").get<std::string>() << '\n';
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "NSS_V2_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
