import random
import unittest
from unittest.mock import patch

from modules.lfs_v2 import (
    WEIGHTS, bb_squeeze_score, calculate_lfs_v2, empirical_percentile,
    funding_extreme_score, get_lfs_veto, normalize_lfs1, oi_drop_score,
    rank_time_series,
)
from modules.lrt15m_engine import evaluate_stage1_symbol


def make_bars(count, interval_ms, base=100.0):
    rows = []
    for i in range(count):
        close = base + 0.15 * i + 1.7 * ((i % 19) - 9) / 9
        rows.append({
            "open_time": i * interval_ms,
            "open": close - 0.2, "high": close + 1.0 + (i % 5) * 0.02,
            "low": close - 1.0 - (i % 7) * 0.02, "close": close,
            "volume": 80.0 + (i % 31) * 3.0,
            "data_source": "MOCK",
        })
    return rows


def oi_rows(hourly=False, change=-0.10, end_ts_ms=None):
    step = 3_600_000 if hourly else 86_400_000
    count = 25 if hourly else 91
    end_ts_ms = 0 if end_ts_ms is None else int(end_ts_ms)
    start_ts_ms = end_ts_ms - (count - 1) * step
    rows = []
    for i in range(count):
        value = 1000.0
        if i == count - 1:
            value = 1000.0 * (1.0 + change)
        rows.append([str(start_ts_ms + i * step), str(value), "0"])
    return rows


class BarsWithMetrics(list):
    def __init__(self, rows, stats_1h, okx_metrics=None):
        super().__init__(rows)
        self.stats_1h = stats_1h
        self.okx_metrics = okx_metrics or {}


class LFSV2UnitTests(unittest.TestCase):
    def setUp(self):
        self.bars_15m = make_bars(500, 900_000)
        self.bars_1h = make_bars(2500, 3_600_000)

    def test_lfs1_normalization(self):
        self.assertAlmostEqual(normalize_lfs1(0.05, 0.02, 0.10), 0.375)

    def test_lfs1_current_uses_same_1h_distribution_as_history(self):
        with patch(
            "modules.lfs_v2._hourly_lfs1_distribution",
            return_value=([0.10, 0.20, 0.30], 100.0),
        ):
            with patch(
                "modules.lfs_v2._hourly_bb_distribution",
                return_value=[0.01, 0.02, 0.03],
            ):
                result = calculate_lfs_v2(
                    "BTCUSDT", self.bars_15m, self.bars_1h,
                    funding_rate=0.0001,
                    oi_1h=oi_rows(hourly=True, change=-0.10),
                    oi_1d=oi_rows(hourly=False, change=0.02),
                    long_short_ratio=1.2,
                )
        component = result["lfs_components"]["LFS1"]
        self.assertAlmostEqual(component["value"], 0.30)
        self.assertEqual(component["historical_timeframe"], "1H")
        self.assertEqual(component["current_timeframe"], "1H")
        self.assertEqual(component["history_observations"], 3)

    def test_lfs4_current_uses_1h_not_15m_bars(self):
        with patch(
            "modules.lfs_v2._hourly_lfs1_distribution",
            return_value=([0.10, 0.20, 0.30], 100.0),
        ):
            with patch(
                "modules.lfs_v2._hourly_bb_distribution",
                return_value=[0.01, 0.02, 0.03],
            ):
                with patch("modules.lfs_v2._bb_width_last", return_value=0.025) as bb_last:
                    result = calculate_lfs_v2(
                        "BTCUSDT", self.bars_15m, self.bars_1h,
                        funding_rate=0.0001,
                        oi_1h=oi_rows(hourly=True, change=-0.10),
                        oi_1d=oi_rows(hourly=False, change=0.02),
                        long_short_ratio=1.2,
                    )
        bb_last.assert_called_once_with(self.bars_1h)
        component = result["lfs_components"]["LFS4"]
        self.assertAlmostEqual(component["value"], 0.025)
        self.assertEqual(component["historical_timeframe"], "1H")
        self.assertEqual(component["current_timeframe"], "1H")

    def test_lfs2_extreme_funding(self):
        self.assertEqual(funding_extreme_score(0.0006), 1.0)

    def test_lfs3_time_series_rank(self):
        history = [i / 1000 for i in range(1, 91)]
        self.assertAlmostEqual(rank_time_series(0.081, history), 0.90)

    def test_lfs4_squeeze(self):
        self.assertEqual(bb_squeeze_score(0.02, 0.03, 0.04), 1.0)

    def test_lfs5_oi_drop(self):
        self.assertEqual(oi_drop_score(-0.10), 1.0)
        self.assertEqual(oi_drop_score(-0.05), 0.5)

    def test_lfs_v2_full_data(self):
        result = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=0.0001,
            oi_1h=oi_rows(hourly=True, change=-0.10),
            oi_1d=oi_rows(hourly=False, change=0.02),
            long_short_ratio=1.2,
        )
        self.assertEqual(result["lfs_coverage_pct"], 100.0)
        self.assertEqual(result["lfs_status"], "FULL")

    def test_lfs_v2_partial_okx(self):
        result = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=None,
            oi_1h=oi_rows(hourly=True, change=-0.05),
            oi_1d=oi_rows(hourly=False, change=0.02),
            long_short_ratio=1.2,
        )
        self.assertEqual(result["lfs_coverage_pct"], 80.0)
        self.assertEqual(result["lfs_status"], "FULL")
        self.assertEqual(result["lfs_components"]["LFS2"]["status"], "UNAVAILABLE")

    def test_lfs_v2_insufficient(self):
        """فقط LFS1 و LFS2 در دسترس‌اند: پوشش 0.25 + 0.20 = 0.45."""
        with patch("modules.lfs_v2._hourly_bb_distribution", return_value=[]):
            result = calculate_lfs_v2(
                "BTCUSDT", self.bars_15m, self.bars_1h,
                funding_rate=0.0003,
                oi_1h=None, oi_1d=None, long_short_ratio=None,
            )
        self.assertIsNotNone(result["lfs_components"]["LFS1"]["score"])
        self.assertIsNotNone(result["lfs_components"]["LFS2"]["score"])
        self.assertEqual(result["lfs_coverage_pct"], 45.0)
        self.assertEqual(result["lfs_status"], "PARTIAL_PROXY")
        self.assertGreaterEqual(result["lfs_coverage_pct"], 40.0)
        self.assertLess(result["lfs_coverage_pct"], 80.0)

    def test_lfs_v2_truly_insufficient(self):
        """فقط LFS1 در دسترس است: پوشش 0.25 و امتیاز قابل استفاده ندارد."""
        with patch("modules.lfs_v2._hourly_bb_distribution", return_value=[]):
            result = calculate_lfs_v2(
                "BTCUSDT", self.bars_15m, self.bars_1h,
                funding_rate=None,
                oi_1h=None, oi_1d=None, long_short_ratio=None,
            )
        self.assertIsNotNone(result["lfs_components"]["LFS1"]["score"])
        self.assertTrue(all(
            result["lfs_components"][name]["score"] is None
            for name in ("LFS2", "LFS3", "LFS4", "LFS5")
        ))
        self.assertEqual(result["lfs_status"], "INSUFFICIENT")
        self.assertIsNone(result["lfs_score"])
        self.assertLess(result["lfs_coverage_pct"], 40.0)

    def test_stage1_rejects_nonfinite_15m_ohlcv(self):
        rows = BarsWithMetrics(self.bars_15m, self.bars_1h)
        rows[100]["close"] = float("nan")
        result = evaluate_stage1_symbol("BTCUSDT", rows)
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["reason"], "INVALID_OHLC")

    def test_stage1_rejects_nonfinite_1h_ohlcv(self):
        rows = BarsWithMetrics(self.bars_15m, self.bars_1h)
        rows.stats_1h[100]["close"] = float("inf")
        result = evaluate_stage1_symbol("BTCUSDT", rows)
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["reason"], "DATA_INSUFFICIENT_1H_INVALID_OHLC")

    def test_stage1_rejects_gaps_in_full_historical_1h_lfs_window(self):
        rows = BarsWithMetrics(self.bars_15m, self.bars_1h)
        rows.stats_1h[500]["open_time"] += 3_600_000
        result = evaluate_stage1_symbol("BTCUSDT", rows)
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["reason"], "DATA_INSUFFICIENT_1H_HISTORY_GAP")

    def test_stage1_stops_safely_on_insufficient_lfs_v2(self):
        rows = BarsWithMetrics(self.bars_15m, self.bars_1h)
        with patch("modules.lfs_v2._hourly_bb_distribution", return_value=[]):
            result = evaluate_stage1_symbol("BTCUSDT", rows)
        self.assertEqual(result["lfs_status"], "INSUFFICIENT")
        self.assertIsNone(result["lfs_score"])
        self.assertEqual(result["veto"], "LFS_INSUFFICIENT_COVERAGE")
        self.assertEqual(result["decision"], "NO_TRADE")

    def test_api_status_rejects_nonfinite_funding_and_invalid_ratio(self):
        result = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=float("nan"),
            oi_1h=None, oi_1d=None, long_short_ratio=float("inf"),
        )
        self.assertFalse(result["api_status"]["funding"])
        self.assertFalse(result["api_status"]["long_short_ratio"])

    def test_live_derivative_components_require_fresh_source_timestamps(self):
        as_of = self.bars_1h[-1]["open_time"] + 3_600_000
        fresh = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=0.0001,
            oi_1h=oi_rows(hourly=True, change=-0.10, end_ts_ms=as_of),
            oi_1d=oi_rows(hourly=False, change=0.02, end_ts_ms=as_of),
            long_short_ratio=1.2,
            as_of_time_ms=as_of,
            funding_received_at_ms=as_of,
            long_short_ratio_timestamp_ms=as_of,
        )
        self.assertTrue(all(fresh["api_status"][key] for key in (
            "funding", "oi_1h", "oi_1d", "long_short_ratio"
        )))

        stale = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=0.0001,
            oi_1h=oi_rows(hourly=True, change=-0.10),
            oi_1d=oi_rows(hourly=False, change=0.02),
            long_short_ratio=1.2,
            as_of_time_ms=as_of,
            funding_received_at_ms=as_of - 10 * 60 * 1000,
            long_short_ratio_timestamp_ms=as_of - 3 * 60 * 60 * 1000,
        )
        self.assertFalse(any(stale["api_status"].values()))
        self.assertEqual(stale["lfs_components"]["LFS2"]["status"], "UNAVAILABLE")
        self.assertEqual(stale["lfs_components"]["LFS3"]["status"], "UNAVAILABLE")
        self.assertEqual(stale["lfs_components"]["LFS5"]["status"], "UNAVAILABLE")
        self.assertEqual(stale["lfs_status"], "PARTIAL_PROXY")

    def test_lfs_v2_bounded(self):
        rng = random.Random(17)
        for _ in range(100):
            funding = rng.uniform(-1.0, 1.0)
            ratio = rng.uniform(0.01, 5.0)
            result = calculate_lfs_v2(
                "ETHUSDT", self.bars_15m, self.bars_1h,
                funding_rate=funding,
                oi_1h=oi_rows(hourly=True, change=rng.uniform(-2.0, 2.0)),
                oi_1d=oi_rows(hourly=False, change=rng.uniform(-2.0, 2.0)),
                long_short_ratio=ratio,
            )
            self.assertGreaterEqual(result["lfs_score"], 0.0)
            self.assertLessEqual(result["lfs_score"], 1.0)
            for component in result["lfs_components"].values():
                if component["score"] is not None:
                    self.assertGreaterEqual(component["score"], 0.0)
                    self.assertLessEqual(component["score"], 1.0)

    def test_lfs_v2_veto(self):
        self.assertEqual(get_lfs_veto(0.25, 100.0), "LFS_BELOW_THRESHOLD")
        self.assertEqual(get_lfs_veto(0.80, 39.9), "LFS_INSUFFICIENT_COVERAGE")

    def test_weights_are_fixed_and_not_redistributed(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0)
        result = calculate_lfs_v2(
            "SOLUSDT", self.bars_15m, self.bars_1h,
            funding_rate=None, oi_1h=None, oi_1d=None, long_short_ratio=None,
        )
        self.assertAlmostEqual(
            result["lfs_score"],
            sum(
                item["score"] * item["weight"]
                for item in result["lfs_components"].values()
                if item["score"] is not None
            ),
        )


if __name__ == "__main__":
    unittest.main()
