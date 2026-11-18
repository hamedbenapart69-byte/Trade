"""Security checks for V18.2 quarantine of the legacy Python L2 pipeline."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


class OrderbookWorkflowSecurityTests(unittest.TestCase):
    def test_legacy_collector_is_manual_only_and_has_no_artifact_upload(self):
        collector = read("orderbook-l2.yml")
        self.assertIn("workflow_dispatch:", collector)
        self.assertNotIn("schedule:", collector)
        self.assertNotIn("push:", collector)
        self.assertNotIn("actions/upload-artifact", collector)
        self.assertIn("permissions:\n  contents: read", collector)
        self.assertNotIn("contents: write", collector)
        self.assertNotIn("git push", collector)

    def test_legacy_persistence_handler_is_quarantined(self):
        persist = read("persist-orderbook-l2.yml")
        self.assertIn("workflow_dispatch:", persist)
        self.assertNotIn("workflow_run:", persist)
        self.assertIn("persist:\n    if: ${{ false }}", persist)
        self.assertNotIn("contents: write", persist)
        self.assertNotIn("actions/download-artifact", persist)


if __name__ == "__main__":
    unittest.main()
