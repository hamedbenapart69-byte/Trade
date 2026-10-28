import os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app import store
from scripts.backup_db import main

class BackupTests(unittest.TestCase):
 def test_backup_restorable_and_checked(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/"source.db"; backup=Path(tmp)/"nested"/"backup.db"
   with patch.dict(os.environ,{"CONTROL_DB_PATH":str(source)}):
    store.init_db(); store.insert_run(run_id="run-backup",idempotency_key="backup-key-0001",workflow="sample.review",payload={"safe":True},created_at="2026-01-01T00:00:00+00:00")
    with patch("sys.argv",["backup_db.py",str(backup)]): self.assertEqual(main(),0)
   with sqlite3.connect(str(backup)) as conn:
    self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok"); self.assertEqual(conn.execute("SELECT id FROM runs").fetchone()[0],"run-backup"); self.assertEqual(conn.execute("SELECT event_type FROM run_events").fetchone()[0],"created")
   # Open the backup as a fresh restored database and verify application-level reads.
   with patch.dict(os.environ,{"CONTROL_DB_PATH":str(backup)}):
    store.init_db()
    restored=store.get_runs()
    self.assertEqual(restored["total"],1)
    self.assertEqual(restored["items"][0]["id"],"run-backup")
 def test_missing_source(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"CONTROL_DB_PATH":str(Path(tmp)/"missing.db")}): self.assertEqual(main(),2)
if __name__=="__main__": unittest.main()
