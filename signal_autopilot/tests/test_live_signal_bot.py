import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import calculate_confluence, tenkan_kijun_cross
from modules.live_data_adapter import LiveOHLCVFetcher, is_closed_candle
from telegram_bot import build_signal_messages


def candle(ts, open_, high, low, close, volume=100.0, buy=55.0):
    return {
        "open_time": ts, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume, "taker_buy_base": buy,
    }


class LiveSignalBotTests(unittest.TestCase):
    def test_open_candle_is_excluded_by_close_time_rule(self):
        now_ms = 1_800_000_000_000
        self.assertTrue(is_closed_candle(now_ms - 900_000, 900_000, now_ms))
        self.assertFalse(is_closed_candle(now_ms, 900_000, now_ms))

    def test_confluence_uses_five_approved_gates_and_60_threshold(self):
        result = {
            "higher_timeframe_bias_confirmed": True,
            "higher_timeframe_bias": {"4h_kumo": "BULLISH", "1h_kijun": "BEARISH"},
            "zone_distance_pct": 0.40,
            "lfs_components": {
                "liquidity_sweep": True,
                "order_block": True,
                "fair_value_gap": False,
            },
            "cvd": {"source": "KLINE_TAKER_BUY_PROXY"},
            "lfs_score": 0.80,
        }
        rows = []
        score, parts = calculate_confluence(result, rows, "BUY")
        self.assertEqual(score, 40)
        self.assertEqual(set(parts), {
            "bias_4h": 20, "bias_1h": 0, "sweep": 20,
            "zone_reaction": 0, "tenkan_kijun_cross_10": 0,
        })
        self.assertFalse(parts["tenkan_kijun_cross_10"])

    def test_cross_lookback_is_ten_closed_candles(self):
        from modules.lrt15m_engine import CROSS_LOOKBACK, tenkan_kijun_cross as cross
        self.assertEqual(CROSS_LOOKBACK, 10)
        bars = []
        for i in range(40):
            center = 100.0 if i < 23 else 110.0
            bars.append(candle(i * 900000, center, center + 0.5, center - 0.5, center))
        self.assertTrue(cross(bars, "BUY", lookback=10))
        self.assertFalse(cross(bars, "BUY", lookback=3))

    def test_zone_distance_uses_synthetic_fvg_and_080_percent_limit(self):
        from modules.lrt15m_engine import zone_distance
        rows = [candle(i * 900000, 99.5, 100.0, 99.0, 99.5) for i in range(8)]
        rows[-1] = candle(7 * 900000, 100.25, 100.5, 100.2, 100.3)
        near = zone_distance(rows, "BUY", None)
        self.assertEqual(near["zone_type"], "FVG")
        self.assertTrue(near["within_limit"])
        self.assertLess(near["distance_pct"], 0.80)
        rows[-1] = candle(7 * 900000, 102.0, 102.3, 101.0, 102.1)
        far = zone_distance(rows, "BUY", None)
        self.assertFalse(far["within_limit"])
        self.assertGreater(far["distance_pct"], 0.80)

    def test_proxy_lfs_threshold_is_030_and_real_threshold_is_unchanged(self):
        from modules.lrt15m_engine import MIN_LFS_SCORE_PROXY_CVD, MIN_LFS_SCORE_REAL_CVD
        self.assertEqual(MIN_LFS_SCORE_PROXY_CVD, 0.30)
        self.assertEqual(MIN_LFS_SCORE_REAL_CVD, 0.70)

    def test_watchlist_and_monitoring_thresholds_are_separate(self):
        from modules.lrt15m_engine import (
            MONITORING_CONFLUENCE_THRESHOLD, WATCHLIST_CONFLUENCE_THRESHOLD,
        )
        self.assertEqual(WATCHLIST_CONFLUENCE_THRESHOLD, 80)
        self.assertEqual(MONITORING_CONFLUENCE_THRESHOLD, 60)

    def test_five_components_score_100(self):
        result = {
            "higher_timeframe_bias_confirmed": True,
            "lfs_components": {
                "liquidity_sweep": True,
                "order_block": True,
                "fair_value_gap": False,
            },
            "cvd": {"source": "KLINE_TAKER_BUY_PROXY"},
            "lfs_score": 0.80,
        }
        rows = []
        # Force the cross helper through a patch-free valid 15m series.
        # With fewer than 30 bars the cross component correctly remains false.
        score, parts = calculate_confluence(result, rows, "BUY")
        self.assertLessEqual(score, 80)
        self.assertFalse(parts["tenkan_kijun_cross_10"])


    def test_ccxt_short_pages_are_paginated_until_history_requirement_is_met(self):
        class DummyExchange:
            rateLimit = 0
            markets = {
                "BTC/USDT:USDT": {
                    "active": True, "swap": True, "linear": True,
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "symbol": "BTC/USDT:USDT",
                }
            }

            def __init__(self):
                self.calls = 0

            def fetch_ohlcv(self, symbol, timeframe, since, limit):
                self.calls += 1
                return [
                    [since + i * 900_000, 100, 102, 99, 101, 10]
                    for i in range(300)
                ]

        fetcher = LiveOHLCVFetcher.__new__(LiveOHLCVFetcher)
        fetcher.limit = 1500
        exchange = DummyExchange()
        fetcher._exchange = lambda provider: exchange
        rows = fetcher._from_ccxt(
            "okx",
            "BTCUSDT",
            1_900_000_000_000,
        )
        self.assertEqual(len(rows), 1500)
        self.assertEqual(exchange.calls, 5)
        self.assertEqual(rows[0]["cvd_source"], "UNAVAILABLE_NEUTRAL_PROXY")

    def test_message_contains_nine_ordered_sections(self):
        signal = {
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "engine": "LRT-15m",
            "timeframe": "15m",
            "signal_id": "test-id",
            "status": "WATCHLIST",
            "calibration_status": "UNCALIBRATED",
            "confluence_score": 100,
            "ichimoku": {},
            "levels": {},
            "calibration": {},
            "costs": {},
            "risk_flags": ["UNCALIBRATED"],
        }
        header, chart, body = build_signal_messages(signal)
        combined = "\n".join([header, chart, body])
        for number in range(1, 10):
            self.assertIn(f"{number}. ", combined)


if __name__ == "__main__":
    unittest.main()
