"""آزمون‌های قطعی نرمال‌سازی Parquet پانزده‌دقیقه‌ای."""
from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.deduplicate_lrt15m_parquet import normalize


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def bar(ts: int, close: float = 101.0, source: str = "BINANCE_VISION_KLINES") -> dict:
    return {
        "open_time": ts, "open": 100.0, "high": max(102.0, close),
        "low": 99.0, "close": close, "volume": 10.0,
        "data_source": source, "cvd_source": "PROXY",
    }


class Lrt15mDedupTests(unittest.TestCase):
    def test_identical_duplicate_rows_are_reduced_to_one_and_raw_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw"
            output = root / "normalized"
            report = root / "report.json"
            row = bar(1_800_000)
            write_rows(source / "BTCUSDT_15m_2024-01-01_2024-02-01.parquet", [row])
            write_rows(source / "BTCUSDT_15m_2024-01-01_2024-02-01_copy.parquet", [row])

            result = normalize(source, output, report, expected_symbols=1)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["input_rows"], 2)
            self.assertEqual(result["unique_rows"], 1)
            self.assertEqual(result["exact_duplicate_rows_removed"], 1)
            self.assertEqual(len(list(source.glob("*.parquet"))), 2)
            normalized = pq.read_table(output / "BTCUSDT_15m_deduplicated.parquet").to_pylist()
            self.assertEqual(len(normalized), 1)

    def test_conflicting_ohlcv_is_reported_and_fails_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw"
            output = root / "normalized"
            report = root / "report.json"
            write_rows(source / "ETHUSDT_15m_a.parquet", [bar(2_700_000, 101.0)])
            write_rows(source / "ETHUSDT_15m_b.parquet", [bar(2_700_000, 103.0)])

            with self.assertRaisesRegex(ValueError, "CONFLICTING_OHLCV"):
                normalize(source, output, report, expected_symbols=1)

            self.assertFalse(output.exists())
            self.assertEqual(report.exists(), True)
            self.assertIn("FAIL_CONFLICTING_OHLCV", report.read_text(encoding="utf-8"))

    def test_non_aligned_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw"
            write_rows(source / "BTCUSDT_15m_a.parquet", [bar(1_800_001)])
            with self.assertRaisesRegex(ValueError, "INVALID_15M_TIMESTAMP"):
                normalize(source, root / "normalized", root / "report.json", expected_symbols=1)

    def test_symbol_coverage_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "raw"
            write_rows(source / "BTCUSDT_15m_a.parquet", [bar(1_800_000)])
            with self.assertRaisesRegex(ValueError, "SYMBOL_COVERAGE_FAIL"):
                normalize(source, root / "normalized", root / "report.json", expected_symbols=27)


if __name__ == "__main__":
    unittest.main()
