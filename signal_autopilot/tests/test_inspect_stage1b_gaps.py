"""آزمون‌های آفلاین ممیزی شکاف‌های دادهٔ 15m."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from signal_autopilot.scripts.inspect_stage1b_gaps import (
    INTERVAL_MS,
    group_missing_timestamps,
    inspect_gap,
)


class GapAuditTests(unittest.TestCase):
    def test_groups_adjacent_missing_bars(self):
        gaps = group_missing_timestamps([0, INTERVAL_MS, 3 * INTERVAL_MS])
        self.assertEqual(len(gaps), 2)
        self.assertEqual(gaps[0]["bars"], 2)
        self.assertEqual(gaps[0]["duration_minutes"], 30)
        self.assertEqual(gaps[1]["bars"], 1)


    def test_separates_unpersisted_ephemeral_rows_from_true_compute_gaps(self):
        start = int(datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "lrt15m"
            base = storage / "base" / "FILUSDT_15m.parquet"
            tail = storage / "live_tail" / "2026-11-16" / "FILUSDT_15m.parquet"
            base.parent.mkdir(parents=True)
            tail.parent.mkdir(parents=True)
            base_times = [start + i * INTERVAL_MS for i in range(4)]
            tail_times = [start + i * INTERVAL_MS for i in (5, 6)]
            pq.write_table(pa.table({"open_time": base_times}), base)
            pq.write_table(pa.table({"open_time": tail_times}), tail)
            report_path = root / "data_report.json"
            report_path.write_text(json.dumps({
                "generated_at_utc": "2026-11-16T13:45:00+00:00",
                "symbols": [{
                    "symbol": "FILUSDT",
                    "first_open_ms": start,
                    "last_open_ms": start + 7 * INTERVAL_MS,
                    "rows": 7,
                    "tail_rows": 3,
                    "expected_rows": 8,
                    "gap_count": 1,
                }],
            }), encoding="utf-8")

            result = inspect_gap(storage, report_path, "FILUSDT")
            counts = result["storage_counts"]
            self.assertEqual(counts["persisted_missing_bars"], 2)
            self.assertEqual(counts["inferred_ephemeral_rows"], 1)
            self.assertEqual(counts["compute_input_missing_bars"], 1)
            self.assertEqual(counts["persisted_gap_ranges"], 2)
            self.assertEqual(counts["inferred_ephemeral_gap_ranges"], 1)
            self.assertEqual(counts["compute_input_gap_ranges"], 1)
            self.assertTrue(all(result["consistency_checks"].values()))

    def test_inspects_storage_and_matches_data_report(self):
        start = int(datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "lrt15m"
            base = storage / "base" / "FILUSDT_15m.parquet"
            tail = storage / "live_tail" / "2026-11-16" / "FILUSDT_15m.parquet"
            base.parent.mkdir(parents=True)
            tail.parent.mkdir(parents=True)
            base_times = [start + i * INTERVAL_MS for i in range(4)]
            tail_times = [start + i * INTERVAL_MS for i in (6, 7)]
            pq.write_table(pa.table({"open_time": base_times}), base)
            pq.write_table(pa.table({"open_time": tail_times}), tail)
            report_path = root / "data_report.json"
            report_path.write_text(json.dumps({
                "generated_at_utc": "2026-11-16T13:45:00+00:00",
                "symbols": [{
                    "symbol": "FILUSDT",
                    "first_open_ms": start,
                    "last_open_ms": start + 7 * INTERVAL_MS,
                    "rows": 6,
                    "tail_rows": 2,
                    "expected_rows": 8,
                    "gap_count": 1,
                    "reason": "BASELINE_MISSING_OR_INCOMPLETE",
                    "provider_status": {"mexc": "MEXC_CONTRACT_NOT_LISTED"},
                }],
            }), encoding="utf-8")

            result = inspect_gap(storage, report_path, "FILUSDT")
            self.assertEqual(result["storage_counts"]["missing_bars"], 2)
            self.assertEqual(result["storage_counts"]["gap_ranges"], 1)
            self.assertEqual(result["gap_ranges"][0]["bars"], 2)
            self.assertTrue(all(result["consistency_checks"].values()))
            self.assertFalse(result["raw_price_values_read"])
            self.assertFalse(result["raw_provider_data_downloaded"])


if __name__ == "__main__":
    unittest.main()
