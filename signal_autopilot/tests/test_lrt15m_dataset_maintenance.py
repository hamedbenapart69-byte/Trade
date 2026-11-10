"""آزمون‌های نگهداری افزایشی و تازگی دادهٔ LRT-15m."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import importlib.util

_module_path = Path(__file__).resolve().parents[1] / "scripts" / "maintain_lrt15m_dataset.py"
_spec = importlib.util.spec_from_file_location("maintain_lrt15m_dataset", _module_path)
_maintenance = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_maintenance)

INTERVAL_MS = _maintenance.INTERVAL_MS
EXPECTED_ROWS = _maintenance.EXPECTED_ROWS
_fetch_symbol_tail = _maintenance._fetch_symbol_tail
_merge_rows = _maintenance._merge_rows
_tail_partition_path = _maintenance._tail_partition_path
freshness_state = _maintenance.freshness_state
migrate_legacy_snapshots = _maintenance.migrate_legacy_snapshots
build_dataset_manifest = _maintenance.build_dataset_manifest
maintain_dataset = _maintenance.maintain_dataset
_missing_baseline_result = _maintenance._missing_baseline_result


def write_timestamps(path: Path, timestamps: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([
        {"open_time": ts, "open": 100.0, "high": 102.0, "low": 99.0,
         "close": 101.0, "volume": 10.0}
        for ts in timestamps
    ]), path)


class FreshnessGateTests(unittest.TestCase):
    def test_closed_candle_within_limit_is_fresh(self):
        last_open = 100 * INTERVAL_MS
        now = last_open + INTERVAL_MS + 3 * 60_000
        result = freshness_state(last_open, now, max_age_minutes=30)
        self.assertTrue(result["fresh"])
        self.assertEqual(result["age_minutes"], 3.0)

    def test_stale_candle_is_not_fresh(self):
        last_open = 100 * INTERVAL_MS
        now = last_open + INTERVAL_MS + 31 * 60_000
        result = freshness_state(last_open, now, max_age_minutes=30)
        self.assertFalse(result["fresh"])
        self.assertEqual(result["age_minutes"], 31.0)

    def test_missing_or_discontinuous_candle_is_not_fresh(self):
        self.assertFalse(freshness_state(None, 100 * INTERVAL_MS)["fresh"])
        self.assertFalse(freshness_state(100 * INTERVAL_MS, 100 * INTERVAL_MS + INTERVAL_MS,
                                         continuity=False)["fresh"])


class TailCollectorTests(unittest.TestCase):
    def test_okx_primary_and_mexc_fallback_only_keep_closed_expected_bars(self):
        start = 98 * INTERVAL_MS
        end = 100 * INTERVAL_MS
        now = end + 5 * 60_000

        class FakeDownloader:
            @staticmethod
            def fetch_okx_history_15m(symbol, start_ms, end_ms):
                return {start: {"close": 10, "data_source": "OKX"}}, "OKX_OK"

            @staticmethod
            def fetch_mexc_futures_15m(symbol, start_ms, end_ms):
                return {
                    start + INTERVAL_MS: {"close": 11, "data_source": "MEXC"},
                    end: {"close": 12, "data_source": "MEXC_OPEN"},
                }, "MEXC_OK"

        bars, status = _fetch_symbol_tail("BTCUSDT", start, end, now, FakeDownloader)
        self.assertEqual(set(bars), {start, start + INTERVAL_MS})
        self.assertEqual(status["expected_bars"], "2")
        self.assertEqual(status["received_bars"], "2")
        self.assertEqual(status["missing_bars"], "0")
        self.assertNotIn(end, bars)

    def test_merge_is_timestamp_unique_and_later_group_wins(self):
        rows = _merge_rows(
            [{"open_time": 1, "close": 10}, {"open_time": 2, "close": 20}],
            [{"open_time": 2, "close": 21}, {"open_time": 3, "close": 30}],
        )
        self.assertEqual([x["open_time"] for x in rows], [1, 2, 3])
        self.assertEqual(rows[1]["close"], 21)

    def test_tail_partition_uses_utc_day(self):
        end = int(datetime(2026, 1, 1, 17, 15, tzinfo=timezone.utc).timestamp() * 1000)
        path = _tail_partition_path(Path("/tmp/data"), "BTCUSDT", end)
        self.assertEqual(path.parts[-2:], ("2026-01-01", "BTCUSDT_15m.parquet"))


class BaselineMigrationTests(unittest.TestCase):
    def test_migrates_latest_snapshot_and_removes_duplicate_legacy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "BTCUSDT_15m_2024-11-09_2026-11-09.parquet"
            newer = root / "BTCUSDT_15m_2024-11-10_2026-11-10.parquet"
            timestamps = list(range(0, EXPECTED_ROWS * INTERVAL_MS, INTERVAL_MS))
            write_timestamps(older, timestamps)
            write_timestamps(newer, [x + INTERVAL_MS for x in timestamps])

            result = migrate_legacy_snapshots(root, ["BTCUSDT"])
            base = root / "base" / "BTCUSDT_15m.parquet"
            self.assertTrue(base.exists())
            self.assertTrue(result["validation"]["BTCUSDT"]["valid"])
            self.assertEqual(result["validation"]["BTCUSDT"]["first_open_ms"], INTERVAL_MS)
            self.assertFalse(older.exists())
            self.assertFalse(newer.exists())
            self.assertEqual(len(result["removed_legacy_files"]), 2)

    def test_replaces_invalid_existing_baseline_with_latest_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base" / "BTCUSDT_15m.parquet"
            write_timestamps(base, [0, INTERVAL_MS])
            latest = root / "BTCUSDT_15m_2024-11-10_2026-11-10.parquet"
            timestamps = list(range(0, EXPECTED_ROWS * INTERVAL_MS, INTERVAL_MS))
            write_timestamps(latest, timestamps)

            result = migrate_legacy_snapshots(root, ["BTCUSDT"])
            self.assertTrue(result["validation"]["BTCUSDT"]["valid"])
            self.assertEqual(result["validation"]["BTCUSDT"]["rows"], EXPECTED_ROWS)
            self.assertFalse(latest.exists())




    def test_falls_back_to_older_valid_snapshot_when_newest_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            older = root / "BTCUSDT_15m_2024-11-09_2026-11-09.parquet"
            newer = root / "BTCUSDT_15m_2024-11-10_2026-11-10.parquet"
            timestamps = list(range(0, EXPECTED_ROWS * INTERVAL_MS, INTERVAL_MS))
            write_timestamps(older, timestamps)
            bad_rows = [
                {"open_time": ts, "open": 100.0, "high": 102.0, "low": 99.0,
                 "close": 101.0, "volume": 10.0}
                for ts in timestamps
            ]
            bad_rows[0]["high"] = 98.0
            pq.write_table(pa.Table.from_pylist(bad_rows), newer)

            result = migrate_legacy_snapshots(root, ["BTCUSDT"])
            self.assertTrue(result["validation"]["BTCUSDT"]["valid"])
            self.assertEqual(result["validation"]["BTCUSDT"]["first_open_ms"], 0)
            self.assertTrue((root / "base" / "BTCUSDT_15m.parquet").exists())

    def test_rejects_duplicate_timestamp_inside_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.parquet"
            write_timestamps(path, [0, INTERVAL_MS, INTERVAL_MS])
            valid, _, _, _, reason = _maintenance._validate_baseline(path)
            self.assertFalse(valid)
            self.assertEqual(reason, "BASELINE_DUPLICATE_TIMESTAMPS")

    def test_rejects_invalid_ohlc_relationship(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "baseline.parquet"
            write_timestamps(path, [0])
            rows = _read_rows_for_test(path)
            rows[0]["high"] = 98.0
            pq.write_table(pa.Table.from_pylist(rows), path)
            valid, _, _, _, reason = _maintenance._validate_baseline(path)
            self.assertFalse(valid)
            self.assertEqual(reason, "BASELINE_OHLC_RELATION:row=0")


class P0DataOnlyAndManifestTests(unittest.TestCase):
    def test_data_only_does_not_trigger_full_backfill_or_signal_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "storage"
            universe = root / "universe.json"
            symbols = [f"COIN{i:02d}USDT" for i in range(27)]
            universe.write_text(json.dumps({"symbols": symbols}), encoding="utf-8")
            class NoBackfillDownloader:
                def run(self, *args, **kwargs):
                    raise AssertionError("full backfill must not run in P0 data-only mode")

            report = maintain_dataset(
                storage, root / "compute", root / "report.json",
                root / "signals.json", universe, now_ms=2_000_000_000_000,
                downloader=NoBackfillDownloader(), data_only=True,
            )
            self.assertEqual(report["status"], "DEGRADED")
            self.assertFalse((root / "signals.json").exists())
            self.assertTrue((root / "report.json").exists())

    def test_manifest_hashes_27_baselines_and_tail_without_signal_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storage = root / "storage"
            base = storage / "base"
            original_expected = _maintenance.EXPECTED_ROWS
            _maintenance.EXPECTED_ROWS = 2
            try:
                symbols = [f"COIN{i:02d}USDT" for i in range(27)]
                for symbol in symbols:
                    write_timestamps(base / f"{symbol}_15m.parquet", [0, INTERVAL_MS])
                tail_row = {
                    "open_time": 2 * INTERVAL_MS, "open": 101.0, "high": 103.0,
                    "low": 100.0, "close": 102.0, "volume": 5.0,
                }
                write_timestamps(storage / "live_tail" / "2026-01-01" / "COIN00USDT_15m.parquet",
                                 [2 * INTERVAL_MS])
                report_path = root / "data_report.json"
                report_path.write_text(json.dumps({"status": "DEGRADED"}), encoding="utf-8")

                manifest = build_dataset_manifest(
                    storage, report_path, root / "manifest.json",
                    "workflow-sha", "engine-sha", "12345", "legacy-sha",
                )
                self.assertEqual(manifest["symbols_count"], 27)
                self.assertEqual(manifest["baseline_files_count"], 27)
                self.assertEqual(manifest["live_tail_files_count"], 1)
                self.assertEqual(len(manifest["dataset_sha256"]), 64)
                self.assertFalse(manifest["signal_engine_executed"])
                self.assertEqual(manifest["data_gate_status"], "DEGRADED")
            finally:
                _maintenance.EXPECTED_ROWS = original_expected


def _read_rows_for_test(path: Path) -> list[dict]:
    return pq.read_table(path).to_pylist()


class MissingBaselineContractTests(unittest.TestCase):
    def test_missing_baseline_returns_all_four_worker_fields(self):
        symbol, bars, status, ephemeral = _missing_baseline_result("BTCUSDT")
        self.assertEqual(symbol, "BTCUSDT")
        self.assertEqual(bars, {})
        self.assertEqual(status, {"status": "BASELINE_MISSING"})
        self.assertEqual(ephemeral, {})


if __name__ == "__main__":
    unittest.main()
