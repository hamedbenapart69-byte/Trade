import math
import unittest
from datetime import datetime

from modules.signal_engine import build_signal, generate_signals, C10


GENERATED = "2026-11-08T19:00:00+03:30"


class EmaContinuationV2Tests(unittest.TestCase):
    def make_row(self, direction="up", proxy=False, volume_multiplier=1.5, extension_atr=0.0):
        now_ms = int(datetime.fromisoformat(GENERATED).timestamp() * 1000)
        start = now_ms - 220 * 3_600_000
        candles = []
        sign = 1.0 if direction == "up" else -1.0 if direction == "down" else 0.0
        for index in range(220):
            amplitude = 0.18 if sign >= 0 else 0.40
            base = 100.0 if sign >= 0 else 160.0
            close = base + sign * index * 0.05 + amplitude * math.sin(index * 1.17)
            open_ = close - sign * 0.025
            if sign >= 0:
                high = close + 0.10
                low = 99.5 + index * 0.05 + 0.05 * math.sin(index * 1.17)
            else:
                high = 160.7 - index * 0.05 + 0.10 * math.sin(index * 1.17)
                low = close - 0.10
            if index == 219:
                open_ = close - sign * 0.22
                high = close + 0.10 if sign >= 0 else close + 0.50
                low = close - 0.50 if sign >= 0 else close - 0.10
            candles.append({
                "timestamp": start + index * 3_600_000,
                "open": open_, "high": high, "low": low, "close": close,
                "volume": 1500.0 if index == 219 else 1000.0,
            })
        entry = candles[-1]["close"] + extension_atr * 0.5
        row = {
            "symbol": "BTC/USDT:USDT", "timeframe": "1H",
            "availability": {"ohlcv": "OK"}, "ohlcv": candles, "last": entry,
            "ticker_timestamp_utc": "2026-11-08T15:29:00+00:00",
            "ticker_timestamp_source": "FETCH_TIME_PROXY" if proxy else "EXCHANGE",
        }
        if volume_multiplier != 1.5:
            row["ohlcv"][-1]["volume"] = 1000.0 * volume_multiplier
        return row

    def test_long_signal_requires_all_quality_gates_and_has_structural_stop(self):
        result = build_signal(self.make_row("up"), GENERATED)
        self.assertEqual(result["status"], "BUY_NOW", result.get("reason"))
        self.assertEqual(result["side"], "BUY")
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit"][0], result["entry"])
        self.assertGreater(result["take_profit"][1], result["take_profit"][0])
        self.assertTrue(all(result["quality_gates"].values()))
        self.assertEqual(result["quality_metrics"]["reward_risk_tp1"], 1.5)
        self.assertEqual(result["quality_metrics"]["reward_risk_tp2"], 2.5)
        self.assertEqual(len(result["evidence_candles"]), 200)
        self.assertEqual(len(result["input_hash"]), 64)

    def test_short_signal_has_inverse_risk_levels(self):
        result = build_signal(self.make_row("down"), GENERATED)
        self.assertEqual(result["status"], "SELL_NOW", result.get("reason"))
        self.assertEqual(result["side"], "SELL")
        self.assertGreater(result["stop_loss"], result["entry"])
        self.assertLess(result["take_profit"][0], result["entry"])
        self.assertLess(result["take_profit"][1], result["take_profit"][0])

    def test_proxy_timestamp_can_never_become_immediate_signal(self):
        result = build_signal(self.make_row("up", proxy=True), GENERATED)
        self.assertEqual(result["entry_price_quality"], "PROXY_FETCH_TIME")
        self.assertEqual(result["status"], "CONDITIONAL_BUY")
        self.assertNotEqual(result["status"], "BUY_NOW")

    def test_low_volume_fails_closed(self):
        result = build_signal(self.make_row("up", volume_multiplier=0.8), GENERATED)
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP", result)
        self.assertIn("volume_confirmation", result["reason"])

    def test_flat_market_has_no_qualified_setup(self):
        result = build_signal(self.make_row("flat"), GENERATED)
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP")

    def test_insufficient_history_is_degraded(self):
        row = self.make_row("up")
        row["ohlcv"] = row["ohlcv"][-70:]
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")
        self.assertIsNone(result["entry"])

    def test_missing_live_futures_ticker_is_degraded(self):
        row = self.make_row("up")
        row.pop("last")
        row.pop("ticker_timestamp_utc")
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")
        self.assertIsNone(result["entry"])

    def test_bad_ohlcv_is_degraded_not_actionable(self):
        row = self.make_row("up")
        row["ohlcv"][-1]["high"] = 0.0
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")

    def test_all_outputs_use_c10_and_no_signal_is_explicit(self):
        payload = generate_signals({
            "generated_at_utc": GENERATED,
            "symbols": [self.make_row("flat")],
        })
        self.assertTrue(all(item["status"] in C10 for item in payload["signals"]))
        self.assertEqual(payload["today_signal_message"], "امروز سیگنال نیست", payload["signals"])
        self.assertEqual(payload["engine"], "EMA20_EMA50_ATR14_QUALITY_GATES_V2")

    def test_proxy_is_counted_as_conditional_not_trade(self):
        payload = generate_signals({
            "provider": "kucoinfutures", "generated_at_utc": GENERATED,
            "symbols": [self.make_row("up", proxy=True)],
        })
        self.assertEqual(len(payload["trade_signals"]), 0)
        self.assertEqual(len(payload["conditional_signals"]), 1)
        self.assertIn("ورود فوری مجاز نیست", payload["today_signal_message"])

    def test_partial_universe_remains_degraded(self):
        payload = generate_signals({
            "provider": "kucoinfutures", "generated_at_utc": GENERATED,
            "symbols_requested": 100, "symbols": [self.make_row("flat")],
        })
        self.assertEqual(payload["pipeline_status"], "DEGRADED")
        self.assertEqual(payload["quality"]["coverage_pct"], 1.0)
        self.assertIn("1 از 100", payload["today_signal_message"])


if __name__ == "__main__":
    unittest.main()
