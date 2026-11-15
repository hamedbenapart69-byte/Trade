"""Regression tests for event-driven research outcome tracking."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "research_outcome_tracker.yml"


class ResearchOutcomeEventTriggerTests(unittest.TestCase):
    def test_tracker_runs_after_persisted_scanner_state(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('workflows:\n      - "Persist Stage 1B Scanner State"', content)
        self.assertIn("types: [completed]", content)
        self.assertIn("branches: [main]", content)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", content)

    def test_schedule_uses_off_peak_minutes_and_keeps_manual_fallback(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "7 */4 * * *"', content)
        self.assertNotIn('cron: "7,22,37,52 * * * *"', content)
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("group: research-state-writes", content)
        self.assertIn('python-version: "3.11"', content)

    def test_outcome_coverage_is_one_to_one_and_fail_closed(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Validate one-to-one signal outcome coverage", content)
        self.assertIn("SOURCE_SIGNAL_ID_DUPLICATE", content)
        self.assertIn("OUTCOME_SIGNAL_ID_DUPLICATE", content)
        self.assertIn("OUTCOME_COVERAGE_MISMATCH", content)
        self.assertIn("OUTCOME_COVERAGE_VALIDATED=PASS", content)

    def test_tracker_remains_public_data_only(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Update research outcomes from public OHLCV only", content)
        self.assertIn("ref: production-v1", content)
        self.assertNotIn("TELEGRAM_TOKEN", content)
        self.assertNotIn("API_SECRET", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
