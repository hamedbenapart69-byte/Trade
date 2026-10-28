import os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from app import store
from app.main import app

class OutboxTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ["CONTROL_DB_PATH"]=str(Path(self.tmp.name)/"outbox.db"); os.environ["CONTROL_API_TOKEN"]="outbox-test-token-long-enough-123456"; os.environ["WORKER_API_TOKEN"]="worker-test-token-long-enough-123456"; store.init_db(); self.client=TestClient(app); self.headers={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}; self.worker_headers={"X-API-Key":os.environ["WORKER_API_TOKEN"]}
  r=self.client.post("/runs",json={"workflow":"sample.review","input":{"x":1}},headers={**self.headers,"Idempotency-Key":"outbox-run-0001"}); self.run_id=r.json()["id"]
 def tearDown(self):
  self.client.close(); self.tmp.cleanup(); os.environ.pop("CONTROL_DB_PATH",None); os.environ.pop("CONTROL_API_TOKEN",None); os.environ.pop("WORKER_API_TOKEN",None)
 def approve(self): return self.client.post(f"/runs/{self.run_id}/approve",json={"decided_by":"owner"},headers=self.headers)
 def test_cannot_queue_before_approval(self): self.assertEqual(self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).status_code,409)
 def test_queue_idempotent_lease_and_finish(self):
  self.assertEqual(self.approve().status_code,200); a=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers); b=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers); self.assertEqual(a.status_code,202); self.assertEqual(a.json()["id"],b.json()["id"])
  item=self.client.post("/internal/outbox/lease",headers=self.worker_headers).json()["item"]; self.assertEqual(item["status"],"leased"); self.assertEqual(item["workflow"],"sample.review")
  done=self.client.post(f"/internal/outbox/{item['id']}/finish",json={"lease_token":item["lease_token"],"succeeded":True,"result":{"test":"ok"}},headers=self.worker_headers); self.assertEqual(done.status_code,200); self.assertEqual(done.json()["status"],"completed"); self.assertIsNone(self.client.post("/internal/outbox/lease",headers=self.worker_headers).json()["item"])
 def test_stale_token_rejected(self):
  self.approve(); item=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).json(); self.client.post("/internal/outbox/lease",headers=self.worker_headers)
  r=self.client.post(f"/internal/outbox/{item['id']}/finish",json={"lease_token":"not-the-current-lease-token","succeeded":True,"result":{}},headers=self.worker_headers); self.assertEqual(r.status_code,409)
 def test_worker_token_cannot_approve_and_operator_token_cannot_lease(self):
  self.assertEqual(self.client.post(f"/runs/{self.run_id}/approve",json={"decided_by":"worker"},headers=self.worker_headers).status_code,401)
  self.assertEqual(self.client.post("/internal/outbox/lease",headers=self.headers).status_code,401)
 def test_lease_duration_bounded(self): self.assertEqual(self.client.post("/internal/outbox/lease?lease_seconds=2",headers=self.worker_headers).status_code,400)
 def test_expired_lease_becomes_unknown_not_auto_retried(self):
  self.approve(); item=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).json()
  now=datetime.now(timezone.utc)+timedelta(seconds=2)
  leased=store.lease_next_outbox(now=now.isoformat(),lease_until=(now+timedelta(seconds=10)).isoformat())
  self.assertEqual(leased["id"],item["id"])
  later=now+timedelta(seconds=20)
  self.assertIsNone(store.lease_next_outbox(now=later.isoformat(),lease_until=(later+timedelta(seconds=30)).isoformat()))
  with store.db_connection() as conn:
   status=conn.execute("SELECT status FROM execution_outbox WHERE id=?",(item["id"],)).fetchone()["status"]
  self.assertEqual(status,"unknown")
 def test_unknown_requires_explicit_reconciliation_before_retry(self):
  self.approve(); item=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).json()
  now=datetime.now(timezone.utc)+timedelta(seconds=2)
  store.lease_next_outbox(now=now.isoformat(),lease_until=(now+timedelta(seconds=10)).isoformat())
  later=now+timedelta(seconds=20)
  store.lease_next_outbox(now=later.isoformat(),lease_until=(later+timedelta(seconds=30)).isoformat())
  bad=self.client.post(f"/internal/outbox/{item['id']}/reconcile",json={"action":"retry","actor":"operator","note":"checked destination"},headers=self.headers)
  self.assertEqual(bad.status_code,200); self.assertEqual(bad.json()["status"],"queued")
  leased=self.client.post("/internal/outbox/lease",headers=self.worker_headers).json()["item"]; self.assertEqual(leased["id"],item["id"])
if __name__=="__main__": unittest.main()

