"""Tests for causal market-structure primitives."""
import unittest

from modules.market_structure import (
    detect_confirmed_swings,
    detect_fair_value_gaps,
)


def candle(open_, high, low, close):
    return {"open": open_, "high": high, "low": low, "close": close}


class FairValueGapTests(unittest.TestCase):
    def test_bullish_gap_is_confirmed_on_third_candle(self):
        rows = [
            candle(10, 11, 9, 10),
            candle(10, 13, 10, 12),
            candle(14, 15, 13, 14),
        ]
        self.assertEqual(detect_fair_value_gaps(rows), [{
            "direction": "BULLISH", "bottom": 11.0, "top": 13.0,
            "pattern_start_index": 0, "confirmed_at_index": 2,
        }])

    def test_bearish_gap_is_confirmed_on_third_candle(self):
        rows = [
            candle(14, 15, 13, 14),
            candle(14, 14, 11, 12),
            candle(10, 12, 9, 10),
        ]
        gaps = detect_fair_value_gaps(rows)
        self.assertEqual(gaps[0]["direction"], "BEARISH")
        self.assertEqual((gaps[0]["bottom"], gaps[0]["top"]), (12.0, 13.0))
        self.assertEqual(gaps[0]["confirmed_at_index"], 2)

    def test_no_gap_when_middle_candle_direction_disagrees(self):
        rows = [
            candle(10, 11, 9, 10),
            candle(12, 13, 10, 11),
            candle(14, 15, 13, 14),
        ]
        self.assertEqual(detect_fair_value_gaps(rows), [])

    def test_invalid_ohlc_rejected(self):
        with self.assertRaises(ValueError):
            detect_fair_value_gaps([candle(10, 8, 9, 10)])


class ConfirmedSwingTests(unittest.TestCase):
    def test_swing_high_is_not_available_until_right_bars_close(self):
        rows = [
            candle(8, 9, 7, 8),
            candle(9, 10, 8, 9),
            candle(10, 15, 9, 14),
            candle(9, 11, 8, 9),
            candle(8, 9, 7, 8),
        ]
        point = detect_confirmed_swings(rows, span=2)[0]
        self.assertEqual(point["kind"], "HIGH")
        self.assertEqual(point["pivot_index"], 2)
        self.assertEqual(point["confirmed_at_index"], 4)

    def test_swing_low_is_confirmed_with_delay(self):
        rows = [
            candle(12, 13, 11, 12),
            candle(10, 11, 8, 9),
            candle(7, 8, 4, 5),
            candle(9, 10, 7, 9),
            candle(11, 12, 10, 11),
        ]
        points = detect_confirmed_swings(rows, span=2)
        low = next(point for point in points if point["kind"] == "LOW")
        self.assertEqual(low["pivot_index"], 2)
        self.assertEqual(low["confirmed_at_index"], 4)

    def test_span_must_be_positive(self):
        with self.assertRaises(ValueError):
            detect_confirmed_swings([], span=0)


if __name__ == "__main__":
    unittest.main()
