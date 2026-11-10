import unittest

from app.signals import Candle
from app.research_education import (
    detect_breakout_retests,
    detect_breakout_acceptance,
    detect_liquidity_sweeps,
    higher_timeframe_bias,
    passes_higher_timeframe_gate,
)


def candle(i, o, h, l, c, final=True):
    return Candle(i * 60_000, o, h, l, c, 100.0, (i + 1) * 60_000 - 1, final)


class EducationHypothesisTests(unittest.TestCase):
    def test_h1_detects_sweep_of_prior_high_and_reclaim(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 99.5, 100.5))
        events = detect_liquidity_sweeps(bars, lookback=20, atr_period=14)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].hypothesis_id, "H1")
        self.assertEqual(events[0].side, "SHORT")
        self.assertEqual(events[0].signal_index, 25)

    def test_h1_does_not_call_close_above_prior_high_a_reclaim(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 99.5, 102))
        self.assertEqual(
            detect_liquidity_sweeps(bars, lookback=20, atr_period=14), []
        )

    def test_h1_rejects_open_or_out_of_order_candles(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars[-1] = candle(24, 100, 103, 99, 100, final=False)
        self.assertEqual(detect_liquidity_sweeps(bars), [])
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars[5], bars[6] = bars[6], bars[5]
        self.assertEqual(detect_liquidity_sweeps(bars), [])

    def test_h6_detects_breakout_then_held_retest(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 100, 102))
        bars.append(candle(26, 102, 102.5, 100.5, 101.5))
        events = detect_breakout_retests(
            bars, range_lookback=20, retest_window=4,
            tolerance_atr=0.10, atr_period=14,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].hypothesis_id, "H6")
        self.assertEqual(events[0].side, "LONG")
        self.assertEqual(events[0].signal_index, 26)

    def test_h6_rejects_retest_that_closes_back_inside_range(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 100, 102))
        bars.append(candle(26, 102, 102.5, 99.5, 100))
        self.assertEqual(detect_breakout_retests(bars), [])

    def test_h5_price_proxy_requires_consecutive_closes_outside_range(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 100, 102))
        bars.append(candle(26, 102, 103, 101, 102.5))
        bars.append(candle(27, 102.5, 103.5, 102, 103))
        events = detect_breakout_acceptance(bars, range_lookback=20, acceptance_bars=2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].hypothesis_id, "H5_PRICE_PROXY")
        self.assertEqual(events[0].side, "LONG")
        self.assertEqual(events[0].signal_index, 27)

    def test_h5_price_proxy_rejects_failed_acceptance(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(25)]
        bars.append(candle(25, 100, 103, 100, 102))
        bars.append(candle(26, 102, 102.5, 99.5, 100))
        bars.append(candle(27, 100, 101, 99, 100))
        self.assertEqual(detect_breakout_acceptance(bars), [])

    def test_h7_requires_completed_htf_bars_and_directional_alignment(self):
        rising = [
            candle(i, 100 + i, 101 + i, 99 + i, 100 + i)
            for i in range(60)
        ]
        self.assertEqual(higher_timeframe_bias(rising), "UP")
        self.assertTrue(passes_higher_timeframe_gate("LONG", rising))
        self.assertFalse(passes_higher_timeframe_gate("SHORT", rising))
        rising[-1] = candle(59, 159, 160, 158, 159, final=False)
        self.assertEqual(higher_timeframe_bias(rising), "NEUTRAL")

    def test_h7_returns_neutral_when_history_is_insufficient(self):
        rising = [candle(i, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(30)]
        self.assertEqual(higher_timeframe_bias(rising), "NEUTRAL")

    def test_invalid_parameters_fail_closed(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(30)]
        self.assertEqual(detect_liquidity_sweeps(bars, lookback=1), [])
        self.assertEqual(detect_breakout_retests(bars, retest_window=0), [])


if __name__ == "__main__":
    unittest.main()
