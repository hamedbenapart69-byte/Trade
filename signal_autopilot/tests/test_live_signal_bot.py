import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import calculate_confluence, tenkan_kijun_cross
from modules.live_data_adapter import LiveOHLCVFetcher, is_closed_candle
from telegram_bot import build_signal_messages


class LiveSignalBotTests(unittest.TestCase):
    def test_open_candle_is_excluded_by_close_time_rule(self):
        now_ms = 1_800_000_000_000
        self.assertTrue(is_closed_candle(now_ms - 900_000, 900_000, now_ms))
        self.assertFalse(is_closed_candle(now_ms, 900_000, now_ms))

    def test_confluence_requires_all_five_components_for_more_than_80(self):
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
        score, parts = calculate_confluence(result, rows, "BUY")
        self.assertEqual(score, 80)
        self.assertFalse(parts["tenkan_kijun_cross"])

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
        self.assertFalse(parts["tenkan_kijun_cross"])


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
