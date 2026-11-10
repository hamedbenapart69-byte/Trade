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


    def test_real_message_id_is_written_to_snapshot_and_signal(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            async def fake_send(token, chat_id, messages):
                return [987654]
            payload = {
                "pipeline_status": "OK",
                "generated_at_utc": "2026-11-08T12:00:00+00:00",
                "signals": [{
                    "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                    "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
                }],
            }
            with patch.dict(os.environ, {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }, clear=True), patch("modules.notifier._send", new=fake_send):
                notify_tier_a(payload)
            self.assertEqual(payload["message_id_current"], {"BTC/USDT:USDT": 987654})
            self.assertIsNone(payload["message_id_audience"])
            self.assertIsNotNone(payload["published_at"])
            self.assertEqual(payload["signals"][0]["message_id_current"], 987654)
            self.assertEqual(payload["signals"][0]["published_at"], payload["published_at"])

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


    def test_same_signal_is_not_resent_when_generated_timestamp_changes(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.extend(messages)
                return [100 + len(sent)]
            env = {
                "TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }
            base_signal = {
                "signal_id": "EMA_TREND_CONTINUATION_MVP:1H",
                "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
            }
            with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
                first = notify_tier_a({"generated_at_utc":"2026-11-10T10:00:00+00:00","signals":[dict(base_signal)]})
                second = notify_tier_a({"generated_at_utc":"2026-11-10T14:00:00+00:00","signals":[dict(base_signal)]})
            self.assertEqual(first["status"], "SENT")
            self.assertEqual(second, {"status":"NO_NEW_MESSAGES","sent":0})
            self.assertEqual(len(sent), 1)

    def test_same_signal_resends_only_when_entry_sl_or_tp_changes(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.extend(messages)
                return [200 + len(sent)]
            env = {
                "TELEGRAM_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "12345",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }
            base = {
                "signal_id": "EMA_TREND_CONTINUATION_MVP:1H",
                "symbol": "ETH/USDT:USDT", "status": "SELL_NOW", "side": "SELL",
                "entry": 200, "stop_loss": 210, "take_profit": [180, 160],
            }
            changed = dict(base, entry=201)
            with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
                first = notify_tier_a({"generated_at_utc":"2026-11-10T10:00:00+00:00","signals":[base]})
                second = notify_tier_a({"generated_at_utc":"2026-11-10T14:00:00+00:00","signals":[changed]})
            self.assertEqual(first["status"], "SENT")
            self.assertEqual(second["status"], "SENT")
            self.assertEqual(len(sent), 2)


    def test_current_and_audience_channels_have_independent_idempotency(self):
        import os
        from modules.notifier import notify_tier_a
        with tempfile.TemporaryDirectory() as tmp:
            sent = []
            async def fake_send(token, chat_id, messages):
                sent.append((chat_id, list(messages)))
                return [1000 + len(sent)]
            env = {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "-100-current",
                "TELEGRAM_AUDIENCE_CHANNEL_ID": "-100-audience",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }
            payload = {
                "pipeline_status": "OK",
                "generated_at_utc": "2026-11-10T16:00:00+00:00",
                "signals": [{
                    "signal_id": "EMA_TREND_CONTINUATION_MVP:1H",
                    "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                    "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
                }],
            }
            with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
                first = notify_tier_a(payload)
                current_ids = payload["message_id_current"]
                audience_ids = payload["message_id_audience"]
                second = notify_tier_a({
                    "pipeline_status": "OK",
                    "generated_at_utc": "2026-11-10T16:04:00+00:00",
                    "signals": [{
                        "signal_id": "EMA_TREND_CONTINUATION_MVP:1H",
                        "symbol": "BTC/USDT:USDT", "status": "BUY_NOW", "side": "BUY",
                        "entry": 100, "stop_loss": 95, "take_profit": [110, 120],
                    }],
                })
            self.assertEqual(first["status"], "SENT")
            self.assertEqual(first["sent"], 2)
            self.assertEqual(second["status"], "NO_NEW_MESSAGES")
            self.assertEqual(second["sent"], 0)
            self.assertEqual({chat for chat, _ in sent}, {"-100-current", "-100-audience"})
            self.assertIsNotNone(current_ids)
            self.assertIsNotNone(audience_ids)
            state = json.loads((Path(tmp) / "sent.json").read_text(encoding="utf-8"))
            self.assertEqual(state["__schema_version__"], 3)
            self.assertIn("signals", state["destinations"]["current"])
            self.assertIn("signals", state["destinations"]["audience"])

    def test_audience_delivery_continues_if_current_channel_fails(self):
        import os
        from modules.notifier import notify_tier_a
        async def fake_send(token, chat_id, messages):
            if chat_id == "-100-current":
                raise RuntimeError("Chat not found")
            return [2001]
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "TELEGRAM_TOKEN": "test-token",
                "TELEGRAM_CHAT_ID": "-100-current",
                "TELEGRAM_AUDIENCE_CHANNEL_ID": "-100-audience",
                "TELEGRAM_STATE_PATH": str(Path(tmp) / "sent.json"),
            }
            payload = {
                "pipeline_status": "OK",
                "generated_at_utc": "2026-11-10T16:00:00+00:00",
                "signals": [{
                    "signal_id": "EMA_TREND_CONTINUATION_MVP:1H",
                    "symbol": "ETH/USDT:USDT", "status": "SELL_NOW", "side": "SELL",
                    "entry": 200, "stop_loss": 210, "take_profit": [180, 160],
                }],
            }
            with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
                result = notify_tier_a(payload)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["sent"], 1)
            self.assertEqual(result["destinations"]["current"]["status"], "CHAT_NOT_FOUND")
            self.assertEqual(result["destinations"]["audience"]["status"], "SENT")
            self.assertEqual(payload["message_id_audience"], {"ETH/USDT:USDT": 2001})

    def test_send_test_message_targets_both_configured_channels(self):
        import os
        from modules.notifier import send_test_message
        calls = []
        async def fake_send(token, chat_id, messages):
            calls.append(chat_id)
            return [3000 + len(calls)]
        env = {
            "TELEGRAM_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "-100-current",
            "TELEGRAM_AUDIENCE_CHANNEL_ID": "-100-audience",
        }
        with patch.dict(os.environ, env, clear=True), patch("modules.notifier._send", new=fake_send):
            result = send_test_message()
        self.assertEqual(result, {"status": "TEST_SENT", "sent": 2})
        self.assertEqual(calls, ["-100-current", "-100-audience"])

if __name__=="__main__":
    unittest.main()
