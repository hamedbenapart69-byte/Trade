"""تست‌های Mock برای فرمت و مقصد ایزولهٔ وضعیت قرنطینه تلگرام."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from modules.notifier import (
    _format_legacy_quarantine_status,
    _format_signal,
    notify_tier_a,
    send_legacy_quarantine_status_test,
)


QUARANTINE = {
    "lifecycle": "LEGACY_RESEARCH_ONLY",
    "production_enabled": False,
}


class TelegramMockContractTests(unittest.TestCase):
    def test_quarantine_message_is_explicit_and_does_not_claim_live_scan(self):
        message = _format_legacy_quarantine_status(QUARANTINE)
        self.assertIn("LEGACY_RESEARCH_ONLY", message)
        self.assertIn("production_enabled: false", message)
        self.assertIn("NO_QUALIFIED_SETUP", message)
        self.assertIn("اسکن زنده بازار نیست", message)

    def test_invalid_quarantine_state_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "LEGACY_QUARANTINE_STATE_INVALID"):
            _format_legacy_quarantine_status({
                "lifecycle": "ACTIVE",
                "production_enabled": True,
            })

    def test_status_test_sender_uses_only_test_chat_id(self):
        env = {
            "GITHUB_EVENT_NAME": "push",
            "TELEGRAM_TOKEN": "MOCK_TOKEN",
            "TELEGRAM_TEST_CHAT_ID": "-100000000001",
            "TELEGRAM_CHAT_ID": "-100000000099",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("modules.notifier._send", new_callable=AsyncMock, return_value=[77]) as send:
                result = send_legacy_quarantine_status_test(QUARANTINE)

        self.assertEqual(result, {"status": "TEST_SENT", "sent": 1})
        self.assertEqual(send.await_args.args[1], "-100000000001")
        self.assertIn("NO_QUALIFIED_SETUP", send.await_args.args[2][0])

    def test_status_sender_skips_without_test_channel(self):
        env = {
            "GITHUB_EVENT_NAME": "push",
            "TELEGRAM_TOKEN": "MOCK_TOKEN",
            "TELEGRAM_TEST_CHAT_ID": "",
            "TELEGRAM_CHAT_ID": "-100000000099",
        }
        with patch.dict(os.environ, env, clear=False):
            result = send_legacy_quarantine_status_test(QUARANTINE)
        self.assertEqual(result, {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0})

    def test_live_test_workflow_is_manual_and_uses_only_test_chat_secret(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github" / "workflows" / "telegram-quarantine-test.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("TELEGRAM_TEST_CHAT_ID", workflow)
        self.assertIn("TELEGRAM_TOKEN", workflow)
        self.assertNotIn("secrets.TELEGRAM_CHAT_ID", workflow)
        self.assertIn("send_legacy_quarantine_status_test", workflow)

    def test_normal_signal_formatter_and_delivery_are_mocked_without_network(self):
        payload = {
            "generated_at_utc": "2026-11-10T00:00:00+00:00",
            "signals": [{
                "symbol": "BTCUSDT", "status": "BUY_NOW", "entry": 100.0,
                "stop_loss": 98.0, "take_profit": [103.0, 105.0],
                "timeframe": "1H", "reason": "mock reason",
                "hypothesis": "mock hypothesis", "falsification": "mock invalidation",
            }],
        }
        formatted = _format_signal(payload["signals"][0], payload)
        self.assertIn("BTCUSDT", formatted)
        self.assertIn("ورود: 100.0", formatted)
        self.assertIn("حد ضرر: 98.0", formatted)
        self.assertIn("فرضیه: mock hypothesis", formatted)

        with tempfile.TemporaryDirectory() as temp:
            env = {
                "GITHUB_EVENT_NAME": "push",
                "TELEGRAM_TOKEN": "MOCK_TOKEN",
                "TELEGRAM_CHAT_ID": "-100000000099",
                "TELEGRAM_AUDIENCE_CHANNEL_ID": "",
                "TELEGRAM_STATE_PATH": str(Path(temp) / "sent.json"),
            }
            with patch.dict(os.environ, env, clear=False):
                with patch("modules.notifier._send", new_callable=AsyncMock, return_value=[88]) as send:
                    result = notify_tier_a(payload)

            self.assertEqual(result["status"], "SENT")
            self.assertEqual(send.await_args.args[1], "-100000000099")
            self.assertTrue((Path(temp) / "sent.json").exists())


if __name__ == "__main__":
    unittest.main()
