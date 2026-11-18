#include "cfss/meta_calibration.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

using json = nlohmann::json;

namespace {
json read_json(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_open_failed:" + path.string());
    auto value = json::parse(input);
    if (!value.is_object()) throw std::runtime_error("input_root_invalid");
    return value;
}

std::string read_raw(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("input_hash_open_failed");
    return {std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
}

void write_json(const std::filesystem::path& path, const json& value) {
    cfss::write_file_atomic(path, value.dump(2) + "\n", true);
}

std::vector<cfss::meta::Outcome> parse_outcomes(const json& ledger) {
    std::vector<cfss::meta::Outcome> out;
    if (!ledger.contains("outcomes") || !ledger.at("outcomes").is_array())
        throw std::runtime_error("outcome_ledger_array_missing");
    for (const auto& row : ledger.at("outcomes")) {
        if (!row.is_object()) throw std::runtime_error("outcome_row_not_object");
        cfss::meta::Outcome item{};
        item.signal_id = row.value("signal_id", std::string{});
        item.path = row.value("path", std::string{});
        item.regime = row.value("regime", std::string{});
        item.closed_at_ms = row.value("closed_at_ms", std::int64_t{0});
        item.raw_score = row.value("raw_score", std::numeric_limits<double>::quiet_NaN());
        item.win = row.value("win", false);
        item.win_r = row.value("win_r", 0.0);
        item.loss_r = row.value("loss_r", 0.0);
        item.fee_r = row.value("fee_r", 0.0);
        item.slippage_r = row.value("slippage_r", 0.0);
        item.funding_r = row.value("funding_r", 0.0);
        out.push_back(item);
    }
    return out;
}

json optional_number(const std::optional<double>& value) {
    return value ? json(*value) : json(nullptr);
}

json calibration_json(const cfss::meta::CalibrationReport& report) {
    return {
        {"status", report.status}, {"reason", report.reason}, {"method", report.method},
        {"sample_count", report.sample_count}, {"train_count", report.train_count},
        {"validation_count", report.validation_count}, {"oos_count", report.oos_count},
        {"brier_raw_oos", optional_number(report.brier_raw_oos)},
        {"brier_calibrated_oos", optional_number(report.brier_calibrated_oos)},
        {"brier_ci_low", optional_number(report.brier_ci_low)},
        {"brier_ci_high", optional_number(report.brier_ci_high)},
        {"log_loss_oos", optional_number(report.log_loss_oos)},
        {"win_rate_oos", optional_number(report.win_rate_oos)},
        {"win_rate_ci_low", optional_number(report.win_rate_ci_low)},
        {"win_rate_ci_high", optional_number(report.win_rate_ci_high)},
        {"probability_win", optional_number(report.probability_win)},
        {"avg_win_r", optional_number(report.avg_win_r)},
        {"avg_loss_r", optional_number(report.avg_loss_r)},
        {"avg_fee_r", optional_number(report.avg_fee_r)},
        {"avg_slippage_r", optional_number(report.avg_slippage_r)},
        {"avg_funding_r", optional_number(report.avg_funding_r)},
        {"ev_net", optional_number(report.ev_net)},
        {"ev_status", report.ev_status}, {"ev_decision", report.ev_decision}
    };
}

json evaluate_candidate(const json& candidate, const std::string& regime,
                        const std::vector<cfss::meta::Outcome>& outcomes,
                        bool ledger_available) {
    auto status = candidate.value("status", std::string{"INSUFFICIENT_DATA"});
    const auto path = candidate.value("path", std::string{"UNKNOWN"});
    const auto score = candidate.contains("score") && candidate.at("score").is_number()
        ? std::optional<double>{candidate.at("score").get<double>()} : std::nullopt;
    cfss::meta::CalibrationReport report{};
    std::string reason = "NO_CANDIDATE_TO_CALIBRATE";

    if (status == "CANDIDATE") {
        if (candidate.value("hypothesis", std::string{}).empty() ||
            candidate.value("falsification", std::string{}).empty() ||
            !score || *score < 0.0 || *score > 1.0) {
            status = "INSUFFICIENT_DATA";
            reason = "CANDIDATE_MISSING_HYPOTHESIS_FALSIFICATION_OR_SCORE";
        } else if (!ledger_available) {
            report.reason = "OUTCOME_LEDGER_MISSING";
            reason = report.reason;
        } else {
            report = cfss::meta::calibrate(outcomes, path, regime, *score);
            reason = report.reason;
            if (report.status == "INVALID_OUTCOME_LEDGER") {
                status = "INSUFFICIENT_DATA";
            } else if (report.ev_decision == "NO_TRADE") {
                status = "NO_TRADE";
            } else if (report.ev_decision == "EV_POSITIVE_RESEARCH_ONLY") {
                status = "EV_POSITIVE_RESEARCH_ONLY";
            }
        }
    }

    return {
        {"path", path},
        {"candidate_status", status},
        {"direction", candidate.value("direction", std::string{"NONE"})},
        {"raw_score", optional_number(score)},
        {"data_class", candidate.value("data_class", std::string{"UNAVAILABLE"})},
        {"hypothesis", candidate.value("hypothesis", std::string{})},
        {"falsification", candidate.value("falsification", std::string{})},
        {"confidence_status", report.status == "CALIBRATED" ? "CALIBRATED" : "NOT_CALIBRATED"},
        {"confidence_probability", optional_number(report.probability_win)},
        {"calibration", calibration_json(report)},
        {"ev_status", report.ev_status},
        {"ev_net", optional_number(report.ev_net)},
        {"ev_decision", report.ev_decision},
        {"reason", reason},
        {"regime", regime},
        {"actionable", false}
    };
}
}

int main(int argc, char** argv) {
    if (argc != 5) {
        std::cerr << "usage: meta_cognition_probe <dual-engine-report.json> <liquidity.json> <outcomes-ledger.json> <meta-cognition.json>\n";
        return 2;
    }
    try {
        const std::filesystem::path dual_path{argv[1]};
        const std::filesystem::path liquidity_path{argv[2]};
        const std::filesystem::path outcomes_path{argv[3]};
        const auto dual = read_json(dual_path);
        const auto liquidity = read_json(liquidity_path);
        const auto ledger = read_json(outcomes_path);
        if (dual.value("artifact_type", std::string{}) != "cfss_dual_engine_report_v1" ||
            liquidity.value("artifact_type", std::string{}) != "cfss_liquidity_phase_v1" ||
            ledger.value("artifact_type", std::string{}) != "cfss_outcome_ledger_v1")
            throw std::runtime_error("input_artifact_type_mismatch");

        const auto run_id = dual.value("source_run_id", std::string{});
        const auto scan_id = dual.value("source_scan_id", std::string{});
        const auto decision_time = dual.value("decision_time_ms", std::int64_t{0});
        const auto l1_hash = dual.value("l1_sha256", std::string{});
        if (liquidity.value("source_run_id", std::string{}) != run_id ||
            liquidity.value("source_scan_id", std::string{}) != scan_id ||
            liquidity.value("decision_time_ms", std::int64_t{0}) != decision_time ||
            liquidity.value("l1_sha256", std::string{}) != l1_hash)
            throw std::runtime_error("STAGE5_STAGE4_PROVENANCE_MISMATCH");

        const auto outcomes = parse_outcomes(ledger);
        const bool ledger_available = ledger.value("ledger_status", std::string{"AVAILABLE"}) == "AVAILABLE";
        json instruments = json::array();
        for (const auto& item : dual.at("instruments")) {
            const auto symbol = item.value("symbol", std::string{"UNKNOWN"});
            std::string phase = "UNAVAILABLE";
            for (const auto& liq : liquidity.at("instruments"))
                if (liq.value("symbol", std::string{}) == symbol)
                    phase = liq.value("phase", std::string{"UNAVAILABLE"});
            instruments.push_back({
                {"symbol", symbol},
                {"regime", phase},
                {"golden_rule", item.at("golden_rule")},
                {"lrt", evaluate_candidate(item.at("lrt"), phase, outcomes, ledger_available)},
                {"nmt", evaluate_candidate(item.at("nmt"), phase, outcomes, ledger_available)}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_meta_cognition_v1"},
            {"version", "META_COGNITION_V1"},
            {"source_run_id", run_id},
            {"source_scan_id", scan_id},
            {"decision_time_ms", decision_time},
            {"l1_sha256", l1_hash},
            {"stage5_report_sha256", cfss::sha256_hex(read_raw(dual_path))},
            {"liquidity_report_sha256", cfss::sha256_hex(read_raw(liquidity_path))},
            {"outcome_ledger_sha256", cfss::sha256_hex(read_raw(outcomes_path))},
            {"outcome_ledger_status", ledger.value("ledger_status", std::string{"AVAILABLE"})},
            {"outcome_ledger_count", outcomes.size()},
            {"calibration_policy", {
                {"split", "CHRONOLOGICAL_60_20_20"},
                {"minimum_total", 180},
                {"minimum_train", 100},
                {"minimum_validation", 30},
                {"minimum_oos", 50},
                {"methods", {"PLATT", "ISOTONIC"}},
                {"selection", "VALIDATION_BRIER_ONLY"},
                {"final_evaluation", "UNTOUCHED_OOS"}
            }},
            {"actionable", false},
            {"instruments", instruments}
        };
        write_json(argv[4], output);
        std::cout << "META_COGNITION_STATUS=GENERATED"
                  << " OUTCOME_LEDGER_STATUS=" << output.at("outcome_ledger_status")
                  << " OUTCOMES=" << outcomes.size() << '\n';
        for (const auto& item : instruments)
            std::cout << item.at("symbol").get<std::string>()
                      << " LRT=" << item.at("lrt").at("candidate_status").get<std::string>()
                      << " LRT_CONF=" << item.at("lrt").at("confidence_status").get<std::string>()
                      << " NMT=" << item.at("nmt").at("candidate_status").get<std::string>()
                      << " NMT_CONF=" << item.at("nmt").at("confidence_status").get<std::string>()
                      << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "META_COGNITION_PROBE_ERROR=" << error.what() << '\n';
        return 1;
    }
}
