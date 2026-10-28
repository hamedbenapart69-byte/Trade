import os,unittest
from unittest.mock import patch
import httpx
from app.integrations.n8n import IntegrationConfigurationError,IntegrationDeliveryError,IntegrationDisabled,deliver_approved_payload

class N8nAdapterTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{"ENABLE_N8N_EXECUTION":"true","N8N_WEBHOOK_URL":"https://automation.example.test/webhook/secret-path","N8N_TIMEOUT_SECONDS":"8"},clear=False); self.env.start()
 def tearDown(self): self.env.stop()
 def test_disabled(self):
  with patch.dict(os.environ,{"ENABLE_N8N_EXECUTION":"false"}),self.assertRaises(IntegrationDisabled): deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={},idempotency_key="key-0001")
 def test_sends_payload_key_and_token(self):
  seen={}
  def handler(req): seen["body"]=req.read().decode(); seen["key"]=req.headers.get("Idempotency-Key"); seen["token"]=req.headers.get("X-Webhook-Token"); return httpx.Response(202,text="accepted")
  with patch.dict(os.environ,{"N8N_WEBHOOK_TOKEN":"test-secret"}):
   c=httpx.Client(transport=httpx.MockTransport(handler)); result=deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={"x":1},idempotency_key="key-0001",client=c); c.close()
  self.assertEqual(result.status_code,202); self.assertIn('"run_id":"r1"',seen["body"]); self.assertEqual(seen["key"],"key-0001"); self.assertEqual(seen["token"],"test-secret")
 def test_rejects_plain_http_external(self):
  with patch.dict(os.environ,{"N8N_WEBHOOK_URL":"http://automation.example.test/hook"}),self.assertRaises(IntegrationConfigurationError): deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={},idempotency_key="key-0001")
 def test_rejects_missing_url(self):
  with patch.dict(os.environ,{"N8N_WEBHOOK_URL":""}),self.assertRaises(IntegrationConfigurationError): deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={},idempotency_key="key-0001")
 def test_non_success_does_not_retry(self):
  calls=[]
  def handler(req): calls.append(1); return httpx.Response(503,text="unavailable")
  c=httpx.Client(transport=httpx.MockTransport(handler))
  with self.assertRaises(IntegrationDeliveryError): deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={},idempotency_key="key-0001",client=c)
  c.close(); self.assertEqual(len(calls),1)
 def test_timeout_bound(self):
  with patch.dict(os.environ,{"N8N_TIMEOUT_SECONDS":"90"}),self.assertRaises(IntegrationConfigurationError): deliver_approved_payload(run_id="r1",workflow="demo.flow",payload={},idempotency_key="key-0001")
if __name__=="__main__": unittest.main()
