import logging, os, unittest
from fastapi.testclient import TestClient
from app.main import app

class ObservabilitySecurityTests(unittest.TestCase):
 def setUp(self):
  os.environ["CONTROL_API_TOKEN"]="observability-control-token-long-123456"
  self.client=TestClient(app)
 def tearDown(self):
  self.client.close(); os.environ.pop("CONTROL_API_TOKEN",None)
 def test_access_log_redacts_query_and_credentials(self):
  secret="do-not-log-this-secret-987654"
  with self.assertLogs("control.access",level="INFO") as captured:
   response=self.client.get("/health?api_key="+secret,headers={"X-API-Key":secret,"X-Request-ID":"safe-request-123"})
  self.assertEqual(response.status_code,200)
  self.assertEqual(response.headers["X-Request-ID"],"safe-request-123")
  joined=" ".join(captured.output)
  self.assertIn("http_request",joined)
  self.assertIn("safe-request-123",joined)
  self.assertNotIn(secret,joined)
  self.assertNotIn("api_key",joined)
 def test_invalid_request_id_is_replaced(self):
  response=self.client.get("/health",headers={"X-Request-ID":"secret with spaces"})
  self.assertRegex(response.headers["X-Request-ID"],r"^[0-9a-f-]{36}$")
if __name__=="__main__": unittest.main()
