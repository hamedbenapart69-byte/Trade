"""Static security checks for the public L2 collector/persistence split."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = (ROOT / ".github/workflows/orderbook-l2.yml").read_text(encoding="utf-8")
PERSIST = (ROOT / ".github/workflows/persist-orderbook-l2.yml").read_text(encoding="utf-8")


class OrderbookWorkflowSecurityTests(unittest.TestCase):
    def test_collector_is_read_only_and_does_not_push(self):
        self.assertIn("permissions:\n  contents: read", COLLECTOR)
        self.assertNotIn("contents: write", COLLECTOR)
        self.assertNotIn("git push", COLLECTOR)
        self.assertIn("actions/upload-artifact@v4", COLLECTOR)

    def test_persistence_runs_only_for_successful_in_repo_main_capture(self):
        self.assertIn('workflows: ["Public L2 Order Book Collector"]', PERSIST)
        self.assertIn("branches: [main]", PERSIST)
        self.assertIn("conclusion == 'success'", PERSIST)
        self.assertIn("head_repository.full_name == github.repository", PERSIST)

    def test_write_permission_is_scoped_to_trusted_persist_job(self):
        self.assertIn("permissions:\n  contents: read", PERSIST)
        self.assertIn("actions: read\n      contents: write", PERSIST)
        self.assertIn("ref: main", PERSIST)
        self.assertIn("ref: market-data", PERSIST)

    def test_persistence_uses_non_force_push(self):
        self.assertIn("git push origin HEAD:refs/heads/market-data", PERSIST)
        self.assertNotIn("--force", PERSIST)
        self.assertIn("git rebase --abort", PERSIST)


if __name__ == "__main__":
    unittest.main()
