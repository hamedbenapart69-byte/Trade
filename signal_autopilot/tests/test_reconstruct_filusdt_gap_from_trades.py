"""آزمون‌های آفلاین تجمیع معاملات آرشیوی به کندل."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest.mock import patch
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
            {"trade_time": start + 2, "event_time": start + 2, "trade_id": 12, "price": "10.5", "quantity": "2", "order_type": "MARKET"},
            {"trade_time": start + 1, "event_time": start + 1, "trade_id": 11, "price": "10", "quantity": "1", "order_type": "MARKET"},
            {"trade_time": start + 3, "event_time": start + 3, "trade_id": 13, "price": "0", "quantity": "0", "order_type": "NA"},
            {"trade_time": start + INTERVAL_MS + 1, "event_time": start + INTERVAL_MS + 1, "trade_id": 14, "price": "11", "quantity": "3", "order_type": "MARKET"},
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
        self.assertEqual(quality["event_time_mismatch_rows"], 0)
        self.assertEqual(quality["invalid_or_nonpositive_rows"], 0)

    def test_trade_id_quality_counts_duplicates_and_gaps(self):
        rows = [{"trade_id": value, "trade_time": 1_800_000_000_000 + index * 1000} for index, value in enumerate([10, 11, 11, 14, 15])]
        quality = MODULE.trade_id_quality(rows)
        self.assertEqual(quality["trade_id_rows"], 5)
        self.assertEqual(quality["unique_trade_ids"], 4)
        self.assertEqual(quality["duplicate_trade_ids"], 1)
        self.assertEqual(quality["trade_id_gap_intervals"], 1)
        self.assertEqual(quality["missing_trade_ids_estimate"], 2)
        self.assertEqual(len(quality["trade_id_gap_time_ranges"]), 1)
        self.assertEqual(quality["trade_id_gap_time_ranges"][0]["missing_trade_ids_estimate"], 2)

    def test_hour_file_selection_stays_under_anonymous_limit(self):
        segments = [
            {"start_ms": 1_800_000_000_000, "end_exclusive_ms": 1_800_090_000_000},
            {"start_ms": 1_800_172_800_000, "end_exclusive_ms": 1_800_262_800_000},
        ]
        hours = MODULE._hour_starts_for_segments(segments)
        self.assertLessEqual(len(hours), 60)
        self.assertEqual(len(hours), 58)

    def test_binance_vision_archive_comparison_counts_exact_ohlcv(self):
        vision = MODULE._load_vision_audit_module()
        start = 1_800_000_000_000
        end = start + 199 * INTERVAL_MS
        expected_times = list(range(start, end + INTERVAL_MS, INTERVAL_MS))
        fake_rows = {
            ts: {"open": "10", "high": "11", "low": "9", "close": "10.5", "volume": "100"}
            for ts in expected_times
        }
        def fake_daily(date):
            return fake_rows, {"date": date, "checksum_verified": True, "daily_rows": 96, "archive_bytes": 100, "archive_sha256": "a" * 64}
        with patch.object(vision, "inspect_gap", return_value={"compute_input_gap_ranges": [{"first_open_ms": start, "last_open_ms": end}]}), patch.object(vision, "_daily_klines", side_effect=fake_daily):
            result = vision.validate_archive(Path("."), Path("report.json"), None, {
                ts: {"open": "10", "high": "11", "low": "9", "close": "10.5", "volume": "100"}
                for ts in expected_times
            })
        self.assertEqual(result["available_gap_candles"], 200)
        self.assertEqual(result["trade_reconstruction_comparison"]["compared_candles"], 200)
        self.assertEqual(result["trade_reconstruction_comparison"]["exact_ohlcv_candles"], 200)
        self.assertEqual(result["status"], "ARCHIVE_COVERAGE_VERIFIED_RESEARCH_ONLY")

if __name__ == "__main__":
    unittest.main()
