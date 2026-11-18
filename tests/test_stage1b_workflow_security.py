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


    def test_paid_railway_deployment_is_disabled(self):
        workflow = read("deploy-railway.yml")
        self.assertIn("deploy:\n    if: ${{ false }}", workflow)
        self.assertNotIn("RAILWAY_TOKEN", workflow)
        self.assertNotIn("railway up", workflow)

    def test_legacy_v5_autopilot_and_pages_deployment_are_disabled(self):
        workflow = read("v5-signal-autopilot.yml")
        self.assertIn("scan-and-build:\n    if: ${{ false }}", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertNotIn("actions/deploy-pages", workflow)
        self.assertNotIn("pages: write", workflow)

    def test_legacy_telegram_probe_is_disabled(self):
        workflow = read("telegram_probe.yml")
        self.assertIn("probe:\n    if: ${{ false }}", workflow)
        self.assertNotIn("TELEGRAM_TOKEN", workflow)
        self.assertNotIn("TELEGRAM_AUDIENCE_CHANNEL_ID", workflow)
        self.assertNotIn("V9 PROBE", workflow)

    def test_legacy_channel_check_is_manual_only(self):
        workflow = read("telegram_channel_check.yml")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("schedule:", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
