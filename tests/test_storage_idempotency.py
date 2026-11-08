import csv
import tempfile
import unittest
from pathlib import Path
from modules.storage import publish

class StorageIdempotencyTests(unittest.TestCase):
    def test_same_four_hour_bucket_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            base={"provider":"okx","engine":"placeholder","signals":[{"symbol":"BTC/USDT:USDT",
              "status":"NO_QUALIFIED_SETUP","side":None,"tier":"NONE","reason":"test",
              "confidence":"NOT_CALIBRATED","ev_net":"NOT_CALIBRATED"}]}
            first=dict(base,generated_at_utc="2026-11-08T12:01:00+00:00")
            second=dict(base,generated_at_utc="2026-11-08T15:59:00+00:00")
            publish(first,root=str(root))
            publish(second,root=str(root))
            with (root/"data/history.csv").open(encoding="utf-8",newline="") as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["idempotency_key"],"2026-11-08T12:00:00+00:00|BTC/USDT:USDT|placeholder")
            self.assertTrue((root/"web/data/signals.json").exists())

if __name__=="__main__": unittest.main()
