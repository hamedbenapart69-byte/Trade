import unittest

from app.signals import Candle
from app.research_education import (
    detect_breakout_retests,
    detect_breakout_acceptance,
    detect_liquidity_sweeps,
    detect_value_boundary_rejections,
    filter_events_by_higher_timeframe,
    filter_events_by_higher_timeframe_regime,
    map_events_to_signal_candles,
    ResearchEvent,
    _higher_timeframe_bias_series,
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

    def test_h2_time_proxy_requires_two_closes_back_inside_prior_24h_range(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(30)]
        bars.append(candle(30, 100, 103, 100, 102))
        bars.append(candle(31, 102, 102.5, 100, 100.5))
        bars.append(candle(32, 100.5, 101, 99.5, 100))
        events = detect_value_boundary_rejections(
            bars, lookback=24, rejection_bars=2
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].hypothesis_id, "H2_TIME_REJECTION_PROXY")
        self.assertEqual(events[0].side, "SHORT")
        self.assertEqual(events[0].signal_index, 32)

    def test_h2_time_proxy_rejects_single_close_reclaim_without_second_close(self):
        bars = [candle(i, 100, 101, 99, 100) for i in range(30)]
        bars.append(candle(30, 100, 103, 100, 102))
        bars.append(candle(31, 102, 102.5, 100, 100.5))
        bars.append(candle(32, 100.5, 103, 100, 102))
        self.assertEqual(
            detect_value_boundary_rejections(
                bars, lookback=24, rejection_bars=2
            ),
            [],
        )

    def test_4h_events_map_to_hourly_candle_with_identical_close_time(self):
        hour_ms = 60 * 60_000
        hourly = [
            Candle(i * hour_ms, 100, 101, 99, 100, 100.0, (i + 1) * hour_ms - 1, True)
            for i in range(8)
        ]
        four_hour = [
            Candle(i * 4 * hour_ms, 100, 101, 99, 100, 400.0, (i + 1) * 4 * hour_ms - 1, True)
            for i in range(2)
        ]
        event = ResearchEvent("H1_LRT_V3_4H", "LONG", 1, 99.0, 0, "4h_sweep_reclaim")
        mapped = map_events_to_signal_candles([event], four_hour, hourly)
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].signal_index, 7)
        self.assertEqual(mapped[0].side, "LONG")
    def test_h8_lrt_v2_accepts_only_neutral_higher_timeframe_regime(self):
        signal_bars = [
            Candle(i * 60 * 60_000, 100, 101, 99, 100, 100.0, (i + 1) * 60 * 60_000 - 1, True)
            for i in range(240)
        ]
        neutral_htf = [
            Candle(i * 4 * 60 * 60_000, 100, 101, 99, 100, 400.0, (i + 1) * 4 * 60 * 60_000 - 1, True)
            for i in range(60)
        ]
        events = [
            ResearchEvent("H1", "LONG", 239, 100.0, 238, "sweep_reclaim"),
            ResearchEvent("H1", "SHORT", 239, 100.0, 238, "sweep_reclaim"),
        ]
        filtered = filter_events_by_higher_timeframe_regime(
            events, signal_bars, neutral_htf, allowed_biases=("NEUTRAL",)
        )
        self.assertEqual(filtered, events)

    def test_h8_lrt_v2_rejects_directional_higher_timeframe_regime(self):
        signal_bars = [
            Candle(i * 60 * 60_000, 100 + i, 101 + i, 99 + i, 100 + i, 100.0, (i + 1) * 60 * 60_000 - 1, True)
            for i in range(240)
        ]
        rising_htf = [
            Candle(i * 4 * 60 * 60_000, 100 + i, 101 + i, 99 + i, 100 + i, 400.0, (i + 1) * 4 * 60 * 60_000 - 1, True)
            for i in range(60)
        ]
        event = ResearchEvent("H1", "LONG", 239, 300.0, 238, "sweep_reclaim")
        filtered = filter_events_by_higher_timeframe_regime(
            [event], signal_bars, rising_htf, allowed_biases=("NEUTRAL",)
        )
        self.assertEqual(filtered, [])
    def test_h8_bias_series_matches_scalar_bias_on_each_completed_prefix(self):
        bars = [
            Candle(
                i * 4 * 60 * 60_000, 100 + i, 101 + i, 99 + i, 100 + i,
                400.0, (i + 1) * 4 * 60 * 60_000 - 1, True,
            )
            for i in range(60)
        ]
        expected = [higher_timeframe_bias(bars[:i + 1]) for i in range(len(bars))]
        self.assertEqual(_higher_timeframe_bias_series(bars), expected)
    def test_h8_dlc_direction_gate_filters_misaligned_confirmation_events(self):
        signal_bars = [
            Candle(
                i * 60 * 60_000, 100 + i, 101 + i, 99 + i, 100 + i,
                100.0, (i + 1) * 60 * 60_000 - 1, True,
            )
            for i in range(240)
        ]
        htf_bars = [
            Candle(
                i * 4 * 60 * 60_000,
                100 + i,
                101 + i,
                99 + i,
                100 + i,
                400.0,
                (i + 1) * 4 * 60 * 60_000 - 1,
                True,
            )
            for i in range(60)
        ]
        events = [
            ResearchEvent("H1", "LONG", 239, 300.0, 238, "reclaim"),
            ResearchEvent("H1", "SHORT", 239, 300.0, 238, "reclaim"),
        ]
        filtered = filter_events_by_higher_timeframe(
            events, signal_bars, htf_bars
        )
        self.assertEqual([event.side for event in filtered], ["LONG"])

    def test_h8_dlc_uses_only_completed_higher_timeframe_candles(self):
        signal_bars = [
            Candle(
                i * 60 * 60_000, 100 + i, 101 + i, 99 + i, 100 + i,
                100.0, (i + 1) * 60 * 60_000 - 1, True,
            )
            for i in range(240)
        ]
        htf_bars = [
            Candle(
                i * 4 * 60 * 60_000,
                100 + i,
                101 + i,
                99 + i,
                100 + i,
                400.0,
                (i + 1) * 4 * 60 * 60_000 - 1,
                True,
            )
            for i in range(59)
        ]
        # این کندل پس از زمان سیگنال بسته می‌شود و نباید در جهت HTF دخالت کند.
        htf_bars.append(
            Candle(
                59 * 4 * 60 * 60_000,
                159,
                160,
                80,
                80,
                400.0,
                60 * 4 * 60 * 60_000 - 1,
                True,
            )
        )
        event = ResearchEvent("H5_PRICE_PROXY", "LONG", 235, 150.0, 234, "acceptance")
        filtered = filter_events_by_higher_timeframe(
            [event], signal_bars, htf_bars
        )
        self.assertEqual(filtered, [event])

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
