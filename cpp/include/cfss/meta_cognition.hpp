#pragma once

#include "cfss/meta_calibration.hpp"

#include <cstdint>
#include <cmath>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace cfss::meta {
using json = nlohmann::json;

struct CandidateEvaluation {
    std::string candidate_status;
    std::string reason;
    CalibrationReport calibration;
};

// کالیبراسیون هر مسیر/رژیم باید مستقل از وجود کاندیدای تازه به‌روزرسانی شود.
inline CandidateEvaluation evaluate_calibration_continuously(
    const json& candidate,
    const std::string& regime,
    const std::vector<Outcome>& outcomes,
    bool ledger_available,
    std::int64_t decision_time_ms) {
    CandidateEvaluation result{};
    result.candidate_status = candidate.value("status", std::string{"INSUFFICIENT_DATA"});
    const auto path = candidate.value("path", std::string{"UNKNOWN"});
    const auto score_model_version = candidate.value(
        "score_model_version",
        path == "PLAN_A_LRT" ? std::string{"LFS_V2_PROXY"} :
        (path == "PLAN_A_NMT" ? std::string{"NSS_V2_PROXY"} : std::string{"UNAVAILABLE"}));
    result.calibration.score_model_version = score_model_version;

    bool has_score = false;
    double score_value = 0.0;
    if (candidate.contains("score") && candidate.at("score").is_number()) {
        score_value = candidate.at("score").get<double>();
        has_score = std::isfinite(score_value);
    }
    const bool is_candidate = result.candidate_status == "CANDIDATE";

    if (is_candidate &&
        (candidate.value("hypothesis", std::string{}).empty() ||
         candidate.value("falsification", std::string{}).empty() ||
         !has_score || score_value < 0.0 || score_value > 1.0)) {
        result.candidate_status = "INSUFFICIENT_DATA";
        result.reason = "CANDIDATE_MISSING_HYPOTHESIS_FALSIFICATION_OR_SCORE";
        result.calibration.reason = result.reason;
        return result;
    }

    if (!has_score || score_value < 0.0 || score_value > 1.0) {
        result.reason = "CURRENT_SCORE_UNAVAILABLE_FOR_CALIBRATION";
        result.calibration.reason = result.reason;
        if (is_candidate) result.candidate_status = "INSUFFICIENT_DATA";
        return result;
    }

    if (!ledger_available) {
        result.reason = "OUTCOME_LEDGER_MISSING";
        result.calibration.reason = result.reason;
        if (is_candidate) result.candidate_status = "INSUFFICIENT_DATA";
        return result;
    }

    // حتی در نبود setup، score و regime جاری برای پایش calibration استفاده می‌شوند.
    result.calibration = calibrate(
        outcomes, path, regime, score_value, decision_time_ms,
        candidate.value("data_class", std::string{"UNAVAILABLE"}),
        "DAILY_SWING", score_model_version);

    if (!is_candidate) {
        result.reason = "NO_QUALIFIED_CANDIDATE";
        return result;
    }

    result.reason = result.calibration.reason;
    if (result.calibration.status == "INVALID_OUTCOME_LEDGER") {
        result.candidate_status = "INSUFFICIENT_DATA";
    } else if (result.calibration.ev_decision == "NO_TRADE") {
        result.candidate_status = "NO_TRADE";
    } else if (result.calibration.ev_decision == "EV_POSITIVE_RESEARCH_ONLY") {
        result.candidate_status = "EV_POSITIVE_RESEARCH_ONLY";
    }
    return result;
}
}  // namespace cfss::meta
