"""آزمون‌های ثبات snapshot سیگنال در اسکن‌های تکراری."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.signal_tracker import SignalTracker


class SignalTrackerSnapshotTests(unittest.TestCase):
    def test_load_rejects_open_closed_id_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "open_signals.json"
            row = {"signal_id": "duplicate-1"}
            path.write_text(json.dumps({
                "schema_version": 1,
                "open_signals": {"duplicate-1": row},
                "closed_signals": {"duplicate-1": row},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signal_state_open_closed_id_overlap"):
                SignalTracker(path)

    def test_load_rejects_record_key_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "open_signals.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "open_signals": {"key-1": {"signal_id": "different-id"}},
                "closed_signals": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "signal_state_record_invalid"):
                SignalTracker(path)

    def test_closed_signal_id_cannot_be_reopened(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = SignalTracker(Path(tmp) / "open_signals.json")
            tracker.upsert({
                "signal_id": "closed-once",
                "symbol": "BTCUSDT",
                "direction": "BUY",
                "mode": "PRODUCTION",
                "status": "WATCHLIST",
                "created_at_utc": "2026-11-15T10:00:00+00:00",
            })
            self.assertTrue(tracker.close("closed-once", "TEST_CLOSE"))
            with self.assertRaisesRegex(ValueError, "signal_id_already_closed"):
                tracker.upsert({
                    "signal_id": "closed-once",
                    "symbol": "BTCUSDT",
                    "direction": "BUY",
                    "mode": "PRODUCTION",
                    "status": "WATCHLIST",
                    "created_at_utc": "2026-11-15T10:15:00+00:00",
                })
            state = tracker.snapshot()
            self.assertNotIn("closed-once", state["open_signals"])
            self.assertIn("closed-once", state["closed_signals"])

    def test_repeated_upsert_preserves_first_signal_timestamp_and_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = SignalTracker(Path(tmp) / "open_signals.json")
            first = {
                "signal_id": "stable-1",
                "symbol": "BTCUSDT",
                "direction": "BUY",
                "mode": "PRODUCTION",
                "status": "WATCHLIST",
                "created_at_utc": "2026-11-15T10:00:00+00:00",
                "last_closed_candle_utc": "2026-11-15T09:45:00+00:00",
                "levels": {"entry": 100.0, "stop_loss": 98.0, "tp2": 104.0},
                "lfs_score": 0.30,
                "lfs_threshold": 0.30,
                "hypothesis": "first immutable hypothesis",
            }
            with patch("modules.signal_tracker._now", side_effect=[
                "2026-11-15T10:00:01+00:00",
                "2026-11-15T10:00:02+00:00",
                "2026-11-15T10:15:01+00:00",
                "2026-11-15T10:15:02+00:00",
            ]):
                first_record = tracker.upsert(first)
                second = {
                    **first,
                    "created_at_utc": "2026-11-15T10:15:00+00:00",
                    "levels": {"entry": 101.0, "stop_loss": 99.0, "tp2": 105.0},
                    "lfs_score": 0.55,
                    "lfs_threshold": 0.70,
                    "hypothesis": "later changed hypothesis",
                }
                second_record = tracker.upsert(second)

            self.assertEqual(second_record["created_at_utc"], "2026-11-15T10:00:00+00:00")
            self.assertEqual(second_record["first_seen_utc"], first_record["first_seen_utc"])
            self.assertEqual(second_record["levels"], first["levels"])
            self.assertEqual(second_record["last_closed_candle_utc"], first["last_closed_candle_utc"])
            self.assertEqual(second_record["lfs_score"], 0.30)
            self.assertEqual(second_record["lfs_threshold"], 0.30)
            self.assertEqual(second_record["hypothesis"], "first immutable hypothesis")
            self.assertEqual(second_record["updates"], 2)
            self.assertEqual(second_record["last_seen_utc"], "2026-11-15T10:15:01+00:00")

            saved = json.loads((Path(tmp) / "open_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["open_signals"]["stable-1"]["created_at_utc"], first["created_at_utc"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
