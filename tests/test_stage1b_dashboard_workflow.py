"""Regression checks for the Stage 1B public dashboard publisher workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-stage1b-dashboard.yml"
APP = ROOT / "web" / "futures" / "app.js"


class Stage1BDashboardWorkflowTests(unittest.TestCase):
    def test_scanner_failure_publishes_explicit_degraded_snapshot(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("publish-degraded-report:", workflow)
        self.assertIn("publish_degraded_stage1b_report.py", workflow)
        self.assertIn("MARKET_DATA_DEGRADED", workflow)
        self.assertIn("github.event.workflow_run.updated_at", workflow)
        failure_job = workflow.split("publish-degraded-report:", 1)[1]
        self.assertNotIn("actions/download-artifact", failure_job)
        self.assertIn("timed_out", failure_job)

    def test_publisher_runs_only_after_successful_scanner_and_uses_trusted_code(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"Trader_me Stage 1B LRT-15m Signal Bot"', content)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", content)
        self.assertIn("ref: production-v1", content)
        self.assertIn("ref: signals", content)
        self.assertIn("persist-credentials: false", content)
        self.assertIn("contents: write", content)
        self.assertIn('python-version: "3.11"', content)

    def test_publisher_downloads_scanner_artifact_and_writes_only_lrt_files(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("trader-me-stage1-signal-bot-${{ github.event.workflow_run.id }}", content)
        self.assertIn("incoming/stage1_lrt_report.json", content)
        self.assertIn("publish_stage1b_dashboard.py", content)
        self.assertIn("git -C signals-repo add lrt15m_signals.json lrt15m_history.csv", content)
        self.assertNotIn("git -C signals-repo add .", content)

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
