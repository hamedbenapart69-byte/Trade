import os,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import store
from app.main import app

class ConsoleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); os.environ["CONTROL_DB_PATH"]=str(Path(self.tmp.name)/"console.db"); os.environ["CONTROL_API_TOKEN"]="console-test-token-long-enough-123456"; store.init_db(); self.client=TestClient(app); self.headers={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}
 def tearDown(self):
  self.client.close(); self.tmp.cleanup(); os.environ.pop("CONTROL_DB_PATH",None); os.environ.pop("CONTROL_API_TOKEN",None)
 def test_console_is_served_without_leaking_api_token(self):
  r=self.client.get("/"); self.assertEqual(r.status_code,200); self.assertIn("مرکز کنترل هوشمند",r.text); self.assertIn("localStorage",r.text.lower(),msg="UI must not persist credentials")
 def test_outbox_requires_operator_auth(self):
  self.assertEqual(self.client.get("/outbox").status_code,401)
  self.assertEqual(self.client.get("/outbox",headers=self.headers).status_code,200)
 def test_outbox_status_filter_validation(self):
  self.assertEqual(self.client.get("/outbox?status=not-real",headers=self.headers).status_code,400)
if __name__=="__main__": unittest.main()
