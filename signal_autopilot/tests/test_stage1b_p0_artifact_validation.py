"""Unit tests for the trusted Stage 1b artifact validator."""
import unittest

from scripts.verify_stage1b_p0_artifact import safe_manifest_path, validate_rows


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


class Stage1bArtifactRowTests(unittest.TestCase):
    def test_rejects_duplicate_or_unsorted_timestamps(self):
        path = safe_manifest_path("live_tail/2026-11-11/BTCUSDT_15m.parquet")
        row = {"open_time": 1_800_000_000_000, "open": 100.0, "high": 102.0,
               "low": 99.0, "close": 101.0, "volume": 10.0}
        with self.assertRaises(ValueError):
            validate_rows([row, row], "BTCUSDT", "LIVE_TAIL", path)

    def test_rejects_non_finite_ohlcv(self):
        path = safe_manifest_path("live_tail/2026-11-11/BTCUSDT_15m.parquet")
        row = {"open_time": 1_800_000_000_000, "open": float("nan"), "high": 102.0,
               "low": 99.0, "close": 101.0, "volume": 10.0}
        with self.assertRaises(ValueError):
            validate_rows([row], "BTCUSDT", "LIVE_TAIL", path)


if __name__ == "__main__":
    unittest.main()
