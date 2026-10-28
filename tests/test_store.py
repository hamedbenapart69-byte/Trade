import os,tempfile,unittest
from pathlib import Path
from app import store

class StoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ["CONTROL_DB_PATH"]=str(Path(self.tmp.name)/"test.db"); store.init_db()
 def tearDown(self): self.tmp.cleanup(); os.environ.pop("CONTROL_DB_PATH",None)
 def create(self,key="idempotency-001",payload=None): return store.insert_run(run_id="run-1",idempotency_key=key,workflow="sample.review",payload=payload or {"text":"safe"},created_at="2026-01-01T00:00:00+00:00")
 def test_persist_and_hide_key(self):
  r=self.create(); self.assertEqual(store.get_run(r["id"])["status"],"pending_approval"); self.assertNotIn("idempotency_key",r)
 def test_idempotent_same_request(self): self.assertEqual(self.create()["id"],self.create()["id"])
 def test_conflict_different_payload(self):
  self.create()
  with self.assertRaisesRegex(ValueError,"idempotency_key_conflict"): self.create(payload={"text":"different"})
 def test_single_use_approval(self):
  self.create(); store.decide_run("run-1",decision="approved",decided_by="owner",note=None,decided_at="2026-01-01T00:01:00+00:00")
  with self.assertRaisesRegex(ValueError,"run_already_decided"): store.decide_run("run-1",decision="rejected",decided_by="owner",note=None,decided_at="2026-01-01T00:02:00+00:00")
 def test_rejection_persisted(self):
  self.create(); r=store.decide_run("run-1",decision="rejected",decided_by="owner",note="not safe",decided_at="2026-01-01T00:01:00+00:00"); self.assertEqual(r["decision_note"],"not safe")
 def test_missing_run(self): self.assertIsNone(store.get_run("missing"))
if __name__=="__main__": unittest.main()
