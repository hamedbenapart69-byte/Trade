import math
import unittest
from datetime import datetime

from modules.signal_engine import build_signal, generate_signals, C10, ema, atr


GENERATED = "2026-11-08T19:00:00+03:30"


class EmaContinuationV2Tests(unittest.TestCase):
    def make_row(self, direction="up", proxy=False, pullback=True):
        now_ms = int(datetime.fromisoformat(GENERATED).timestamp() * 1000)
        sign = 1 if direction == "up" else -1 if direction == "down" else 0

        candles_1h = []
        start_1h = now_ms - 220 * 3_600_000
        for index in range(220):
            base = 100.0 if sign >= 0 else 160.0
            close = base + sign * 0.04 * index + (0.10 * math.sin(index * 0.9) if sign else 0.0)
            open_ = close - sign * 0.02
            candles_1h.append({
                "timestamp": start_1h + index * 3_600_000,
                "open": open_, "high": close + 0.25, "low": close - 0.25,
                "close": close, "volume": 1000.0,
            })

        if sign:
            ema50_1h = ema(
                [float(c["close"]) for c in candles_1h], 50
            )[-1]
            atr_1h = atr(candles_1h)
            if sign > 0:
                candles_1h[-1]["open"] = candles_1h[-1]["close"] - 0.20
                candles_1h[-1]["high"] = candles_1h[-1]["close"] + 0.20
                candles_1h[-1]["low"] = (
                    ema50_1h + 0.05 * atr_1h if pullback else candles_1h[-1]["close"] - 0.20
                )
            else:
                candles_1h[-1]["open"] = candles_1h[-1]["close"] + 0.20
                candles_1h[-1]["low"] = candles_1h[-1]["close"] - 0.20
                candles_1h[-1]["high"] = (
                    ema50_1h - 0.05 * atr_1h if pullback else candles_1h[-1]["close"] + 0.20
                )

        candles_4h = []
        start_4h = now_ms - 220 * 14_400_000
        for index in range(220):
            base = 100.0 if sign >= 0 else 160.0
            close = base + sign * 0.5 * index + (0.5 * math.sin(index * 0.4) if sign else 0.0)
            open_ = close - sign * 0.10
            candles_4h.append({
                "timestamp": start_4h + index * 14_400_000,
                "open": open_, "high": close + 0.50, "low": close - 0.50,
                "close": close, "volume": 4000.0,
            })

        return {
            "symbol": "BTC/USDT:USDT", "timeframe": "1H",
            "availability": {"ohlcv": "OK", "ohlcv_4h": "OK"},
            "ohlcv": candles_1h, "ohlcv_4h": candles_4h,
            "last": candles_1h[-1]["close"], "quote_volume_24h": 20_000_000.0,
            "ticker_timestamp_utc": "2026-11-08T15:29:00+00:00",
            "ticker_timestamp_source": "FETCH_TIME_PROXY" if proxy else "EXCHANGE",
        }

    def test_long_v2_requires_4h_regime_and_1h_pullback_rejection(self):
        result = build_signal(self.make_row("up"), GENERATED)
        self.assertEqual(result["status"], "BUY_NOW", result.get("reason"))
        self.assertEqual(result["side"], "BUY")
        self.assertLess(result["stop_loss"], result["entry"])
        self.assertGreater(result["take_profit"][0], result["entry"])
        self.assertGreater(result["take_profit"][1], result["take_profit"][0])
        self.assertTrue(all(result["quality_gates"].values()))
        self.assertEqual(result["quality_metrics"]["reward_risk_tp1"], 1.5)
        self.assertEqual(result["quality_metrics"]["reward_risk_tp2"], 2.5)
        self.assertEqual(len(result["evidence_candles"]["1h"]), 200)
        self.assertEqual(len(result["evidence_candles"]["4h"]), 200)
        self.assertEqual(len(result["input_hash"]), 64)

    def test_short_v2_has_inverse_structural_risk_levels(self):
        result = build_signal(self.make_row("down"), GENERATED)
        self.assertEqual(result["status"], "SELL_NOW", result.get("reason"))
        self.assertEqual(result["side"], "SELL")
        self.assertGreater(result["stop_loss"], result["entry"])
        self.assertLess(result["take_profit"][0], result["entry"])
        self.assertLess(result["take_profit"][1], result["take_profit"][0])

    def test_proxy_timestamp_is_conditional_not_immediate(self):
        result = build_signal(self.make_row("up", proxy=True), GENERATED)
        self.assertEqual(result["entry_price_quality"], "PROXY_FETCH_TIME")
        self.assertEqual(result["status"], "CONDITIONAL_BUY")

    def test_no_1h_pullback_means_no_setup(self):
        result = build_signal(self.make_row("up", pullback=False), GENERATED)
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP")
        self.assertFalse(result["quality_gates"]["1h_pullback_to_ema50"])

    def test_flat_4h_regime_has_no_setup(self):
        result = build_signal(self.make_row("flat"), GENERATED)
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP")

    def test_low_liquidity_fails_g4(self):
        row = self.make_row("up")
        row["quote_volume_24h"] = 5_000_000.0
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "NO_QUALIFIED_SETUP")
        self.assertIn("G4 minimum", result["reason"])

    def test_insufficient_4h_history_is_degraded(self):
        row = self.make_row("up")
        row["ohlcv_4h"] = row["ohlcv_4h"][-70:]
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")
        self.assertIsNone(result["entry"])

    def test_missing_live_futures_ticker_is_degraded(self):
        row = self.make_row("up")
        row.pop("last")
        row.pop("ticker_timestamp_utc")
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")

    def test_irregular_1h_timestamps_are_degraded(self):
        row = self.make_row("up")
        row["ohlcv"][-2]["timestamp"] -= 3_600_000
        result = build_signal(row, GENERATED)
        self.assertEqual(result["status"], "MARKET_DATA_DEGRADED")

    def test_bad_ohlcv_is_degraded(self):
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
        self.assertEqual(payload["today_signal_message"], "امروز سیگنال نیست")
        self.assertEqual(payload["engine"], "EMA_4H_REGIME_1H_PULLBACK_V2")

    def test_proxy_is_conditional_not_trade(self):
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
