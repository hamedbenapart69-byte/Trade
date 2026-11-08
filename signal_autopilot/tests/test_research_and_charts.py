import unittest

from modules.chart_renderer import render_signal_chart
from research.mvp_validation import backtest_window


class ChartRendererTests(unittest.TestCase):
    def test_chart_is_png_and_contains_real_candle_context(self):
        candles = []
        start = 1794151800000 - 70 * 3600000
        for i in range(70):
            close = 100.0 + i * 0.25
            candles.append({
                "timestamp": start + i * 3600000,
                "open": close - 0.1,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000.0,
            })
        signal = {
            "symbol": "BTC-USDT-SWAP",
            "side": "BUY",
            "entry": 118.0,
            "stop_loss": 116.0,
            "take_profit": [121.0, 124.0],
            "reason": "EMA20 بالاتر از EMA50 و فاصله بیش از حداقل تعیین‌شده",
            "chart_candles": candles,
        }
        image = render_signal_chart(signal)
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(image), 10_000)


class WalkForwardExecutionTests(unittest.TestCase):
    def test_same_bar_stop_and_target_uses_conservative_stop(self):
        rows = []
        for i in range(120):
            close = 100.0 + i * 0.5
            rows.append({
                "timestamp": 1_700_000_000_000 + i * 3_600_000,
                "open": close - 0.1,
                "high": close + 0.4,
                "low": close - 0.4,
                "close": close,
                "volume": 1000.0,
            })
        # اولین ورود بعد از تأیید EMA در کندل ۵۰ انجام می‌شود.
        entry = rows[51]["open"]
        rows[52]["high"] = entry + 10.0
        rows[52]["low"] = entry - 10.0
        trades = backtest_window("BTC", rows)
        self.assertTrue(trades)
        self.assertEqual(trades[0]["exit_reason"], "STOP_SAME_BAR_AMBIGUITY")
        self.assertLess(trades[0]["net_r"], 0.0)


if __name__ == "__main__":
    unittest.main()
