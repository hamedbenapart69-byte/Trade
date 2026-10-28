import os,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import store

class ApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ["CONTROL_DB_PATH"]=str(Path(self.tmp.name)/"api.db"); os.environ["CONTROL_API_TOKEN"]="test-secret-token-long-enough-123456"; store.init_db(); self.client=TestClient(app)
 def tearDown(self):
  self.client.close(); self.tmp.cleanup(); os.environ.pop("CONTROL_DB_PATH",None); os.environ.pop("CONTROL_API_TOKEN",None)
 def headers(self,key="request-0001"): return {"X-API-Key":os.environ["CONTROL_API_TOKEN"],"Idempotency-Key":key}
 def test_health_public(self):
  r=self.client.get("/health"); self.assertEqual(r.status_code,200); self.assertNotIn("token",r.text.lower())
 def test_api_key_required(self):
  r=self.client.post("/runs",json={"workflow":"sample.review","input":{}},headers={"Idempotency-Key":"request-0001"}); self.assertEqual(r.status_code,401)
 def test_create_idempotent_and_approve(self):
  p={"workflow":"sample.review","input":{"text":"hello"}}; a=self.client.post("/runs",json=p,headers=self.headers()); b=self.client.post("/runs",json=p,headers=self.headers()); self.assertEqual(a.status_code,201); self.assertEqual(a.json()["id"],b.json()["id"])
  rid=a.json()["id"]; h={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}; approved=self.client.post(f"/runs/{rid}/approve",json={"decided_by":"owner"},headers=h); self.assertEqual(approved.json()["status"],"approved"); again=self.client.post(f"/runs/{rid}/reject",json={"decided_by":"owner"},headers=h); self.assertEqual(again.status_code,409)
 def test_list_filter_and_pagination(self):
  self.client.post("/runs",json={"workflow":"sample.review","input":{}},headers=self.headers("list-run-001")); h={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}; r=self.client.get("/runs?status=pending_approval",headers=h); self.assertEqual(r.json()["total"],1); self.assertEqual(self.client.get("/runs?limit=1000",headers=h).status_code,400)
 def test_cancel_audited(self):
  c=self.client.post("/runs",json={"workflow":"sample.review","input":{}},headers=self.headers("cancel-run-001")); rid=c.json()["id"]; h={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}; r=self.client.post(f"/runs/{rid}/cancel",json={"decided_by":"owner","note":"stop"},headers=h); self.assertEqual(r.json()["status"],"cancelled"); events=self.client.get(f"/runs/{rid}/events",headers=h); self.assertEqual([x["type"] for x in events.json()["items"]],["created","cancelled"])
 def test_rejects_invalid_payload(self):
  r=self.client.post("/runs",json={"workflow":"x","unexpected":True},headers=self.headers()); self.assertEqual(r.status_code,422)
 def test_run_input_size_limit(self):
  oversized={"text":"x"*33000}
  r=self.client.post("/runs",json={"workflow":"sample.review","input":oversized},headers=self.headers("oversize-0001"))
  self.assertEqual(r.status_code,413)
  self.assertEqual(r.json()["detail"],"run_input_too_large_max_32768_bytes")
 def test_idempotency_conflict(self):
  h=self.headers("request-0002"); self.client.post("/runs",json={"workflow":"sample.review","input":{"v":1}},headers=h); r=self.client.post("/runs",json={"workflow":"sample.review","input":{"v":2}},headers=h); self.assertEqual(r.status_code,409)
if __name__=="__main__": unittest.main()
