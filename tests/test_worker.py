import os,unittest
import httpx
from worker import run_once,WorkerConfigurationError

class WorkerTests(unittest.TestCase):
 def setUp(self):
  self.old={k:os.environ.get(k) for k in ["ENABLE_WORKER_EXECUTION","CONTROL_API_URL","WORKER_API_TOKEN","WORKER_ALLOWED_WORKFLOWS"]}
  os.environ.update({"ENABLE_WORKER_EXECUTION":"true","CONTROL_API_URL":"https://control.test","WORKER_API_TOKEN":"worker-test-token-long-enough-123456","WORKER_ALLOWED_WORKFLOWS":"sample.review"})
 def tearDown(self):
  for k,v in self.old.items():
   if v is None: os.environ.pop(k,None)
   else: os.environ[k]=v
 def test_disabled_by_default(self):
  os.environ["ENABLE_WORKER_EXECUTION"]="false"
  with self.assertRaises(WorkerConfigurationError): run_once()
 def test_remote_plain_http_is_rejected_before_sending_worker_token(self):
  os.environ["CONTROL_API_URL"]="http://control.example"
  with self.assertRaises(WorkerConfigurationError): run_once()
 def test_idle_queue(self):
  client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={"item":None})))
  self.assertEqual(run_once(client=client),"idle"); client.close()
 def test_allowlisted_workflow_delivered_then_finished(self):
  seen=[]
  def handler(req):
   seen.append(req)
   if req.url.path.endswith("/lease"):
    return httpx.Response(200,json={"item":{"id":"out-1","run_id":"run-1","workflow":"sample.review","input":{"a":1},"lease_token":"x"*36}})
   return httpx.Response(200,json={"status":"completed"})
  client=httpx.Client(transport=httpx.MockTransport(handler))
  def deliverer(**kw):
   self.assertEqual(kw["idempotency_key"],"run-1")
   return type("Result",(),{"status_code":200,"response_text":"ok"})()
  self.assertEqual(run_once(client=client,deliverer=deliverer),"completed")
  self.assertEqual(len(seen),2); self.assertEqual(seen[1].url.path,"/internal/outbox/out-1/finish")
  self.assertNotIn("response",seen[1].content.decode())
  client.close()
 def test_unlisted_workflow_never_delivered(self):
  seen=[]
  def handler(req):
   seen.append(req)
   if req.url.path.endswith("/lease"):
    return httpx.Response(200,json={"item":{"id":"out-2","run_id":"run-2","workflow":"not.allowed","input":{},"lease_token":"x"*36}})
   return httpx.Response(200,json={"status":"failed"})
  client=httpx.Client(transport=httpx.MockTransport(handler))
  def never(**kw): self.fail("unlisted workflow must not be delivered")
  self.assertEqual(run_once(client=client,deliverer=never),"rejected_workflow")
  self.assertEqual(len(seen),2); client.close()
 def test_uncertain_delivery_is_not_marked_failed_or_retried(self):
  seen=[]
  def handler(req):
   seen.append(req)
   return httpx.Response(200,json={"item":{"id":"out-3","run_id":"run-3","workflow":"sample.review","input":{},"lease_token":"x"*36}})
  client=httpx.Client(transport=httpx.MockTransport(handler))
  def uncertain(**kw): raise httpx.ReadTimeout("uncertain delivery")
  with self.assertRaises(httpx.ReadTimeout): run_once(client=client,deliverer=uncertain)
  self.assertEqual(len(seen),1) # no finish and no blind retry
  client.close()
if __name__=="__main__": unittest.main()
