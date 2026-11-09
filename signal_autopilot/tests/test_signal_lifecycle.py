import unittest
from datetime import datetime, timezone

from modules.signal_lifecycle import evaluate_open_signal, summarize_signals


def candle(ms, high, low):
    return {"open_time": ms, "high": high, "low": low, "close": (high + low) / 2}


class SignalLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.signal = {
            "signal_id": "abc123",
            "direction": "BUY",
            "created_at_utc": "2026-11-09T10:00:00+00:00",
            "levels": {"entry": 100, "stop_loss": 95, "tp1": 105, "tp2": 110, "tp3": 115},
            "lifecycle_status": "PENDING_ENTRY",
        }

    def test_pending_entry_activates_then_target_milestone(self):
        updated, events = evaluate_open_signal(
            self.signal, [candle(1794219300000, 106, 99)],
            now=datetime(2026, 11, 9, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(updated["lifecycle_status"], "ACTIVE")
        self.assertEqual([e["type"] for e in events], ["ENTRY_ACTIVATED", "TP1_HIT"])
        self.assertEqual(updated["targets_hit"], 1)

    def test_stop_wins_when_stop_and_target_same_bar(self):
        updated, events = evaluate_open_signal(
            self.signal, [candle(1794219300000, 116, 94)],
            now=datetime(2026, 11, 9, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(updated["lifecycle_status"], "STOPPED")
        self.assertEqual([e["type"] for e in events], ["ENTRY_ACTIVATED", "STOP_HIT"])

    def test_expiry_without_activation(self):
        updated, events = evaluate_open_signal(
            self.signal, [],
            now=datetime(2026, 11, 10, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(updated["lifecycle_status"], "EXPIRED")
        self.assertEqual(events[-1]["type"], "SIGNAL_EXPIRED")

    def test_short_target_and_stop(self):
        signal = {
            **self.signal, "direction": "SELL",
            "levels": {"entry": 100, "stop_loss": 105, "tp1": 95, "tp2": 90},
        }
        updated, events = evaluate_open_signal(
            signal, [candle(1794219300000, 101, 94)],
            now=datetime(2026, 11, 9, 11, tzinfo=timezone.utc),
        )
        self.assertEqual(updated["lifecycle_status"], "ACTIVE")
        self.assertIn("TP1_HIT", [e["type"] for e in events])

    def test_daily_summary_counts_outcomes(self):
        rows = [
            {"created_at_utc": "2026-11-09T10:00:00Z", "lifecycle_status": "TARGET_REACHED",
             "closed_at_utc": "2026-11-09T12:00:00Z"},
            {"created_at_utc": "2026-11-08T10:00:00Z", "lifecycle_status": "STOPPED",
             "closed_at_utc": "2026-11-09T13:00:00Z"},
            {"created_at_utc": "2026-11-09T10:00:00Z", "lifecycle_status": "ACTIVE"},
        ]
        report = summarize_signals(rows, "2026-11-09")
        self.assertEqual(report["issued"], 2)
        self.assertEqual(report["target_reached"], 1)
        self.assertEqual(report["stopped"], 1)
        self.assertEqual(report["active_or_pending"], 1)


if __name__ == "__main__":
    unittest.main()
