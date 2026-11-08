import unittest
from modules.signal_engine import build_signal, generate_signals, C10


class EmaAtrSignalTests(unittest.TestCase):
    def make_row(self, direction="up"):
        candles = []
        # آخرین کندل یک ساعت قبل از زمان تولید گزارش است.
        start = 1794151800000 - 70 * 3600000
        for index in range(70):
            if direction == "up":
                close = 100.0 + index * 0.35
            elif direction == "down":
                close = 160.0 - index * 0.35
            else:
                close = 100.0
            candles.append({
                "timestamp": start + index * 3600000,
                "open": close - 0.1,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0,
            })
        return {
            "symbol": "BTC/USDT:USDT",
            "availability": {"ohlcv": "OK"},
            "ohlcv": candles,
        }

    def test_long_signal_has_entry_stop_and_two_targets(self):
        result = build_signal(self.make_row("up"), "2026-11-08T19:00:00+03:30")
        self.assertEqual(result["status"], "BUY_NOW")
        self.assertEqual(result["side"], "BUY")
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit"][0], result["entry"])
        self.assertGreater(result["take_profit"][1], result["take_profit"][0])

    def test_short_signal_has_inverse_risk_levels(self):
        result = build_signal(self.make_row("down"), "2026-11-08T19:00:00+03:30")
        self.assertEqual(result["status"], "SELL_NOW")
        self.assertEqual(result["side"], "SELL")
        self.assertGreater(result["stop_loss"], result["entry"])
        self.assertLess(result["take_profit"][0], result["entry"])
        self.assertLess(result["take_profit"][1], result["take_profit"][0])

    def test_flat_market_has_no_qualified_setup(self):
        result = build_signal(self.make_row("flat"), "2026-11-08T19:00:00+03:30")
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP")

    def test_missing_ohlcv_degrades_without_requiring_funding(self):
        row = {"symbol": "BTC/USDT:USDT", "availability": {"ohlcv": "UNAVAILABLE"}, "ohlcv": []}
        result = build_signal(row, "2026-11-08T19:00:00+03:30")
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")
        self.assertIsNone(result["entry"])

    def test_all_outputs_use_c10_and_no_signal_message_is_explicit(self):
        payload = generate_signals({
            "generated_at_utc": "2026-11-08T19:00:00+03:30",
            "symbols": [self.make_row("flat")],
        })
        self.assertTrue(all(item["status"] in C10 for item in payload["signals"]))
        self.assertEqual(payload["today_signal_message"], "امروز سیگنال نیست")
        self.assertEqual(payload["provider"], "unknown")
        self.assertEqual(payload["today_signal_message"], "امروز سیگنال نیست")

    def test_degraded_market_is_not_mislabeled_as_no_signal(self):
        payload = generate_signals({
            "provider": "none",
            "generated_at_utc": "2026-11-08T19:00:00+03:30",
            "symbols": [],
        })
        self.assertEqual(payload["pipeline_status"], "DEGRADED")
        self.assertEqual(payload["provider"], "none")
        self.assertEqual(payload["today_signal_message"], "دادهٔ کافی برای ارزیابی بازار در دسترس نیست")


if __name__ == "__main__":
    unittest.main()
