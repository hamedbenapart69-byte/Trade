#include "cfss/risk_gate.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <string>

using namespace cfss::risk;

namespace {
struct TestSuite {
    int checks{0};
    int failures{0};

    void check(bool passed, const std::string& name) {
        ++checks;
        if (!passed) {
            ++failures;
            std::cerr << "FAIL: " << name << '\n';
        }
    }
};

Input ready() {
    Input x;
    x.candidate_present = true;
    x.data_real = true;
    x.liquidity_ok = true;
    x.calibration_valid = true;
    x.net_ev_r = 0.15;
    x.costs_complete = true;
    x.consensus_valid = true;
    x.consensus_reason = "CONSENSUS_CONFIRMED";
    x.correlation_data_valid = true;
    x.risk_snapshot_valid = true;
    x.daily_loss_pct = 1.0;
    x.weekly_loss_pct = 2.0;
    x.portfolio_drawdown_pct = 10.0;
    x.correlated_candidate_exposures = 1;
    return x;
}
} // namespace

int main() {
    TestSuite t;

    t.check(evaluate(Input{}).reason == "NO_QUALIFIED_CANDIDATE",
            "empty input blocks");

    Input x = ready();
    x.golden_rule_veto = true;
    t.check(evaluate(x).reason == "GOLDEN_RULE_HARD_VETO",
            "Golden Rule hard veto");

    x = ready();
    x.candidate_actionable = true;
    t.check(evaluate(x).reason == "UPSTREAM_ACTIONABILITY_FORBIDDEN",
            "upstream actionability forbidden");

    x = ready();
    x.data_real = false;
    t.check(evaluate(x).reason == "REAL_DATA_REQUIRED",
            "non-real data blocks");

    x = ready();
    x.liquidity_ok = false;
    t.check(evaluate(x).reason == "LIQUIDITY_GATE_NOT_PASSED",
            "liquidity gate blocks");

    x = ready();
    x.calibration_valid = false;
    t.check(evaluate(x).reason == "CALIBRATION_NOT_VALID",
            "invalid calibration blocks");

    x = ready();
    x.net_ev_r.reset();
    t.check(evaluate(x).reason == "NET_EV_UNAVAILABLE",
            "missing EV blocks");

    x = ready();
    x.net_ev_r = std::numeric_limits<double>::quiet_NaN();
    t.check(evaluate(x).reason == "NET_EV_UNAVAILABLE",
            "NaN EV blocks");

    x = ready();
    x.net_ev_r = 0.0;
    t.check(evaluate(x).reason == "NET_EV_NON_POSITIVE",
            "zero EV blocks");

    x = ready();
    x.net_ev_r = -0.01;
    t.check(evaluate(x).reason == "NET_EV_NON_POSITIVE",
            "negative EV blocks");

    x = ready();
    x.costs_complete = false;
    t.check(evaluate(x).reason == "COSTS_INCOMPLETE",
            "incomplete costs block");

    x = ready();
    x.risk_snapshot_valid = false;
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "invalid risk snapshot blocks");

    x = ready();
    x.daily_loss_pct.reset();
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "missing daily loss blocks");

    x = ready();
    x.weekly_loss_pct.reset();
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "missing weekly loss blocks");

    x = ready();
    x.portfolio_drawdown_pct.reset();
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "missing portfolio drawdown blocks");

    x = ready();
    x.daily_loss_pct = std::numeric_limits<double>::quiet_NaN();
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "NaN risk percentage blocks");

    x = ready();
    x.daily_loss_pct = -0.01;
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "negative risk percentage blocks");

    x = ready();
    x.weekly_loss_pct = 100.01;
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "risk percentage over 100 blocks");

    x = ready();
    x.correlated_candidate_exposures = -1;
    t.check(evaluate(x).reason == "RISK_SNAPSHOT_INVALID_OR_MISSING",
            "negative correlated exposure count blocks");

    x = ready();
    x.daily_loss_pct = 5.0;
    t.check(evaluate(x).reason == "G7_DAILY_KILL_SWITCH_5_PERCENT",
            "daily kill switch at threshold");

    x = ready();
    x.daily_loss_pct = 4.999;
    t.check(evaluate(x).status == "RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
            "daily loss immediately below threshold remains eligible for manual review");

    x = ready();
    x.weekly_loss_pct = 10.0;
    t.check(evaluate(x).reason == "G7_WEEKLY_KILL_SWITCH_10_PERCENT",
            "weekly kill switch at threshold");

    x = ready();
    x.weekly_loss_pct = 9.999;
    t.check(evaluate(x).status == "RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
            "weekly loss immediately below threshold remains eligible for manual review");

    x = ready();
    x.portfolio_drawdown_pct = 20.01;
    t.check(evaluate(x).reason == "PORTFOLIO_DRAWDOWN_OVER_20_PERCENT",
            "portfolio drawdown over 20 percent blocks");

    x = ready();
    x.portfolio_drawdown_pct = 20.0;
    t.check(evaluate(x).status == "RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
            "portfolio drawdown at 20 percent is boundary-eligible");

    x = ready();
    x.correlated_candidate_exposures = 3;
    t.check(evaluate(x).reason == "G5_CORRELATED_EXPOSURE_CAP",
            "correlated exposure cap blocks");

    x = ready();
    x.correlated_candidate_exposures = 2;
    t.check(evaluate(x).status == "RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
            "two correlated exposures remain boundary-eligible");

    x = ready();
    const Decision d = evaluate(x);
    t.check(d.status == "RISK_CHECKS_PASSED_MANUAL_REVIEW_ONLY",
            "complete eligible snapshot passes risk checks");
    t.check(!d.trade_execution_allowed,
            "execution remains permanently disabled");
    t.check(d.manual_review_required,
            "manual review remains mandatory");

    if (t.failures != 0) {
        std::cerr << "STAGE7_RISK_GATE_TESTS_FAIL: "
                  << t.failures << "/" << t.checks << " checks failed\n";
        return 1;
    }

    std::cout << "STAGE7_RISK_GATE_TESTS_PASS: "
              << t.checks << " runtime checks executed\n";
    return 0;
}
