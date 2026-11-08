import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class IsolatedSignalsBranchTests(unittest.TestCase):
    def test_snapshot_and_history_are_merged_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/"branch"; out.mkdir()
            (out/"signals.json").write_text(json.dumps({"generated_at_utc":"2026-11-08T08:00:00+00:00","signals":[]}),encoding="utf-8")
            fields=["generated_at_utc","symbol","status","side","tier","provider","engine","reason","confidence","ev_net","idempotency_key"]
            with (out/"history.csv").open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                writer.writerow({"generated_at_utc":"2026-11-08T08:00:00+00:00","symbol":"BTC/USDT:USDT","status":"WATCHLIST","idempotency_key":"old"})
            payload={"generated_at_utc":"2026-11-08T12:00:00+00:00","signals":[{"symbol":"ETH/USDT:USDT"}]}
            src_json=root/"signals.json";src_json.write_text(json.dumps(payload),encoding="utf-8")
            src_csv=root/"history.csv"
            with src_csv.open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                writer.writerow({"generated_at_utc":"2026-11-08T12:00:00+00:00","symbol":"ETH/USDT:USDT","status":"NO_QUALIFIED_SETUP","idempotency_key":"new"})
                writer.writerow({"generated_at_utc":"2026-11-08T12:00:00+00:00","symbol":"ETH/USDT:USDT","status":"NO_QUALIFIED_SETUP","idempotency_key":"new"})
            subprocess.run([sys.executable,str(ROOT/"scripts"/"publish_signals_branch.py"),"--source-json",str(src_json),"--source-csv",str(src_csv),"--output-dir",str(out)],cwd=ROOT,check=True)
            self.assertEqual(json.loads((out/"signals.json").read_text(encoding="utf-8"))["generated_at_utc"],payload["generated_at_utc"])
            with (out/"history.csv").open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
            self.assertEqual({r["idempotency_key"] for r in rows},{"old","new"})

    def test_telegram_message_never_invents_calibrated_probability(self):
        from modules.notifier import _format_signal
        message=_format_signal({"symbol":"BTC/USDT:USDT","status":"BUY_NOW","side":"LONG","entry":None,"stop_loss":None,"take_profit":[],"tier":"A","confidence":"NOT_CALIBRATED","lfs":"NOT_CALCULABLE","nss":"NOT_CALCULATED","falsification":"break of support"}, {})
        self.assertIn("نماد: BTC/USDT:USDT",message)
        self.assertIn("ورود: —",message)
        self.assertIn("حد ضرر: —",message)
        self.assertNotIn("NOT_CALIBRATED",message)

    def test_telegram_silently_skips_without_credentials(self):
        from modules.notifier import notify_tier_a, send_test_message
        with patch.dict("os.environ",{},clear=True):
            self.assertEqual(notify_tier_a({"signals":[]})["status"],"SKIPPED_NOT_CONFIGURED")
            self.assertEqual(send_test_message()["status"],"SKIPPED_NOT_CONFIGURED")

    def test_actionable_signal_without_tier_is_sent_to_telegram(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.extend(messages)
            with patch.dict(os.environ, {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }, clear=True), patch("modules.notifier._send", new=fake_send):
                result = notify_tier_a({
                    "pipeline_status": "OK",
                    "generated_at_utc": "2026-11-08T12:00:00+00:00",
                    "signals": [{
                        "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                        "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
                    }],
                })
            self.assertEqual(result, {"status": "SENT", "sent": 1})
            self.assertIn("ورود: 100", sent[0])

    def test_daily_no_signal_message_is_sent_once(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.extend(messages)
            env = {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }
            payload = {
                "pipeline_status": "OK",
                "generated_at_utc": "2026-11-08T12:00:00+00:00",
                "signals": [{"symbol": "BTC", "status": "NO_QUALIFIED_SETUP"}],
            }
            with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
                first = notify_tier_a(payload)
                second = notify_tier_a(payload)
            self.assertEqual(first, {"status": "SENT", "sent": 1})
            self.assertEqual(second, {"status": "NO_NEW_MESSAGES", "sent": 0})
            self.assertEqual(sent, ["امروز سیگنال نیست"])



    def test_email_fallback_sends_only_with_configured_sender_and_recipient(self):
        import os
        from modules.notifier import notify_email
        payload = {
            "generated_at_utc": "2026-11-08T12:00:00+00:00",
            "signals": [{
                "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
            }],
        }
        class FakeSMTP:
            sent_message = None
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def login(self, username, password): self.credentials = (username, password)
            def send_message(self, message): FakeSMTP.sent_message = message
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "465",
            "SMTP_USER": "from@example.test", "SMTP_PASSWORD": "test-app-password",
            "ALERT_EMAIL_TO": "to@example.test",
        }, clear=True), patch("modules.notifier.smtplib.SMTP_SSL", FakeSMTP):
            result = notify_email(payload)
        self.assertEqual(result, {"status": "SENT", "sent": 1})
        self.assertEqual(FakeSMTP.sent_message["To"], "to@example.test")
        self.assertIn(chr(10) + "جهت:", FakeSMTP.sent_message.get_content())

    def test_signal_message_uses_real_newline_characters(self):
        from modules.notifier import _format_signal
        message = _format_signal({
            "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "entry": 100,
            "stop_loss": 95, "take_profit": [110, 120],
        }, {})
        self.assertIn(chr(10), message)
        self.assertNotIn(chr(92) + "n", message)

    def test_multiple_actionable_signals_are_aggregated_into_one_message(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.extend(messages)
            payload = {
                "pipeline_status": "DEGRADED",
                "generated_at_utc": "2026-11-08T12:00:00+00:00",
                "quality": {"symbols_requested": 100, "symbols_processed": 26},
                "signals": [
                    {"symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                     "entry": 100, "stop_loss": 95, "take_profit": [110, 120]},
                    {"symbol": "ETH/USDT:USDT", "status": "SELL_NOW", "side": "SELL",
                     "entry": 200, "stop_loss": 210, "take_profit": [180, 160]},
                ],
            }
            with patch.dict(os.environ, {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }, clear=True), patch("modules.notifier._send", new=fake_send):
                result = notify_tier_a(payload)
            self.assertEqual(result, {"status": "SENT", "sent": 1})
            self.assertEqual(len(sent), 1)
            self.assertIn("BTC/USDT:USDT", sent[0])
            self.assertIn("ETH/USDT:USDT", sent[0])
            self.assertIn("26/100", sent[0])

    def test_chat_not_found_returns_actionable_status(self):
        import os
        from modules.notifier import notify_tier_a
        async def fail_send(token, chat_id, messages):
            raise RuntimeError("Chat not found")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }, clear=True), patch("modules.notifier._send", new=fail_send):
                result = notify_tier_a({
                    "pipeline_status": "OK",
                    "generated_at_utc": "2026-11-08T12:00:00+00:00",
                    "signals": [{
                        "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                        "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
                    }],
                })
        self.assertEqual(result, {"status": "CHAT_NOT_FOUND", "sent": 0})

if __name__=="__main__":
    unittest.main()
