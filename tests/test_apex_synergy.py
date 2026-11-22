from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_apex_synergy as apex


class ApexSynergyTests(unittest.TestCase):
    def test_real_source_artifacts_have_full_expected_coverage(self):
        ohlcv, deriv, meta = apex.load_inputs()
        self.assertEqual(len(ohlcv), 25)
        self.assertEqual(len(deriv), 25)
        for symbol in apex.SYMBOLS:
            self.assertEqual(len(ohlcv[symbol]), 730)
            self.assertEqual(len(deriv[symbol]["metrics"]), 730)
            self.assertTrue(ohlcv[symbol].index.is_monotonic_increasing)
        self.assertEqual(meta["ohlcv_manifest"]["overall_status"], "PASS")
        self.assertEqual(meta["derivatives_manifest"]["overall_status"], "PASS")

    def test_derivatives_are_lagged_and_missing_values_are_not_zero_filled(self):
        _, deriv, _ = apex.load_inputs()
        m = deriv["BTCUSDT"]["metrics"]
        self.assertTrue(pd.isna(m.iloc[0]["sum_open_interest_value"]))
        self.assertTrue(pd.notna(m.iloc[1]["sum_open_interest_value"]))
        one = deriv["ONEUSDT"]["metrics"]
        self.assertGreaterEqual(int(one["sum_taker_long_short_vol_ratio"].isna().sum()), 1)

    def test_features_are_causal_under_future_data_extension(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
        rng = np.random.default_rng(7)
        close = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, len(idx)))
        x = pd.DataFrame({
            "open": close * (1 + rng.normal(0, 0.003, len(idx))),
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": rng.lognormal(10, 0.3, len(idx)),
        }, index=idx)
        x["high"] = x[["open", "high", "close"]].max(axis=1)
        x["low"] = x[["open", "low", "close"]].min(axis=1)
        d = pd.DataFrame({
            "sum_open_interest_value": np.linspace(1e8, 2e8, len(idx)),
            "count_long_short_ratio": np.linspace(0.8, 1.2, len(idx)),
            "sum_toptrader_long_short_ratio": np.linspace(0.9, 1.1, len(idx)),
            "sum_taker_long_short_vol_ratio": np.linspace(0.7, 1.3, len(idx)),
            "funding_daily_sum": np.linspace(-0.001, 0.001, len(idx)),
        }, index=idx)
        full = apex.build_features("TEST", x, {"metrics": d})
        cut = apex.build_features("TEST", x.iloc[:75], {"metrics": d.iloc[:75]})
        cols = [
            "atr", "adx", "momentum_20d", "momentum_60d", "relative_volume",
            "bos", "liquidity_sweep", "fvg_direction", "order_block_score",
            "market_structure", "oi_change_5d", "funding_daily_sum",
        ]
        pd.testing.assert_frame_equal(full[cols].iloc[:75], cut[cols], check_exact=False, rtol=1e-12, atol=1e-12)

    def test_order_block_proxy_is_bounded(self):
        idx = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
        close = pd.Series(np.linspace(100, 130, len(idx)) + np.sin(np.arange(len(idx))) * 2, index=idx)
        x = pd.DataFrame({
            "open": close * 0.999,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": 1000.0,
        }, index=idx)
        x["high"] = x[["open", "high", "close"]].max(axis=1)
        x["low"] = x[["open", "low", "close"]].min(axis=1)
        d = pd.DataFrame(index=idx, data={
            "sum_open_interest_value": 1.0,
            "count_long_short_ratio": 1.0,
            "sum_toptrader_long_short_ratio": 1.0,
            "sum_taker_long_short_vol_ratio": 1.0,
            "funding_daily_sum": 0.0,
        })
        f = apex.build_features("TEST", x, {"metrics": d})
        self.assertTrue(f["order_block_score"].between(-1, 1).all())

    def test_fractional_kelly_is_conservative_and_warmup_is_explicit(self):
        warmup, mode = apex._kelly_risk([0.01, -0.005] * 14 + [0.01])
        self.assertEqual(mode, "WARMUP_FIXED_RISK")
        self.assertEqual(warmup, apex.BASE_RISK_BUDGET)
        risk, mode = apex._kelly_risk([0.02] * 20 + [-0.01] * 10)
        self.assertEqual(mode, "FRACTIONAL_KELLY")
        self.assertGreaterEqual(risk, 0.0)
        self.assertLessEqual(risk, apex.BASE_RISK_BUDGET)
        self.assertLessEqual(risk, 0.25 * (2 / 3 - (1 / 3) / 2))

    def test_walk_forward_uses_unique_monthly_scoring_windows(self):
        idx = pd.date_range("2024-11-01", "2026-10-31", freq="D", tz="UTC")
        folds = apex.make_walk_forward(idx)
        scored = [(f["test_start"], f["scored_end"]) for f in folds]
        self.assertGreaterEqual(len(folds), 12)
        for left, right in zip(scored, scored[1:]):
            self.assertEqual(left[1], right[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
