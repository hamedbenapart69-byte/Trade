"""Workflow policy tests for the production-only Stage 1B scanner."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class Stage1BWorkflowSecurityTests(unittest.TestCase):
    def test_scanner_is_read_only_and_uses_production_code(self):
        scanner = (WORKFLOWS / "signal_bot.yml").read_text(encoding="utf-8")
        self.assertIn("ref: production-v1", scanner)
        self.assertIn("permissions:\n  contents: read", scanner)
        self.assertNotIn("contents: write", scanner)
        self.assertNotIn("TELEGRAM_TOKEN:", scanner)
        self.assertNotIn("TELEGRAM_CHAT_ID:", scanner)
        self.assertIn("stage1b-open-signal-state", scanner)
        self.assertIn("stage1-research-state-${{ github.run_id }}", scanner)

    def test_trusted_notifier_accepts_only_main_and_production_runs(self):
        notifier = (WORKFLOWS / "trusted-stage1b-telegram.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main, production-v1]", notifier)
        self.assertIn("head_branch == 'main'", notifier)
        self.assertIn("head_branch == 'production-v1'", notifier)
        self.assertIn("secrets.TELEGRAM_TOKEN", notifier)
        self.assertIn("secrets.TELEGRAM_CHAT_ID", notifier)
        self.assertIn("vars.DASHBOARD_URL", notifier)
        validation_step = notifier.split("Validate report before claiming delivery", 1)[1].split(
            "Claim this scanner run before Telegram delivery", 1
        )[0]
        self.assertNotIn("secrets.TELEGRAM_TOKEN", validation_step)
        self.assertNotIn("secrets.TELEGRAM_CHAT_ID", validation_step)

    def test_trusted_notifier_checks_out_production_code(self):
        notifier = (WORKFLOWS / "trusted-stage1b-telegram.yml").read_text(encoding="utf-8")
        self.assertIn("Checkout trusted notifier from production-v1", notifier)
        self.assertIn("ref: production-v1", notifier)
        self.assertNotIn("ref: main", notifier)
        self.assertIn('python-version: "3.11"', notifier)

    def test_trusted_notifier_only_follows_stage1b_scanner(self):
        notifier = (WORKFLOWS / "trusted-stage1b-telegram.yml").read_text(encoding="utf-8")
        self.assertIn('"Trader_me Stage 1B LRT-15m Signal Bot"', notifier)
        self.assertNotIn('"Trader_me Stage 1 Signal Bot"', notifier)

    def test_live_scanner_never_receives_telegram_secrets(self):
        scanner = (WORKFLOWS / "signal_bot.yml").read_text(encoding="utf-8")
        self.assertIn("read-only, no Telegram credentials", scanner)
        self.assertNotIn("secrets.TELEGRAM_TOKEN", scanner)
        self.assertNotIn("secrets.TELEGRAM_CHAT_ID", scanner)
        self.assertIn('python-version: "3.11"', scanner)
        persistence = (WORKFLOWS / "persist-stage1b-state.yml").read_text(encoding="utf-8")
        self.assertIn('python-version: "3.11"', persistence)


    def test_trusted_notifier_uses_serialized_durable_at_most_once_delivery(self):
        notifier = (WORKFLOWS / "trusted-stage1b-telegram.yml").read_text(encoding="utf-8")
        self.assertIn("group: trusted-stage1b-telegram-delivery", notifier)
        self.assertNotIn("group: trusted-stage1b-telegram-${{ github.event.workflow_run.id }}", notifier)
        self.assertIn("ref: telegram-delivery-state", notifier)
        self.assertIn("contents: write", notifier)
        self.assertIn('claimed=false', notifier)
        self.assertIn('claimed=true', notifier)
        self.assertIn("telegram_delivery_ledger.py claim", notifier)
        self.assertIn("telegram_delivery_ledger.py finalize", notifier)
        self.assertIn("--validate-only", notifier)
        self.assertLess(
            notifier.index("Validate report before claiming delivery"),
            notifier.index("Claim this scanner run before Telegram delivery"),
        )
        self.assertLess(
            notifier.index("Claim this scanner run before Telegram delivery"),
            notifier.index("Send validated Stage 1B report to Telegram"),
        )
        self.assertLess(
            notifier.index("Send validated Stage 1B report to Telegram"),
            notifier.index("Finalize durable delivery state"),
        )

    def test_state_writer_persists_only_validated_state_artifacts(self):
        writer = (WORKFLOWS / "persist-stage1b-state.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main, production-v1]", writer)
        self.assertIn("signal-state", writer)
        self.assertIn("stage1-research-data", writer)
        self.assertIn("research_signals.json", writer)
        self.assertIn("OPEN_SIGNAL_STATE_VALIDATED", writer)
        self.assertIn("RESEARCH_STATE_VALIDATED", writer)

    def test_research_tracker_serializes_research_branch_writes(self):
        tracker = (WORKFLOWS / "research_outcome_tracker.yml").read_text(encoding="utf-8")
        self.assertIn("group: research-state-writes", tracker)

    def test_scanner_artifact_names_match_the_trusted_persistence_contract(self):
        scanner = (WORKFLOWS / "signal_bot.yml").read_text(encoding="utf-8")
        writer = (WORKFLOWS / "persist-stage1b-state.yml").read_text(encoding="utf-8")
        self.assertIn("name: stage1b-open-signal-state", scanner)
        self.assertIn("name: stage1b-open-signal-state", writer)
        self.assertIn("name: stage1-research-state-${{ github.run_id }}", scanner)
        self.assertIn("name: stage1-research-state-${{ github.event.workflow_run.id }}", writer)
        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", writer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
