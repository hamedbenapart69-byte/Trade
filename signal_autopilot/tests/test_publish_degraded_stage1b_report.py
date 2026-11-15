"""آزمون گزارش صریح MARKET_DATA_DEGRADED پس از شکست اسکنر."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "signal_autopilot" / "scripts"))

from publish_degraded_stage1b_report import (
    build_degraded_source,
    publish_degraded_report,
)

UNIVERSE = ROOT / "config" / "universe.json"


class DegradedStage1BReportTests(unittest.TestCase):
    def test_degraded_source_covers_full_universe_without_market_values(self):
        source = build_degraded_source(
            UNIVERSE,
            "2026-11-15T05:00:00+00:00",
            "123456",
            "failure",
        )
        self.assertEqual(source["report_status"], "MARKET_DATA_DEGRADED")
        self.assertEqual(source["production_watchlist_count"], 0)
        self.assertEqual(source["research_candidate_count"], 0)
        self.assertEqual(source["symbols_reported"], source["universe_count"])
        self.assertEqual(source["upstream_run_id"], "123456")
        self.assertEqual(source["upstream_conclusion"], "failure")
        self.assertTrue(all(row["veto"] == "DATA_WORKFLOW_FAILED" for row in source["symbols"]))
        self.assertTrue(all(row["entry"] is None and row["stop_loss"] is None for row in source["symbols"]))
        self.assertTrue(all(row["take_profit_1"] is None and row["take_profit"] is None for row in source["symbols"]))
        self.assertTrue(all(row["cvd"]["source"] == "UNAVAILABLE" for row in source["symbols"]))

    def test_publishes_degraded_snapshot_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "signals"
            generated = datetime.now(timezone.utc).isoformat()
            result = publish_degraded_report(
                UNIVERSE,
                output_dir,
                generated,
                "123456",
                "timed_out",
            )
            dashboard = json.loads((output_dir / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["report_status"], "MARKET_DATA_DEGRADED")
            self.assertEqual(dashboard["upstream_run_id"], "123456")
            self.assertEqual(dashboard["upstream_conclusion"], "timed_out")
            self.assertEqual(dashboard["candidate_setups"], 0)
            self.assertTrue(all(row["decision"] == "MARKET_DATA_DEGRADED" for row in dashboard["signals"]))
            self.assertTrue(all(row["entry"] is None and row["take_profit"] is None for row in dashboard["signals"]))
            self.assertTrue((output_dir / "lrt15m_history.csv").exists())
            self.assertEqual(result["report_status"], "MARKET_DATA_DEGRADED")

    def test_rejects_old_failure_event_instead_of_overwriting_fresh_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "REPORT_STALE"):
                publish_degraded_report(
                    UNIVERSE,
                    Path(tmp) / "signals",
                    (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
                    "123456",
                    "failure",
                )

    def test_rejects_non_failure_conclusion(self):
        with self.assertRaisesRegex(ValueError, "SCANNER_FAILURE_CONCLUSION_INVALID"):
            build_degraded_source(
                UNIVERSE,
                datetime.now(timezone.utc).isoformat(),
                "123456",
                "success",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
