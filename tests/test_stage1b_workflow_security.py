"""Policy tests for quarantined legacy Python Stage 1B automation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class Stage1BWorkflowSecurityTests(unittest.TestCase):
    def test_legacy_signal_bot_is_disabled_and_cannot_publish(self):
        scanner = read("signal_bot.yml")
        self.assertIn("workflow_dispatch:", scanner)
        self.assertNotIn("schedule:", scanner)
        self.assertNotIn("push:", scanner)
        self.assertIn("live-scan:\n    if: ${{ false }}", scanner)
        self.assertNotIn("actions/upload-artifact", scanner)
        self.assertNotIn("TELEGRAM_TOKEN:", scanner)
        self.assertNotIn("TELEGRAM_CHAT_ID:", scanner)

    def test_legacy_trusted_telegram_notifier_is_disabled(self):
        notifier = read("trusted-stage1b-telegram.yml")
        self.assertNotIn("workflow_run:", notifier)
        self.assertIn("notify:\n    if: ${{ false }}", notifier)
        self.assertNotIn("secrets.TELEGRAM_TOKEN", notifier)
        self.assertNotIn("secrets.TELEGRAM_CHAT_ID", notifier)
        self.assertNotIn("contents: write", notifier)

    def test_legacy_state_writer_is_disabled(self):
        writer = read("persist-stage1b-state.yml")
        self.assertNotIn("workflow_run:", writer)
        self.assertIn("persist-state:\n    if: ${{ false }}", writer)
        self.assertNotIn("contents: write", writer)
        self.assertNotIn("actions/download-artifact", writer)

    def test_legacy_p0_persistence_is_disabled(self):
        writer = read("persist-stage1b-p0-data.yml")
        self.assertNotIn("workflow_run:", writer)
        self.assertIn("persist:\n    if: ${{ false }}", writer)
        self.assertNotIn("contents: write", writer)
        self.assertNotIn("actions/download-artifact", writer)

    def test_legacy_dashboard_publisher_is_disabled(self):
        publisher = read("publish-stage1b-dashboard.yml")
        self.assertNotIn("workflow_run:", publisher)
        self.assertIn("publish-dashboard:\n    if: ${{ false }}", publisher)
        self.assertIn("publish-degraded-report:\n    if: ${{ false }}", publisher)
        self.assertNotIn("pages: write", publisher)

    def test_remaining_legacy_maintenance_is_manual_only(self):
        for name in (
            "stage1b-scheduled.yml",
            "research_outcome_tracker.yml",
            "test_okx_endpoints.yml",
        ):
            with self.subTest(workflow=name):
                content = read(name)
                self.assertIn("workflow_dispatch:", content)
                self.assertNotIn("schedule:", content)
                self.assertNotIn("push:", content)
                self.assertNotIn("actions/upload-artifact", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
