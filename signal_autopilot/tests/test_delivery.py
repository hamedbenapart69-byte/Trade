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
        self.assertIn("NOT_CALIBRATED",message)
        self.assertIn("ورود: —",message)
        self.assertIn("SL: —",message)
        self.assertIn("LFS=NOT_CALCULABLE",message)

    def test_telegram_silently_skips_without_credentials(self):
        from modules.notifier import notify_tier_a, send_test_message
        with patch.dict("os.environ",{},clear=True):
            self.assertEqual(notify_tier_a({"signals":[]})["status"],"SKIPPED_NOT_CONFIGURED")
            self.assertEqual(send_test_message()["status"],"SKIPPED_NOT_CONFIGURED")

if __name__=="__main__":
    unittest.main()
