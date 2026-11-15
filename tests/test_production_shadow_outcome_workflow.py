"""Regression tests for production WATCHLIST shadow outcome workflow."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production_shadow_outcome_tracker.yml"


class ProductionShadowOutcomeWorkflowTests(unittest.TestCase):
    def test_runs_after_successful_persist_and_has_manual_recovery(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"Persist Stage 1B Scanner State"', content)
        self.assertIn("types: [completed]", content)
        self.assertIn("branches: [main]", content)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", content)
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("github.ref == 'refs/heads/main'", content)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", content)

    def test_uses_production_code_and_signal_state_branch(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("ref: production-v1", content)
        self.assertIn("ref: signal-state", content)
        self.assertIn("signal-state/signal_autopilot/state/open_signals.json", content)
        self.assertIn("signal-state/signal_autopilot/state/production_outcomes.json", content)
        self.assertIn('python-version: "3.11"', content)

    def test_is_public_data_only_and_never_executes_orders(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("public OHLCV only", content)
        self.assertIn('row.get("execution_status") != "NOT_EXECUTED"', content)
        self.assertIn('row.get("statistics_status") != "NOT_CALCULATED"', content)
        self.assertNotIn("TELEGRAM_TOKEN", content)
        self.assertNotIn("API_SECRET", content)
        self.assertNotIn("create_order", content)

    def test_persists_only_the_separate_production_outcomes_file(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git -C signal-state add signal_autopilot/state/production_outcomes.json", content)
        self.assertNotIn("git -C signal-state add .", content)
        self.assertIn("group: research-state-writes", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
