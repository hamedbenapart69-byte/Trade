"""Regression checks for the quarantined legacy Stage 1B dashboard workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-stage1b-dashboard.yml"
APP = ROOT / "web" / "futures" / "app.js"


class Stage1BDashboardWorkflowTests(unittest.TestCase):
    def test_legacy_dashboard_publisher_is_quarantined(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("workflow_run:", workflow)
        self.assertIn("publish-dashboard:\n    if: ${{ false }}", workflow)
        self.assertIn("publish-degraded-report:\n    if: ${{ false }}", workflow)
        self.assertNotIn("actions/download-artifact", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("pages: write", workflow)

    def test_dashboard_publisher_has_no_legacy_telegram_or_web_delivery_path(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("TELEGRAM_TOKEN", workflow)
        self.assertNotIn("workflow_run:", workflow)
        self.assertNotIn("git -C signals-repo push", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)

    def test_dashboard_publication_is_not_part_of_v18_2(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("publish_stage1b_dashboard.py", workflow)
        self.assertNotIn("publish_degraded_stage1b_report.py", workflow)
        self.assertNotIn("incoming/stage1_lrt_report.json", workflow)

    def test_dashboard_consumes_lrt_specific_files_and_marks_unreported_gate(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("/signals/lrt15m_signals.json", app)
        self.assertIn("/signals/lrt15m_history.csv", app)
        self.assertIn('report.data_gate_status || "NOT_REPORTED"', app)
        self.assertIn("NOT_CALIBRATED", app)
        self.assertIn("TP1:", app)
        self.assertIn("TP2:", app)
        self.assertIn("<th>LFS</th>", app)
        self.assertIn("item.lfs_score", app)
        self.assertIn("item.lfs_coverage_pct", app)
        self.assertIn("report.report_status", app)
        self.assertIn("MARKET_DATA_DEGRADED", app)
        self.assertIn("report.failure_reason", app)
        self.assertIn("فرضیه:", app)
        self.assertIn("ابطال:", app)
        self.assertIn("const fmtPrice", app)

    def test_dashboard_exposes_effective_lfs_threshold(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("item.lfs_threshold", app)
        self.assertIn("item.lfs_threshold_reason", app)

    def test_dashboard_freshness_matches_publisher_clock_skew_and_caches_history(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("MAX_FUTURE_SKEW_MS = 5 * 60 * 1000", app)
        self.assertIn("ageMs < -MAX_FUTURE_SKEW_MS", app)
        self.assertIn("Math.max(0, ageMs)", app)
        self.assertIn("historyLoaded && !force", app)
        self.assertIn("reportLoading", app)
        self.assertIn("loadReport(true)", app)

    def test_dashboard_summary_does_not_call_watchlist_a_qualified_trade(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("نامزدهای زیرنظر", app)
        self.assertNotIn("موقعیت‌های واجد شرایط", app)

    def test_stale_reports_do_not_show_old_candidates_as_current(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn("if (!freshness.fresh)", app)
        self.assertIn("وضعیت‌های قبلی برای ورود جدید نمایش داده نمی‌شوند", app)
        self.assertIn("freshness.fresh ? fmt(report.candidate_setups", app)


if __name__ == "__main__":
    unittest.main(verbosity=2)
