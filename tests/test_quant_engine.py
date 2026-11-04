import unittest
from app.quant.indicators import (MarketDataValidationError, atr, bollinger, correlation, ema, pct_return, rsi, validate_ohlcv, volume_ratio)
from app.quant.decision import Decision, DecisionInput, decide


class QuantIndicatorTests(unittest.TestCase):
    def test_ema_rsi_and_return(self):
        values = [float(x) for x in range(1, 31)]
        self.assertAlmostEqual(ema(values, 10), 25.5)
        self.assertEqual(rsi(values, 14), 100.0)
        self.assertAlmostEqual(pct_return(values, 5), (30 / 25 - 1) * 100)

    def test_ohlcv_and_atr(self):
        candles = []
        for i in range(20):
            close = 100 + i
            candles.append({"timestamp": i + 1, "open": close - .5, "high": close + 1, "low": close - 1, "close": close, "volume": 100 + i})
        self.assertEqual(len(validate_ohlcv(candles)), 20)
        self.assertGreater(atr(candles, 14), 0)
        self.assertGreater(volume_ratio([100] * 20 + [200]), 1)

    def test_bollinger_and_correlation(self):
        band = bollinger([float(x) for x in range(1, 21)])
        self.assertLess(band["lower"], band["middle"])
        self.assertGreater(band["upper"], band["middle"])
        self.assertAlmostEqual(correlation([1, 2, 3], [2, 4, 6]), 1.0)

    def test_invalid_candle_order_rejected(self):
        rows = [{"timestamp": 2, "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 1},
                {"timestamp": 1, "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 1}]
        with self.assertRaises(MarketDataValidationError):
            validate_ohlcv(rows)


class DecisionGateTests(unittest.TestCase):
    def base(self, **changes):
        values = dict(data_age_seconds=30, required_data_complete=True, technical_score=85,
                      fundamental_score=80, liquidity_score=80, risk_score=85,
                      entry_trigger_confirmed=True, stop_loss_pct=3, take_profit_pct=9)
        values.update(changes)
        return DecisionInput(**values)

    def test_buy_requires_every_gate(self):
        self.assertEqual(decide(self.base()).decision, Decision.BUY_NOW)
        self.assertEqual(decide(self.base(entry_trigger_confirmed=False)).decision, Decision.CONDITIONAL_BUY)
        self.assertEqual(decide(self.base(required_data_complete=False)).decision, Decision.INSUFFICIENT_DATA)
        self.assertEqual(decide(self.base(hard_risk_veto=True)).decision, Decision.REJECT)
        self.assertEqual(decide(self.base(take_profit_pct=3)).decision, Decision.REJECT)

    def test_stale_data_never_produces_buy(self):
        self.assertEqual(decide(self.base(data_age_seconds=901)).decision, Decision.INSUFFICIENT_DATA)


if __name__ == "__main__":
    unittest.main()
