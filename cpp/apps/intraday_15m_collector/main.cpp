#include "cfss/okx_provider.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"

#include <curl/curl.h>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <iostream>
#include <stdexcept>
#include <string>

using json = nlohmann::json;

namespace {
json read_json(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("l1_input_open_failed");
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("l1_input_root_invalid");
    return value;
}
std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("l1_hash_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}
void write_json(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: intraday_15m_collector <l1-1h.json> <l1-15m-out.json>\n";
        return 2;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    try {
        const std::filesystem::path input_path{argv[1]};
        const auto l1 = read_json(input_path);
        if (l1.value("schema_version", std::string{}) != "1.0.0" ||
            !l1.contains("instruments") || !l1.at("instruments").is_array() ||
            !l1.contains("window") || l1.at("window").value("timeframe", std::string{}) != "1h")
            throw std::runtime_error("l1_1h_contract_invalid");
        const auto decision_time = l1.at("window").value("end_ms", std::int64_t{0});
        if (decision_time <= 0) throw std::runtime_error("l1_decision_time_invalid");
        const auto source_hash = cfss::sha256_hex(read_raw(input_path));
        json instruments = json::array();
        std::size_t available = 0U;
        for (const auto& source : l1.at("instruments")) {
            cfss::okx::Instrument instrument{};
            instrument.id = source.value("instrument_id", std::string{});
            instrument.base = source.value("base", std::string{});
            instrument.quote = source.value("quote", std::string{"USDT"});
            if (instrument.id.empty() || instrument.base.empty())
                throw std::runtime_error("l1_instrument_mapping_invalid");
            const auto candles = cfss::okx::fetch_recent_candles(
                instrument, "15m", 900'000LL, decision_time, 100);
            if (!candles.empty()) ++available;
            instruments.push_back({
                {"instrument_id", instrument.id},
                {"unified_symbol", source.value("unified_symbol", std::string{})},
                {"timeframe", "15m"},
                {"data_quality", candles.empty() ? "UNAVAILABLE" : "REAL"},
                {"candles", candles}
            });
        }
        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_intraday_15m_market_data_v1"},
            {"source_run_id", l1.value("run_id", std::string{})},
            {"source_scan_id", l1.value("scan_id", std::string{})},
            {"source_l1_sha256", source_hash},
            {"decision_time_ms", decision_time},
            {"window", {{"timeframe", "15m"}, {"end_ms", decision_time}}},
            {"provider_id", "okx"},
            {"candles_sha256", cfss::sha256_hex(instruments.dump())},
            {"instruments", instruments},
            {"coverage", {{"selected_count", instruments.size()},
                          {"available_count", available},
                          {"unavailable_count", instruments.size() - available}}}
        };
        write_json(argv[2], output);
        std::cout << "INTRADAY_15M_STATUS=" << (available == instruments.size() ? "PASS" : "PARTIAL")
                  << " AVAILABLE=" << available << " SELECTED=" << instruments.size() << '\n';
        curl_global_cleanup();
        return available > 0U ? 0 : 1;
    } catch (const std::exception& error) {
        curl_global_cleanup();
        std::cerr << "INTRADAY_15M_ERROR=" << error.what() << '\n';
        return 1;
    }
}
