import random
import unittest

from modules.lfs_v2 import (
    WEIGHTS, bb_squeeze_score, calculate_lfs_v2, empirical_percentile,
    funding_extreme_score, get_lfs_veto, normalize_lfs1, oi_drop_score,
    rank_time_series,
)


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


def oi_rows(hourly=False, change=-0.10):
    step = 3_600_000 if hourly else 86_400_000
    count = 25 if hourly else 91
    rows = []
    for i in range(count):
        value = 1000.0
        if i == count - 1:
            value = 1000.0 * (1.0 + change)
        rows.append([str(i * step), str(value), "0"])
    return rows


class LFSV2UnitTests(unittest.TestCase):
    def setUp(self):
        self.bars_15m = make_bars(500, 900_000)
        self.bars_1h = make_bars(2500, 3_600_000)

    def test_lfs1_normalization(self):
        self.assertAlmostEqual(normalize_lfs1(0.05, 0.02, 0.10), 0.375)

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

    def test_lfs_v2_no_okx(self):
        result = calculate_lfs_v2(
            "BTCUSDT", self.bars_15m, self.bars_1h,
            funding_rate=None, oi_1h=None, oi_1d=None, long_short_ratio=None,
        )
        self.assertEqual(result["lfs_coverage_pct"], 45.0)
        self.assertEqual(result["lfs_status"], "PARTIAL_PROXY")
        self.assertLessEqual(result["lfs_score"], 0.45)

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
