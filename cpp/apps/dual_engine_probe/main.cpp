#include "cfss/dual_engines.hpp"
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
    if (!input) throw std::runtime_error("input_open_failed:" + path.string());
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid:" + path.string());
    return value;
}

std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_hash_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}

const json* find_symbol(const json& artifact, const std::string& symbol) {
    if (!artifact.contains("instruments") || !artifact.at("instruments").is_array()) return nullptr;
    for (const auto& item : artifact.at("instruments"))
        if (item.value("symbol", std::string{}) == symbol) return &item;
    return nullptr;
}

void write_output(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path.string(), value.dump(2) + "\n", true);
}
}

int main(int argc, char** argv) {
    if (argc != 7) {
        std::cerr << "usage: dual_engine_probe <l1.json> <lfs-v2.json> <nss-v2.json> <liquidity.json> <lrt.json> <nmt.json>\n";
        return 2;
    }
    try {
        const std::filesystem::path l1_path{argv[1]};
        const auto l1 = read_json(l1_path);
        const auto lfs = read_json(argv[2]);
        const auto nss = read_json(argv[3]);
        const auto liquidity = read_json(argv[4]);

        if (lfs.value("artifact_type", std::string{}) != "cfss_lfs_v2_proxy" ||
            nss.value("artifact_type", std::string{}) != "cfss_nss_v2_proxy" ||
            liquidity.value("artifact_type", std::string{}) != "cfss_liquidity_phase_v1")
            throw std::runtime_error("input_artifact_type_mismatch");
        if (!l1.contains("window") || !l1.at("window").contains("end_ms") ||
            !l1.contains("instruments") || !l1.at("instruments").is_array())
            throw std::runtime_error("l1_contract_invalid");

        const auto decision_time = l1.at("window").at("end_ms").get<std::int64_t>();
        const auto run_id = l1.value("run_id", std::string{});
        const auto scan_id = l1.value("scan_id", std::string{});
        const auto l1_hash = cfss::sha256_hex(read_raw(l1_path));
        for (const auto* artifact : {&lfs, &nss, &liquidity}) {
            if (artifact->value("source_run_id", std::string{}) != run_id ||
                artifact->value("source_scan_id", std::string{}) != scan_id ||
                artifact->value("decision_time_ms", std::int64_t{0}) != decision_time ||
                artifact->value("l1_sha256", std::string{}) != l1_hash)
                throw std::runtime_error("CROSS_ARTIFACT_PROVENANCE_OR_DECISION_TIME_MISMATCH");
        }

        json lrt_instruments = json::array();
        json nmt_instruments = json::array();
        json combined = json::array();
        bool golden_veto_seen = false;
        for (const auto& instrument : l1.at("instruments")) {
            const auto symbol = instrument.value("unified_symbol", std::string{"UNKNOWN"});
            const auto* lfs_item = find_symbol(lfs, symbol);
            const auto* nss_item = find_symbol(nss, symbol);
            const auto* liquidity_item = find_symbol(liquidity, symbol);
            if (!lfs_item || !nss_item || !liquidity_item)
                throw std::runtime_error("CROSS_ARTIFACT_SYMBOL_COVERAGE_MISMATCH:" + symbol);

            const auto result = cfss::engines::evaluate(
                symbol, instrument, *lfs_item, *nss_item, *liquidity_item, decision_time);
            const auto item = cfss::engines::to_json(result);
            golden_veto_seen = golden_veto_seen || result.golden_rule_veto;
            combined.push_back(item);
            lrt_instruments.push_back({
                {"symbol", symbol},
                {"decision_time_ms", decision_time},
                {"candidate", item.at("lrt")},
                {"golden_rule", item.at("golden_rule")},
                {"actionable", false}
            });
            nmt_instruments.push_back({
                {"symbol", symbol},
                {"decision_time_ms", decision_time},
                {"candidate", item.at("nmt")},
                {"golden_rule", item.at("golden_rule")},
                {"actionable", false}
            });
            std::cout << symbol
                      << " LRT=" << item.at("lrt").value("status", std::string{"UNKNOWN"})
                      << " NMT=" << item.at("nmt").value("status", std::string{"UNKNOWN"})
                      << " GOLDEN_RULE_VETO=" << result.golden_rule_veto << '\n';
        }

        const auto universe = l1.value("universe", json::object());
        const auto universe_target = universe.value("target_count", 0U);
        const auto universe_selected = universe.value("selected_count", 0U);
        const auto universe_status = universe_selected >= universe_target + 1U
            ? "PASS" : "PARTIAL";
        const json universe_summary = {
            {"target_non_btc_count", universe_target},
            {"selected_total_count", universe_selected},
            {"eligible_count", universe.value("eligible_count", 0U)},
            {"status", universe_status}
        };
        const json common = {
            {"schema_version", "1.0.0"},
            {"universe", universe_summary},
            {"source_run_id", run_id},
            {"source_scan_id", scan_id},
            {"decision_time_ms", decision_time},
            {"l1_sha256", l1_hash},
            {"data_class", "PROXY"},
            {"actionable", false}
        };
        json lrt_output = common;
        lrt_output["artifact_type"] = "cfss_lrt_candidates_v1";
        lrt_output["version"] = "LRT_V1";
        lrt_output["path"] = "PLAN_A_LRT";
        lrt_output["instruments"] = lrt_instruments;

        json nmt_output = common;
        nmt_output["artifact_type"] = "cfss_nmt_candidates_v1";
        nmt_output["version"] = "NMT_V1";
        nmt_output["path"] = "PLAN_A_NMT";
        nmt_output["instruments"] = nmt_instruments;

        json combined_output = common;
        combined_output["artifact_type"] = "cfss_dual_engine_report_v1";
        combined_output["version"] = "DUAL_ENGINE_V1";
        combined_output["path_separation"] = true;
        combined_output["golden_rule_veto_seen"] = golden_veto_seen;
        combined_output["instruments"] = combined;

        write_output(argv[5], lrt_output);
        write_output(argv[6], nmt_output);
        std::filesystem::path combined_path{argv[5]};
        combined_path.replace_filename("dual-engine-report.v1.json");
        write_output(combined_path, combined_output);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "DUAL_ENGINE_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
