import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
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
 def test_signal_dashboard_html_is_public_and_rtl(self):
  r=self.client.get("/signals-ui")
  self.assertEqual(r.status_code,200)
  self.assertIn('dir="rtl"',r.text)
  self.assertIn("FUTURES SIGNAL AUTOPILOT",r.text)
 def test_signal_dashboard_data_is_public_read_only_and_limited(self):
  sample={"status":"SCAN_COMPLETED","scanned_at":"2026-11-07T00:00:00+00:00","scan_id":"audit-test",
   "coverage":{"screened":30,"insufficient_data":0,"rejected":30},"screened_assets":30,
   "actionable":[{"symbol":"BTCUSDT","decision":"BUY_NOW","direction":"LONG","entry":100.0,"stop_loss":98.5,
    "take_profit":103.0,"stop_pct":1.5,"risk":{"required_leverage":1.33,"planned_loss_usd":4.0},
    "data_grade":"B","confidence_v5":75}],"conditional":[],
   "validation_context":{"execution":"GitHub-hosted runner","fixture_data":False},
   "limitations":[]}
  with patch("app.main.latest_scan",return_value=sample), patch("app.main.performance",return_value={"mode":"paper_signal_tracking_not_executed_trades","published_signals":0}):
   r=self.client.get("/signals/dashboard-data")
  self.assertEqual(r.status_code,200)
  body=r.json()
  self.assertEqual(body["scan_id"],"audit-test")
  self.assertEqual(body["actionable"][0]["decision"],"BUY_NOW")
  self.assertNotIn("other_candidates",body)
  self.assertNotIn("data_json",body)
  self.assertNotIn("account_credentials",r.text)
 def test_signal_scan_write_route_still_requires_api_key(self):
  r=self.client.post("/signals/scan")
  self.assertEqual(r.status_code,401)

 def test_signal_status_does_not_reuse_stale_historical_scan_claims(self):
  with patch("app.signals.latest_scan",return_value=None):
   r=self.client.get("/signals/status",headers={"X-API-Key":os.environ["CONTROL_API_TOKEN"]})
  self.assertEqual(r.status_code,200)
  body=r.json()
  self.assertEqual(body["status"],"NO_SCAN_YET")
  self.assertFalse(body["full_live_scan_verified"])
  self.assertFalse(body["live_rest_access_verified"])
  self.assertIsNone(body["last_full_live_scan_utc"])

if __name__=="__main__": unittest.main()
