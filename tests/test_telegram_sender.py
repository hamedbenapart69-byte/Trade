import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import telegram_sender


class TelegramSenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "delivery.sqlite3"
        self.chart = self.root / "chart.png"
        self.chart.write_bytes(b"fake-image")

    def tearDown(self):
        self.temp.cleanup()

    def signal(self):
        return {
            "signal_id": "engine-a:BTCUSDT:2026-11-23T10:00:00Z:BUY",
            "symbol": "BTCUSDT", "direction": "BUY", "timeframe": "4h",
            "status": "CONDITIONAL_BUY", "generated_at": "2026-11-23T10:00:00Z",
            "hypothesis": "فرضیه نمونه", "entry": 90000, "stop_loss": 88000,
            "targets": [94000, 98000], "risk_reward": "2R / 4R",
            "confidence": "NOT_CALIBRATED", "calibration_status": "NOT_CALIBRATED",
            "invalidation": "بسته‌شدن کندل زیر حد ابطال", "chart": str(self.chart),
        }

    def test_caption_has_nine_parts(self):
        caption = telegram_sender.build_caption(telegram_sender.normalize_signal(self.signal()))
        self.assertEqual([line.split(")", 1)[0] for line in caption.splitlines()],
                         [str(i) for i in range(1, 10)])

    def test_duplicate_is_blocked(self):
        self.assertTrue(telegram_sender.reserve_delivery(self.db, "id-1", "a" * 64))
        self.assertFalse(telegram_sender.reserve_delivery(self.db, "id-1", "a" * 64))

    def test_definite_failure_can_retry(self):
        self.assertTrue(telegram_sender.reserve_delivery(self.db, "id-2", "b" * 64))
        telegram_sender.update_delivery(self.db, "id-2", "FAILED", error="rejected")
        self.assertTrue(telegram_sender.reserve_delivery(self.db, "id-2", "b" * 64))

    def test_unknown_delivery_is_not_retried(self):
        self.assertTrue(telegram_sender.reserve_delivery(self.db, "id-3", "c" * 64))
        telegram_sender.update_delivery(self.db, "id-3", "UNKNOWN", error="timeout")
        self.assertFalse(telegram_sender.reserve_delivery(self.db, "id-3", "c" * 64))


    def test_accepts_strategy_specific_direction_labels(self):
        signal = self.signal()
        signal["direction"] = "CONDITIONAL_BUY"
        normalized = telegram_sender.normalize_signal(signal)
        self.assertEqual(normalized["direction"], "CONDITIONAL_BUY")

    def test_sender_uses_existing_telegram_token_secret_and_skips_duplicate(self):
        signal_path = self.root / "signal.json"
        signal_path.write_text(json.dumps(self.signal()), encoding="utf-8")
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"}):
            with patch.object(telegram_sender, "telegram_send_photo", return_value="777") as send:
                first = telegram_sender.send_signal(signal_path, self.db)
                second = telegram_sender.send_signal(signal_path, self.db)
        self.assertEqual(first["status"], "SENT")
        self.assertEqual(second["status"], "DUPLICATE_SKIPPED")
        send.assert_called_once()


    def test_idempotency_hash_ignores_json_whitespace_and_key_order(self):
        signal_path = self.root / "signal.json"
        payload = self.signal()
        signal_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.dict(os.environ, {"TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "-100123"}):
            with patch.object(telegram_sender, "telegram_send_photo", return_value="778") as send:
                first = telegram_sender.send_signal(signal_path, self.db)
                signal_path.write_text(json.dumps(payload, indent=4, sort_keys=True), encoding="utf-8")
                second = telegram_sender.send_signal(signal_path, self.db)
        self.assertEqual(first["status"], "SENT")
        self.assertEqual(second["status"], "DUPLICATE_SKIPPED")
        send.assert_called_once()

    def test_payload_collision_is_rejected(self):
        self.assertTrue(telegram_sender.reserve_delivery(self.db, "id-4", "d" * 64))
        with self.assertRaises(ValueError):
            telegram_sender.reserve_delivery(self.db, "id-4", "e" * 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
