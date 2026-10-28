import os,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import store
from app.main import app

class OutboxTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ["CONTROL_DB_PATH"]=str(Path(self.tmp.name)/"outbox.db"); os.environ["CONTROL_API_TOKEN"]="outbox-test-token-long-enough-123456"; store.init_db(); self.client=TestClient(app); self.headers={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}
  r=self.client.post("/runs",json={"workflow":"sample.review","input":{"x":1}},headers={**self.headers,"Idempotency-Key":"outbox-run-0001"}); self.run_id=r.json()["id"]
 def tearDown(self):
  self.client.close(); self.tmp.cleanup(); os.environ.pop("CONTROL_DB_PATH",None); os.environ.pop("CONTROL_API_TOKEN",None)
 def approve(self): return self.client.post(f"/runs/{self.run_id}/approve",json={"decided_by":"owner"},headers=self.headers)
 def test_cannot_queue_before_approval(self): self.assertEqual(self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).status_code,409)
 def test_queue_idempotent_lease_and_finish(self):
  self.assertEqual(self.approve().status_code,200); a=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers); b=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers); self.assertEqual(a.status_code,202); self.assertEqual(a.json()["id"],b.json()["id"])
  item=self.client.post("/internal/outbox/lease",headers=self.headers).json()["item"]; self.assertEqual(item["status"],"leased"); self.assertEqual(item["workflow"],"sample.review")
  done=self.client.post(f"/internal/outbox/{item['id']}/finish",json={"lease_token":item["lease_token"],"succeeded":True,"result":{"test":"ok"}},headers=self.headers); self.assertEqual(done.status_code,200); self.assertEqual(done.json()["status"],"completed"); self.assertIsNone(self.client.post("/internal/outbox/lease",headers=self.headers).json()["item"])
 def test_stale_token_rejected(self):
  self.approve(); item=self.client.post(f"/runs/{self.run_id}/queue",headers=self.headers).json(); self.client.post("/internal/outbox/lease",headers=self.headers)
  r=self.client.post(f"/internal/outbox/{item['id']}/finish",json={"lease_token":"not-the-current-lease-token","succeeded":True,"result":{}},headers=self.headers); self.assertEqual(r.status_code,409)
 def test_lease_duration_bounded(self): self.assertEqual(self.client.post("/internal/outbox/lease?lease_seconds=2",headers=self.headers).status_code,400)
if __name__=="__main__": unittest.main()
