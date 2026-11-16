"""آزمون‌های آفلاین تجمیع معاملات آرشیوی به کندل."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "reconstruct_filusdt_gap_from_trades.py"
SPEC = importlib.util.spec_from_file_location("reconstruct_filusdt_gap_from_trades", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

INTERVAL_MS = MODULE.INTERVAL_MS


class TradeReconstructionTests(unittest.TestCase):
    def test_aggregates_ohlcv_and_excludes_na_rows(self):
        start = 1_800_000_000_000
        rows = [
            {"trade_time": start + 2, "trade_id": 12, "price": "10.5", "quantity": "2", "order_type": "MARKET"},
            {"trade_time": start + 1, "trade_id": 11, "price": "10", "quantity": "1", "order_type": "MARKET"},
            {"trade_time": start + 3, "trade_id": 13, "price": "0", "quantity": "0", "order_type": "NA"},
            {"trade_time": start + INTERVAL_MS + 1, "trade_id": 14, "price": "11", "quantity": "3", "order_type": "MARKET"},
        ]
        candles, quality = MODULE.aggregate_trade_rows(rows)
        self.assertEqual(candles[start]["open"], "10")
        self.assertEqual(candles[start]["high"], "10.5")
        self.assertEqual(candles[start]["low"], "10")
        self.assertEqual(candles[start]["close"], "10.5")
        self.assertEqual(candles[start]["volume"], "3")
        self.assertEqual(candles[start + INTERVAL_MS]["volume"], "3")
        self.assertEqual(quality["na_order_type_rows"], 1)
        self.assertEqual(quality["valid_trade_rows"], 3)

    def test_trade_id_quality_counts_duplicates_and_gaps(self):
        rows = [{"trade_id": value} for value in [10, 11, 11, 14, 15]]
        quality = MODULE.trade_id_quality(rows)
        self.assertEqual(quality["trade_id_rows"], 5)
        self.assertEqual(quality["unique_trade_ids"], 4)
        self.assertEqual(quality["duplicate_trade_ids"], 1)
        self.assertEqual(quality["trade_id_gap_intervals"], 1)
        self.assertEqual(quality["missing_trade_ids_estimate"], 2)

    def test_hour_file_selection_stays_under_anonymous_limit(self):
        segments = [
            {"start_ms": 1_800_000_000_000, "end_exclusive_ms": 1_800_090_000_000},
            {"start_ms": 1_800_172_800_000, "end_exclusive_ms": 1_800_262_800_000},
        ]
        hours = MODULE._hour_starts_for_segments(segments)
        self.assertLessEqual(len(hours), 60)
        self.assertEqual(len(hours), 54)


if __name__ == "__main__":
    unittest.main()
