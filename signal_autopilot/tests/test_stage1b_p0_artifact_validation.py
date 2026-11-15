"""Unit tests for the trusted Stage 1b artifact validator."""
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_stage1b_p0_artifact.py"
_SPEC = importlib.util.spec_from_file_location("verify_stage1b_p0_artifact", _SCRIPT)
_VALIDATOR = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_VALIDATOR)
safe_manifest_path = _VALIDATOR.safe_manifest_path
validate_rows = _VALIDATOR.validate_rows
validate_report_freshness = _VALIDATOR.validate_report_freshness
INTERVAL_MS = _VALIDATOR.INTERVAL_MS


class Stage1bArtifactPathTests(unittest.TestCase):
    def test_accepts_only_expected_baseline_and_tail_layouts(self):
        self.assertEqual(safe_manifest_path("base/BTCUSDT_15m.parquet").as_posix(),
                         "base/BTCUSDT_15m.parquet")
        self.assertEqual(safe_manifest_path(
            "live_tail/2026-11-11/BTCUSDT_15m.parquet").parts[0], "live_tail")

    def test_rejects_path_traversal_and_unexpected_directories(self):
        for value in (
            "../outside.parquet",
            "base/../../outside.parquet",
            "/tmp/BTCUSDT_15m.parquet",
            "signals/BTCUSDT_15m.parquet",
            "live_tail/not-a-date/BTCUSDT_15m.parquet",
            "base/nested/BTCUSDT_15m.parquet",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    safe_manifest_path(value)


class Stage1bReportFreshnessTests(unittest.TestCase):
    @staticmethod
    def make_report(generated_ms, completed_ms, timestamps, expected_rows=4):
        closed_end_ms = (completed_ms // INTERVAL_MS) * INTERVAL_MS
        window_start_ms = closed_end_ms - expected_rows * INTERVAL_MS
        actual = sorted(timestamps)
        continuity = (
            len(actual) == expected_rows
            and all(right - left == INTERVAL_MS for left, right in zip(actual, actual[1:]))
        )
        last_open = actual[-1] if actual else None
        first_open = actual[0] if actual else None
        age = round((generated_ms - (last_open + INTERVAL_MS)) / 60_000, 2) if last_open is not None else None
        fresh = bool(continuity and age is not None and -1 <= age <= 30)
        reason = None if fresh else ("BASELINE_MISSING_OR_INCOMPLETE" if not continuity else "LATEST_15M_CANDLE_STALE")
        return {
            "generated_at_utc": datetime.fromtimestamp(generated_ms / 1000, timezone.utc).isoformat(),
            "start_date_utc": datetime.fromtimestamp(window_start_ms / 1000, timezone.utc).date().isoformat(),
            "end_date_exclusive_utc": datetime.fromtimestamp(closed_end_ms / 1000, timezone.utc).isoformat(),
            "interval": "15m",
            "symbols_complete": int(continuity),
            "symbols_fresh": int(fresh),
            "status": "PASS" if continuity and fresh else "DEGRADED",
            "symbols": [{
                "symbol": "BTCUSDT", "rows": len(actual), "expected_rows": expected_rows,
                "continuity": continuity, "first_open_ms": first_open,
                "last_open_ms": last_open, "fresh": fresh, "age_minutes": age,
                "reason": reason,
            }],
        }

    def test_pass_is_recomputed_from_actual_parquet_timestamps(self):
        completed = 5 * INTERVAL_MS + 7 * 60_000
        generated = completed - 2 * 60_000
        closed_end = (completed // INTERVAL_MS) * INTERVAL_MS
        timestamps = set(range(closed_end - 4 * INTERVAL_MS, closed_end, INTERVAL_MS))
        report = self.make_report(generated, completed, timestamps)
        validate_report_freshness(report, ["BTCUSDT"], {"BTCUSDT": timestamps}, completed, expected_rows=4)

    def test_rejects_artifact_claiming_pass_with_stale_candles(self):
        completed = 5 * INTERVAL_MS + 31 * 60_000
        generated = completed
        closed_end = (completed // INTERVAL_MS) * INTERVAL_MS
        timestamps = set(range(closed_end - 4 * INTERVAL_MS, closed_end, INTERVAL_MS))
        report = self.make_report(generated, completed, timestamps)
        report["symbols"][0]["fresh"] = True
        report["symbols"][0]["reason"] = None
        report["symbols_fresh"] = 1
        report["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "DATA_REPORT_SYMBOL_FRESHNESS_MISMATCH"):
            validate_report_freshness(report, ["BTCUSDT"], {"BTCUSDT": timestamps}, completed, expected_rows=4)

    def test_rejects_report_that_became_stale_before_trusted_persistence(self):
        completed = 5 * INTERVAL_MS + 31 * 60_000
        generated = 5 * INTERVAL_MS + 5 * 60_000
        closed_end = 5 * INTERVAL_MS
        timestamps = set(range(closed_end - 4 * INTERVAL_MS, closed_end, INTERVAL_MS))
        report = self.make_report(generated, completed, timestamps)
        with self.assertRaisesRegex(ValueError, "DATA_REPORT_STALE_BEFORE_PERSISTENCE"):
            validate_report_freshness(report, ["BTCUSDT"], {"BTCUSDT": timestamps}, completed, expected_rows=4)

    def test_degraded_report_is_valid_when_window_has_a_gap(self):
        completed = 5 * INTERVAL_MS + 5 * 60_000
        generated = completed
        closed_end = (completed // INTERVAL_MS) * INTERVAL_MS
        timestamps = {
            closed_end - 4 * INTERVAL_MS,
            closed_end - 3 * INTERVAL_MS,
            closed_end - INTERVAL_MS,
        }
        report = self.make_report(generated, completed, timestamps)
        validate_report_freshness(report, ["BTCUSDT"], {"BTCUSDT": timestamps}, completed, expected_rows=4)

    def test_rejects_report_timestamp_older_than_publication_window(self):
        completed = 5 * INTERVAL_MS + 31 * 60_000
        generated = completed - 31 * 60_000
        closed_end = (completed // INTERVAL_MS) * INTERVAL_MS
        timestamps = set(range(closed_end - 4 * INTERVAL_MS, closed_end, INTERVAL_MS))
        report = self.make_report(generated, completed, timestamps)
        with self.assertRaisesRegex(ValueError, "DATA_REPORT_TIMESTAMP_STALE"):
            validate_report_freshness(report, ["BTCUSDT"], {"BTCUSDT": timestamps}, completed, expected_rows=4)


class Stage1bArtifactRowTests(unittest.TestCase):
    def test_rejects_duplicate_or_unsorted_timestamps(self):
        path = safe_manifest_path("live_tail/2026-11-11/BTCUSDT_15m.parquet")
        row = {"open_time": 1_794_355_200_000, "open": 100.0, "high": 102.0,
               "low": 99.0, "close": 101.0, "volume": 10.0}
        with self.assertRaises(ValueError):
            validate_rows([row, row], "BTCUSDT", "LIVE_TAIL", path)

    def test_rejects_non_finite_ohlcv(self):
        path = safe_manifest_path("live_tail/2026-11-11/BTCUSDT_15m.parquet")
        row = {"open_time": 1_794_355_200_000, "open": float("nan"), "high": 102.0,
               "low": 99.0, "close": 101.0, "volume": 10.0}
        with self.assertRaises(ValueError):
            validate_rows([row], "BTCUSDT", "LIVE_TAIL", path)


if __name__ == "__main__":
    unittest.main()
