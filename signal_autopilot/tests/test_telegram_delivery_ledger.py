"""آزمون‌های دفتر پایدار تحویل اعلان تلگرام."""
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.telegram_delivery_ledger import claim_delivery, finalize_delivery


class TelegramDeliveryLedgerTests(unittest.TestCase):
    def _state(self, root: Path) -> Path:
        path = root / "telegram_deliveries.json"
        path.write_text(
            json.dumps({"schema_version": 1, "deliveries": {}}),
            encoding="utf-8",
        )
        return path

    def test_first_claim_succeeds_and_duplicate_claim_is_suppressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp))
            self.assertTrue(claim_delivery(path, "run-123"))
            self.assertFalse(claim_delivery(path, "run-123"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["deliveries"]["run-123"]["status"], "CLAIMED")

    def test_successful_delivery_is_finalized_and_cannot_be_claimed_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp))
            self.assertTrue(claim_delivery(path, "run-123"))
            status = finalize_delivery(path, "run-123", "success")
            self.assertEqual(status, "SENT")
            self.assertFalse(claim_delivery(path, "run-123"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["deliveries"]["run-123"]["status"], "SENT")

    def test_ambiguous_failure_is_not_automatically_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp))
            self.assertTrue(claim_delivery(path, "run-456"))
            status = finalize_delivery(path, "run-456", "failure")
            self.assertEqual(status, "DELIVERY_UNCONFIRMED")
            self.assertFalse(claim_delivery(path, "run-456"))

    def test_finalize_requires_existing_unfinalized_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp))
            with self.assertRaisesRegex(ValueError, "delivery_claim_not_found"):
                finalize_delivery(path, "missing", "success")
            claim_delivery(path, "run-789")
            finalize_delivery(path, "run-789", "success")
            with self.assertRaisesRegex(ValueError, "delivery_claim_not_found"):
                finalize_delivery(path, "run-789", "success")

    def test_rejects_invalid_ledger_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"schema_version": 2, "deliveries": {}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "delivery_ledger_schema_invalid"):
                claim_delivery(path, "run-1")

    def test_requires_timezone_aware_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._state(Path(tmp))
            with self.assertRaisesRegex(ValueError, "ledger_clock_must_be_timezone_aware"):
                claim_delivery(path, "run-1", now=datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
