#include "cfss/meta_calibration.hpp"
#include "cfss/meta_cognition.hpp"
#include "cfss/hash.hpp"
#include "cfss/atomic_file.hpp"
#include "cfss/shadow_outcomes.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
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
        const std::vector<std::string> required{
            "signal_id", "path", "regime", "closed_at_ms", "raw_score",
            "profile", "entry_fill_reference", "entry_model", "execution_status", "outcome_kind",
            "data_class", "cost_status",
            "resolution_data_sha256", "resolution_bars", "source_scan_id", "symbol",
            "win", "win_r", "loss_r", "fee_r", "slippage_r", "funding_r", "score_model_version"
        };
        for (const auto& key : required) {
            if (!row.contains(key))
                throw std::runtime_error("outcome_required_field_missing:" + key);
            const bool nullable_cost = key == "fee_r" || key == "slippage_r" || key == "funding_r";
            if (row.at(key).is_null() && !nullable_cost)
                throw std::runtime_error("outcome_required_field_null:" + key);
        }
        if (!row.at("signal_id").is_string() || !row.at("path").is_string() ||
            !row.at("regime").is_string() || !row.at("closed_at_ms").is_number_integer() ||
            !row.at("profile").is_string() || !row.at("data_class").is_string() ||
            !row.at("cost_status").is_string() || !row.at("score_model_version").is_string() ||
            !row.at("entry_fill_reference").is_number() ||
            !row.at("entry_model").is_string() || !row.at("execution_status").is_string() ||
            !row.at("outcome_kind").is_string() ||
            !row.at("resolution_data_sha256").is_string() ||
            !row.at("resolution_bars").is_array() || row.at("resolution_bars").empty() ||
            !row.at("source_scan_id").is_string() || !row.at("symbol").is_string() ||
            !row.at("raw_score").is_number() || !row.at("win").is_boolean() ||
            !row.at("win_r").is_number() || !row.at("loss_r").is_number())
            throw std::runtime_error("outcome_field_type_invalid");
        const bool all_costs_numeric = row.at("fee_r").is_number() &&
            row.at("slippage_r").is_number() && row.at("funding_r").is_number();
        const bool all_costs_null = row.at("fee_r").is_null() &&
            row.at("slippage_r").is_null() && row.at("funding_r").is_null();
        if (!all_costs_numeric && !all_costs_null)
            throw std::runtime_error("outcome_cost_fields_must_be_all_numeric_or_all_null");
        const auto cost_status = row.at("cost_status").get<std::string>();
        if ((cost_status == "UNAVAILABLE" && !all_costs_null) ||
            ((cost_status == "REAL" || cost_status == "PROXY") && !all_costs_numeric) ||
            (cost_status != "UNAVAILABLE" && cost_status != "REAL" && cost_status != "PROXY"))
            throw std::runtime_error("outcome_cost_status_does_not_match_cost_fields");
        if (!cfss::shadow::valid_cost_provenance(row))
            throw std::runtime_error("outcome_cost_provenance_invalid");
        if (row.at("profile").get<std::string>() != ledger.value("profile", std::string{}) ||
            row.at("entry_model") != "NEXT_BAR_OPEN_PROXY" ||
            row.at("execution_status") != "NOT_EXECUTED" ||
            row.at("outcome_kind") != "HYPOTHESIS_PROXY")
            throw std::runtime_error("outcome_profile_or_proxy_contract_mismatch");
        const auto data_class = row.at("data_class").get<std::string>();
        if (data_class != "REAL" && data_class != "PROXY")
            throw std::runtime_error("outcome_data_class_invalid");
        cfss::meta::Outcome item{};
        item.signal_id = row.at("signal_id").get<std::string>();
        item.path = row.at("path").get<std::string>();
        item.regime = row.at("regime").get<std::string>();
        item.closed_at_ms = row.at("closed_at_ms").get<std::int64_t>();
        item.raw_score = row.at("raw_score").get<double>();
        item.win = row.at("win").get<bool>();
        item.win_r = row.at("win_r").get<double>();
        item.loss_r = row.at("loss_r").get<double>();
        item.costs_available = all_costs_numeric;
        item.fee_r = all_costs_numeric ? row.at("fee_r").get<double>() : 0.0;
        item.slippage_r = all_costs_numeric ? row.at("slippage_r").get<double>() : 0.0;
        item.funding_r = all_costs_numeric ? row.at("funding_r").get<double>() : 0.0;
        item.data_class = data_class;
        item.profile = row.at("profile").get<std::string>();
        item.outcome_kind = row.at("outcome_kind").get<std::string>();
        item.execution_status = row.at("execution_status").get<std::string>();
        item.source_scan_id = row.at("source_scan_id").get<std::string>();
        item.symbol = row.at("symbol").get<std::string>();
        item.score_model_version = row.at("score_model_version").get<std::string>();
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
        {"score_model_version", report.score_model_version},
        {"sample_count", report.sample_count}, {"train_count", report.train_count},
        {"validation_count", report.validation_count}, {"oos_count", report.oos_count},
        {"train_scan_clusters", report.train_scan_clusters},
        {"train_symbol_clusters", report.train_symbol_clusters},
        {"train_utc_day_clusters", report.train_utc_day_clusters},
        {"validation_scan_clusters", report.validation_scan_clusters},
        {"validation_symbol_clusters", report.validation_symbol_clusters},
        {"validation_utc_day_clusters", report.validation_utc_day_clusters},
        {"oos_scan_clusters", report.oos_scan_clusters},
        {"oos_symbol_clusters", report.oos_symbol_clusters},
        {"oos_utc_day_clusters", report.oos_utc_day_clusters},
        {"train_effective_sample_size", report.train_effective_sample_size},
        {"validation_effective_sample_size", report.validation_effective_sample_size},
        {"oos_effective_sample_size", report.oos_effective_sample_size},
        {"oos_period_start_ms", report.oos_period_start_ms},
        {"oos_period_end_ms", report.oos_period_end_ms},
        {"oos_symbol_distribution", report.oos_symbol_distribution},
        {"oos_daily_distribution", report.oos_daily_distribution},
        {"confidence_interval_method", report.confidence_interval_method},
        {"win_rate_interval_method", report.win_rate_interval_method},
        {"brier_raw_oos", optional_number(report.brier_raw_oos)},
        {"brier_calibrated_oos", optional_number(report.brier_calibrated_oos)},
        {"brier_ci_low", optional_number(report.brier_ci_low)},
        {"brier_ci_high", optional_number(report.brier_ci_high)},
        {"brier_improvement_oos", optional_number(report.brier_improvement_oos)},
        {"brier_improvement_ci_low", optional_number(report.brier_improvement_ci_low)},
        {"brier_improvement_ci_high", optional_number(report.brier_improvement_ci_high)},
        {"power_analysis_status", report.power_analysis_status},
        {"target_brier_improvement_provisional", report.target_brier_improvement},
        {"power_alpha", report.power_alpha},
        {"target_power", report.target_power},
        {"validation_brier_improvement_se", report.validation_brier_improvement_se},
        {"required_oos_effective_sample_size", report.required_oos_effective_sample_size},
        {"log_loss_oos", optional_number(report.log_loss_oos)},
        {"ece_raw_oos", optional_number(report.ece_raw_oos)},
        {"ece_calibrated_oos", optional_number(report.ece_calibrated_oos)},
        {"reliability_bins", [&]() {
            json bins = json::array();
            for (const auto& bin : report.reliability_bins) {
                bins.push_back({
                    {"lower_bound", bin.lower_bound},
                    {"upper_bound", bin.upper_bound},
                    {"count", bin.count},
                    {"mean_probability", bin.mean_probability},
                    {"observed_win_rate", bin.observed_win_rate}
                });
            }
            return bins;
        }()},
        {"win_rate_oos", optional_number(report.win_rate_oos)},
        {"win_rate_ci_low", optional_number(report.win_rate_ci_low)},
        {"win_rate_ci_high", optional_number(report.win_rate_ci_high)},
        {"win_rate_cluster_ci_low", optional_number(report.win_rate_cluster_ci_low)},
        {"win_rate_cluster_ci_high", optional_number(report.win_rate_cluster_ci_high)},
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
                        bool ledger_available, std::int64_t decision_time) {
    const auto evaluated = cfss::meta::evaluate_calibration_continuously(
        candidate, regime, outcomes, ledger_available, decision_time);
    const auto& report = evaluated.calibration;
    const auto path = candidate.value("path", std::string{"UNKNOWN"});
    const auto score_model_version = candidate.value(
        "score_model_version",
        path == "PLAN_A_LRT" ? std::string{"LFS_V2_PROXY"} :
        (path == "PLAN_A_NMT" ? std::string{"NSS_V2_PROXY"} : std::string{"UNAVAILABLE"}));
    const auto score = candidate.contains("score") && candidate.at("score").is_number()
        ? std::optional<double>{candidate.at("score").get<double>()} : std::nullopt;
    return {
        {"path", path},
        {"candidate_status", evaluated.candidate_status},
        {"direction", candidate.value("direction", std::string{"NONE"})},
        {"raw_score", optional_number(score)},
        {"data_class", candidate.value("data_class", std::string{"UNAVAILABLE"})},
        {"score_model_version", score_model_version},
        {"hypothesis", candidate.value("hypothesis", std::string{})},
        {"falsification", candidate.value("falsification", std::string{})},
        {"confidence_status", report.status == "CALIBRATED" ? "CALIBRATED" : "NOT_CALIBRATED"},
        {"confidence_probability", optional_number(report.probability_win)},
        {"calibration", calibration_json(report)},
        {"ev_status", report.ev_status},
        {"ev_net", optional_number(report.ev_net)},
        {"ev_decision", report.ev_decision},
        {"reason", evaluated.reason},
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
        if (ledger.value("profile", std::string{}) != "DAILY_SWING" ||
            dual.value("artifact_type", std::string{}) != "cfss_dual_engine_report_v1" ||
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
        const bool ledger_available = ledger.value("ledger_status", std::string{"UNAVAILABLE"}) == "AVAILABLE";
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
                {"lrt", evaluate_candidate(item.at("lrt"), phase, outcomes, ledger_available, decision_time)},
                {"nmt", evaluate_candidate(item.at("nmt"), phase, outcomes, ledger_available, decision_time)}
            });
        }

        const json output = {
            {"schema_version", "1.0.0"},
            {"artifact_type", "cfss_meta_cognition_v1"},
            {"profile", "DAILY_SWING"},
            {"calibration_scope", {
                {"outcome_kind", "HYPOTHESIS_PROXY"},
                {"execution_status", "NOT_EXECUTED"},
                {"entry_model", "NEXT_BAR_OPEN_PROXY"},
                {"ev_policy", "BLOCK_WHEN_COSTS_UNAVAILABLE"}
            }},
            {"version", "META_COGNITION_V1"},
            {"source_run_id", run_id},
            {"source_scan_id", scan_id},
            {"decision_time_ms", decision_time},
            {"l1_sha256", l1_hash},
            {"stage5_report_sha256", cfss::sha256_hex(read_raw(dual_path))},
            {"liquidity_report_sha256", cfss::sha256_hex(read_raw(liquidity_path))},
            {"outcome_ledger_sha256", cfss::sha256_hex(read_raw(outcomes_path))},
            {"outcome_ledger_status", ledger.value("ledger_status", std::string{"UNAVAILABLE"})},
            {"outcome_ledger_count", outcomes.size()},
            {"calibration_policy", {
                {"split", "CHRONOLOGICAL_60_20_20_PROVISIONAL_INTERNAL"},
                {"split_is_canonical_requirement", false},
                {"sample_size_policy", "PROVISIONAL_INTERNAL_GUARD_WITH_VALIDATION_BASED_POWER_ESTIMATE"},
                {"power_analysis_method", "THREE_WAY_CLUSTER_SE_VALIDATION_PROXY"},
                {"power_analysis_status", "PER_COHORT_AT_RUNTIME"},
                {"target_brier_improvement_provisional", 0.01},
                {"power_alpha", 0.05},
                {"target_power", 0.80},
                {"minimum_total_provisional", 250},
                {"minimum_oos_effective_sample_size_floor_provisional", 30.0},
                {"cluster_dimensions", json::array({"source_scan_id", "symbol", "utc_day"})},
                {"confidence_interval_method", "MAX_OF_ONE_WAY_CLUSTER_SE"},
                {"win_rate_interval_method", "WILSON_95_PLUS_MAX_OF_ONE_WAY_CLUSTER_SE"},
                {"minimum_train_provisional", 100},
                {"minimum_validation_provisional", 30},
                {"minimum_oos_provisional", 50},
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
