import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy, candle_delta
from modules.signal_tracker import SignalTracker


class CVDProxyTests(unittest.TestCase):
    def test_buy_sell_volume_delta_uses_ohlcv_close_location(self):
        bar = {"high": 110, "low": 90, "close": 105, "volume": 100}
        # Close is 75% through range: buy=75, sell=25, delta=50.
        self.assertEqual(candle_delta(bar), 50.0)

    def test_flat_range_has_zero_directional_delta(self):
        self.assertEqual(candle_delta(
            {"high": 100, "low": 100, "close": 100, "volume": 10}
        ), 0.0)

    def test_source_is_explicit_proxy_not_real_flow(self):
        result = calculate_cvd_proxy([
            {"high": 10, "low": 0, "close": 8, "volume": 10}
        ])
        self.assertEqual(CVD_SOURCE, "PROXY_OHLCV")
        self.assertEqual(result["CVD_SOURCE"], "PROXY_OHLCV")
        self.assertFalse(result["is_real_aggressor_flow"])


class SignalTrackerTests(unittest.TestCase):
    def test_upsert_persists_and_updates_open_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "open_signals.json"
            tracker = SignalTracker(path)
            tracker.upsert({"signal_id": "abc123", "symbol": "BTCUSDT"})
            tracker.upsert({"signal_id": "abc123", "direction": "BUY"})
            saved = json.loads(path.read_text(encoding="utf-8"))
            record = saved["open_signals"]["abc123"]
            self.assertEqual(record["symbol"], "BTCUSDT")
            self.assertEqual(record["direction"], "BUY")
            self.assertEqual(record["updates"], 2)
            self.assertEqual(record["tracker_status"], "OPEN")

    def test_close_moves_signal_out_of_open_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "open_signals.json"
            tracker = SignalTracker(path)
            tracker.upsert({"signal_id": "xyz", "symbol": "ETHUSDT"})
            self.assertTrue(tracker.close("xyz", "TEST_CLOSE"))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("xyz", saved["open_signals"])
            self.assertEqual(saved["closed_signals"]["xyz"]["close_reason"], "TEST_CLOSE")


if __name__ == "__main__":
    unittest.main()
