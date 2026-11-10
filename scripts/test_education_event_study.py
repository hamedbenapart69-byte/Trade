"""Tests for the standalone OHLCV event-study execution timing."""

import unittest

from app.research_education import ResearchEvent
from app.signals import Candle
from scripts.education_event_study import event_observation


class EducationEventStudyTests(unittest.TestCase):
    def test_signal_is_known_at_close_and_entry_uses_next_bar_open(self):
        hour_ms = 60 * 60_000
        candles = [
            Candle(
                i * hour_ms,
                100.0,
                103.0,
                99.0,
                100.0 + i * 0.1,
                10.0,
                (i + 1) * hour_ms - 1,
                True,
            )
            for i in range(12)
        ]
        candles[4] = Candle(
            4 * hour_ms, 100.0, 101.0, 99.0, 100.0, 10.0,
            5 * hour_ms - 1, True,
        )
        candles[7] = Candle(
            7 * hour_ms, 100.0, 103.0, 100.0, 102.0, 10.0,
            8 * hour_ms - 1, True,
        )
        event = ResearchEvent(
            "H1_LRT_V3_4H", "LONG", 3, 99.0, 2, "4h_sweep_reclaim"
        )

        observation = event_observation(event, candles, horizon=4)

        self.assertIsNotNone(observation)
        self.assertEqual(observation["signal_time_ms"], candles[3].close_time)
        self.assertEqual(observation["exit_time_ms"], candles[7].close_time)
        self.assertAlmostEqual(observation["gross_return"], 0.02, places=8)


if __name__ == "__main__":
    unittest.main()
