import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class DeliveryTests(unittest.TestCase):
    def test_publish_signals_writes_json_and_deduplicated_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/"latest.json"; out=root/"signals"
            payload={"schema_version":1,"status":"SCAN_COMPLETED","scan_id":"scan-1","scanned_at":"2026-11-08T10:00:00+00:00","screened_assets":12,"actionable":[{"symbol":"BTC-USDT-SWAP"}],"conditional":[]}
            source.write_text(json.dumps(payload),encoding="utf-8")
            cmd=[sys.executable,str(ROOT/"scripts"/"publish_signals.py"),"--source",str(source),"--output-dir",str(out)]
            subprocess.run(cmd,cwd=ROOT,check=True)
            subprocess.run(cmd,cwd=ROOT,check=True)
            self.assertEqual(json.loads((out/"signals.json").read_text(encoding="utf-8"))["scan_id"],"scan-1")
            with (out/"history.csv").open(encoding="utf-8",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["actionable_count"],"1")

    def test_notifier_silently_skips_without_secrets(self):
        env=os.environ.copy()
        env.pop("TELEGRAM_TOKEN",None);env.pop("TELEGRAM_CHAT_ID",None)
        result=subprocess.run([sys.executable,str(ROOT/"notifier.py")],cwd=ROOT,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertIn("skipped",result.stdout+result.stderr)

if __name__=="__main__":
    unittest.main()
