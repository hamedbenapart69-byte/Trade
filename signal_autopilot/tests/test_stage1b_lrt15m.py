import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules"))
import lrt15m_engine as engine


def candle(ts, open_, high, low, close, volume=100.0, buy=55.0):
    return {
        "open_time": ts, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume, "taker_buy_base": buy,
    }


def create_mock_bars_with_sweep_at(candles_ago: int, total: int) -> list[dict]:
    bars = [candle(i * 900000, 100, 102, 99, 101) for i in range(total)]
    index = total - 1 - candles_ago
    if index < 20:
        raise ValueError("mock sweep needs 20 reference candles")
    bars[index] = candle(index * 900000, 100, 102, 98, 100.5)
    return bars


def create_mock_bars_with_small_fvg(gap_atr: float) -> list[dict]:
    bars = [candle(i * 900000, 100, 100.5, 99.5, 100) for i in range(20)]
    bars[-3] = candle(17 * 900000, 100, 100, 99.8, 100)
    bars[-2] = candle(18 * 900000, 100, 100.1, 99.9, 100)
    bars[-1] = candle(19 * 900000, 100.1, 100.5, 100 + gap_atr, 100.3)
    return bars


class LRT15mTests(unittest.TestCase):
    def test_higher_timeframe_conflict_is_watchlist_not_trade(self):
        confirmed, state = engine.higher_timeframe_gate("BUY", "BEARISH", "BULLISH")
        self.assertFalse(confirmed)
        self.assertEqual(state, "WATCHLIST_4H_KUMO_OPPOSITE")

    def test_higher_timeframe_alignment_is_confirmed(self):
        confirmed, state = engine.higher_timeframe_gate("BUY", "BULLISH", "BULLISH")
        self.assertTrue(confirmed)
        self.assertEqual(state, "BIAS_CONFIRMED")

    def test_lfs_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(engine.LFS_WEIGHTS.values()), 1.0)

    def test_detect_sweep_finds_historical_sweep(self):
        """Sweep سه کندل قبل باید در پنجرهٔ جست‌وجو پیدا شود."""
        bars = create_mock_bars_with_sweep_at(candles_ago=3, total=31)
        result = engine.detect_sweep(bars, lookback=20, max_candles_ago=10)
        self.assertTrue(result["bullish"])
        self.assertEqual(result["candles_ago"], 3)

    def test_detect_sweep_no_sweep_in_10_candles(self):
        """Sweep پانزده کندل قبل نباید در پنجرهٔ ده‌کندلی پیدا شود."""
        bars = create_mock_bars_with_sweep_at(candles_ago=15, total=36)
        result = engine.detect_sweep(bars, lookback=20, max_candles_ago=10)
        self.assertFalse(result["bullish"])
        self.assertIsNone(result["candles_ago"])

    def test_zone_distance_fvg_minimum_atr(self):
        """FVG کوچک‌تر از ۰.۳ ATR نباید به‌عنوان Zone ثبت شود."""
        bars = create_mock_bars_with_small_fvg(gap_atr=0.2)
        result = engine.zone_distance(bars, "BUY", atr_value=1.0)
        self.assertNotEqual(result["zone_type"], "FVG")

    def test_bullish_sweep_reclaims_prior_low(self):
        bars = [candle(i * 900000, 100, 102, 99, 101) for i in range(20)]
        bars.append(candle(20 * 900000, 100, 102, 98, 100.5))
        result = engine.detect_sweep(bars)
        self.assertTrue(result["bullish"])
        self.assertFalse(result["bearish"])

    def test_bearish_sweep_rejects_prior_high(self):
        bars = [candle(i * 900000, 100, 102, 99, 101) for i in range(20)]
        bars.append(candle(20 * 900000, 102, 103, 99, 101))
        result = engine.detect_sweep(bars)
        self.assertTrue(result["bearish"])

    def test_bullish_fvg(self):
        bars = [
            candle(0, 100, 101, 99, 100),
            candle(900000, 100, 105, 100, 104),
            candle(1800000, 106, 108, 105, 107),
        ]
        self.assertTrue(engine.detect_fvg(bars, "BUY"))

    def test_aggtrades_cvd_respects_aggressor_side(self):
        trades = [
            {"qty": "2", "m": False},  # buyer aggressor
            {"qty": "1", "m": True},   # seller aggressor
        ]
        self.assertEqual(engine.cvd_delta_from_aggtrades(trades), 1.0)

    def test_kline_cvd_is_explicit_proxy(self):
        bars = [candle(i * 900000, 1, 2, 0.5, 1.5, volume=10, buy=7) for i in range(4)]
        self.assertAlmostEqual(engine.cvd_proxy_from_klines(bars), 13.333333333333329)

    def test_15m_engine_marks_uncalibrated_and_never_fakes_ev(self):
        bars = []
        for i in range(1400):
            base = 100 + i * 0.01
            bars.append(candle(i * 900000, base, base + 0.5, base - 0.5,
                               base + 0.1, volume=100, buy=52))
        result = engine.analyze_symbol("BTCUSDT", bars)
        self.assertEqual(result["confidence"], "NOT_CALIBRATED")
        self.assertEqual(result["brier_score"], "NOT_CALIBRATED")
        self.assertIn("NOT_CALCULATED", result["ev"])
        self.assertEqual(result["ev_status"], "NOT_CALIBRATED")
        self.assertIsNone(result["ev_net"])
        self.assertIn(result["decision"], {"WATCHLIST", "NO_QUALIFIED_SETUP"})

    def test_okx_source_metadata_survives_engine_and_neutralizes_cvd(self):
        bars = []
        for i in range(1400):
            base = 100 + i * 0.01
            bars.append({
                **candle(i * 900000, base, base + 0.5, base - 0.5,
                         base + 0.1, volume=100, buy=50),
                "data_source": "OKX_PUBLIC_SWAP_CANDLE",
                "cvd_source": "OKX_SPOT_CVD_UNAVAILABLE_NEUTRAL_PROXY",
            })
        result = engine.analyze_symbol("BTCUSDT", bars)
        self.assertIn("OKX_PUBLIC_SWAP_CANDLE", result["data_sources"])
        self.assertEqual(result["cvd_source"], "PROXY_OHLCV")
        self.assertEqual(result["decision"], "NO_QUALIFIED_SETUP")

    def test_short_history_is_not_qualified(self):
        result = engine.analyze_symbol("BTCUSDT", [candle(i * 900000, 1, 2, 0.5, 1) for i in range(100)])
        self.assertEqual(result["decision"], "NO_QUALIFIED_SETUP")
        self.assertEqual(result["reason"], "INSUFFICIENT_15M_HISTORY")
        self.assertEqual(result["ev_status"], "NOT_CALIBRATED")
        self.assertIsNone(result["ev_net"])


if __name__ == "__main__":
    unittest.main()
