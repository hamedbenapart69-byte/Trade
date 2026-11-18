#include "cfss/nss.hpp"

#include <algorithm>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {
std::int64_t latest_timestamp(const json& rows) {
    if (!rows.is_array()) return 0;
    std::int64_t latest = 0;
    for (const auto& row : rows) {
        if (!row.is_object() || !row.contains("timestamp_ms") ||
            !row.at("timestamp_ms").is_number_integer()) continue;
        latest = std::max(latest, row.at("timestamp_ms").get<std::int64_t>());
    }
    return latest;
}

json inspect_component(const std::string& id, bool raw_available,
                       std::int64_t timestamp, const std::string& reason) {
    return {
        {"id", id},
        {"score", nullptr},
        {"data_class", raw_available ? "REAL" : "UNAVAILABLE"},
        {"available_at_ms", timestamp},
        {"definition_id", ""},
        {"status", "UNAVAILABLE"},
        {"reason", reason}
    };
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: nss_v1_probe <l1-market-data.json> <nss-v1.json>\n";
        return 2;
    }
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("l1_input_open_failed");
        const json l1 = json::parse(input);
        if (!l1.is_object() || !l1.contains("instruments") || !l1.at("instruments").is_array())
            throw std::runtime_error("l1_instruments_missing");

        json instruments = json::array();
        for (const auto& instrument : l1.at("instruments")) {
            const auto symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            const json candles = instrument.value("candles", json::array());
            const json funding = instrument.value("funding", json::array());
            const json oi = instrument.value("open_interest", json::array());
            const bool basis_available = instrument.contains("basis") &&
                                         instrument.at("basis").is_array() &&
                                         !instrument.at("basis").empty();

            json components = json::array();
            components.push_back(inspect_component(
                "NSS1_OPEN_INTEREST_GROWTH", !oi.empty(), latest_timestamp(oi),
                oi.empty() ? "REAL_OI_INPUT_MISSING" : "RAW_OI_PRESENT_BUT_V1_SCORE_TRANSFORM_UNSPECIFIED"));
            components.push_back(inspect_component(
                "NSS2_HEALTHY_FUNDING", !funding.empty(), latest_timestamp(funding),
                funding.empty() ? "REAL_FUNDING_INPUT_MISSING" : "RAW_FUNDING_PRESENT_BUT_DIRECTIONAL_HEALTH_TRANSFORM_UNSPECIFIED"));
            components.push_back(inspect_component(
                "NSS3_BASIS_EXPANSION", basis_available,
                basis_available ? latest_timestamp(instrument.at("basis")) : 0,
                basis_available ? "BASIS_SCORE_TRANSFORM_UNSPECIFIED" : "REAL_SPOT_PERPETUAL_BASIS_SERIES_MISSING"));
            components.push_back(inspect_component(
                "NSS4_VOLUME_EXPANSION", !candles.empty(), latest_timestamp(candles),
                candles.empty() ? "REAL_OHLCV_INPUT_MISSING" : "RAW_VOLUME_PRESENT_BUT_EXPANSION_TRANSFORM_UNSPECIFIED"));
            components.push_back(inspect_component(
                "NSS5_PRE_BREAKOUT_COMPRESSION", !candles.empty(), latest_timestamp(candles),
                candles.empty() ? "REAL_OHLCV_INPUT_MISSING" : "RAW_OHLCV_PRESENT_BUT_COMPRESSION_TRANSFORM_UNSPECIFIED"));

            instruments.push_back({
                {"symbol", symbol},
                {"status", "UNAVAILABLE"},
                {"score", nullptr},
                {"data_class", "UNAVAILABLE"},
                {"component_coverage", {
                    {"available_scores", 0},
                    {"required_scores", 5},
                    {"raw_oi_present", !oi.empty()},
                    {"raw_funding_present", !funding.empty()},
                    {"raw_ohlcv_present", !candles.empty()},
                    {"real_basis_present", basis_available}
                }},
                {"components", components}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_nss_v1_formula"},
            {"version", "NSS_V1_FORMULA"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"status", "UNAVAILABLE"},
            {"reason", "V18.2 names NSS components and weights but does not define raw-to-score transforms; real basis is also absent from the current L1 contract. No score was fabricated."},
            {"instruments", instruments}
        };

        std::ofstream out(argv[2], std::ios::trunc);
        if (!out) throw std::runtime_error("nss_output_open_failed");
        out << output.dump(2) << '\n';
        if (!out.good()) throw std::runtime_error("nss_output_write_failed");
        std::cout << "NSS_V1_STATUS=UNAVAILABLE\n";
        std::cout << "NSS_V1_SYMBOLS=" << instruments.size() << '\n';
        std::cout << "NSS_V1_DIAGNOSIS=D1+D2\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "NSS_V1_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
