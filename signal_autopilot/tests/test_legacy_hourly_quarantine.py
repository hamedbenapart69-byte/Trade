"""Regression guard: the retired 1H engine cannot fetch, score, or publish."""
from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import logic


ROOT = Path(__file__).resolve().parents[1]


class LegacyHourlyQuarantineTests(unittest.TestCase):
    def test_retired_engine_is_a_fail_closed_tombstone(self):
        output = StringIO()
        with redirect_stdout(output):
            logic.main()
        payload = json.loads(output.getvalue())

        self.assertEqual(payload["pipeline_status"], "DISABLED_LEGACY_ENGINE")
        self.assertEqual(payload["market_scan"], "DISABLED")
        self.assertEqual(payload["dashboard_publication"], "DISABLED")
        self.assertEqual(payload["telegram_delivery"], "DISABLED")
        self.assertIs(payload["manual_trade_only"], True)
        self.assertFalse((ROOT / "legacy").exists())
        self.assertNotIn("MarketDataFetcher", logic.__dict__)


if __name__ == "__main__":
    unittest.main()
