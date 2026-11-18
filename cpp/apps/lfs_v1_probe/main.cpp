#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: lfs_v1_probe <l1-json> <output-json>\n";
        return 2;
    }
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("l1_input_open_failed");
        const json l1 = json::parse(input);
        if (!l1.is_object() || !l1.contains("instruments") || !l1.at("instruments").is_array()) {
            throw std::runtime_error("l1_instruments_missing");
        }

        json rows = json::array();
        for (const auto& instrument : l1.at("instruments")) {
            const std::string symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            const bool orderbook = instrument.contains("orderbook") && instrument.at("orderbook").is_array();
            const bool long_short = instrument.contains("long_short") && instrument.at("long_short").is_array();
            const bool funding = instrument.contains("funding") && instrument.at("funding").is_array() &&
                                 !instrument.at("funding").empty();
            const bool candles = instrument.contains("candles") && instrument.at("candles").is_array() &&
                                 !instrument.at("candles").empty();
            const bool open_interest = instrument.contains("open_interest") &&
                                       instrument.at("open_interest").is_array() &&
                                       !instrument.at("open_interest").empty();

            json components = json::array({
                {{"id", "LFS1_BOOK_THINNESS"}, {"score", nullptr},
                 {"data_class", "UNAVAILABLE"}, {"raw_input", orderbook ? "PRESENT" : "UNAVAILABLE"},
                 {"reason", "No normalized, versioned order-book depth score in L1"}},
                {{"id", "LFS2_FUNDING_EXTREME"}, {"score", nullptr},
                 {"data_class", "UNAVAILABLE"}, {"raw_input", funding ? "PRESENT" : "UNAVAILABLE"},
                 {"reason", "Funding raw series exists, but canonical raw-to-score transform is not specified"}},
                {{"id", "LFS3_LONG_SHORT_POSITIONING"}, {"score", nullptr},
                 {"data_class", "UNAVAILABLE"}, {"raw_input", long_short ? "PRESENT" : "UNAVAILABLE"},
                 {"reason", "No long/short positioning series in L1"}},
                {{"id", "LFS4_VOLATILITY_COMPRESSION"}, {"score", nullptr},
                 {"data_class", "UNAVAILABLE"}, {"raw_input", candles ? "PRESENT" : "UNAVAILABLE"},
                 {"reason", "OHLCV exists, but canonical volatility-compression score transform is not specified"}},
                {{"id", "LFS5_OPEN_INTEREST_CHANGE"}, {"score", nullptr},
                 {"data_class", "UNAVAILABLE"}, {"raw_input", open_interest ? "PRESENT" : "UNAVAILABLE"},
                 {"reason", "Open-interest raw series exists, but canonical change-score transform is not specified"}}
            });

            rows.push_back({
                {"symbol", symbol},
                {"status", "UNAVAILABLE"},
                {"score", nullptr},
                {"data_class", "UNAVAILABLE"},
                {"component_coverage", {{"available_scores", 0}, {"required_scores", 5}}},
                {"components", components}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_lfs_v1_probe"},
            {"version", "LFS_V1_FORMULA"},
            {"source_run_id", l1.value("run_id", std::string{"UNKNOWN"})},
            {"source_scan_id", l1.value("scan_id", std::string{"UNKNOWN"})},
            {"status", "UNAVAILABLE"},
            {"reason", "V1 requires five defined point-in-time component scores; missing scores are never imputed"},
            {"instruments", rows}
        };
        std::ofstream out(argv[2], std::ios::trunc);
        if (!out) throw std::runtime_error("lfs_output_open_failed");
        out << output.dump(2) << '\n';
        if (!out.good()) throw std::runtime_error("lfs_output_write_failed");
        std::cout << "LFS_V1_STATUS=UNAVAILABLE\n";
        std::cout << "LFS_V1_INSTRUMENTS=" << rows.size() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "LFS_V1_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
