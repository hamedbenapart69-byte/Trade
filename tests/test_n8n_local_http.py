import json, os, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from app.integrations.n8n import deliver_approved_payload, IntegrationDeliveryError

class LocalReceiver(BaseHTTPRequestHandler):
    calls=[]
    response_status=202
    response_body=b'{"accepted":true}'
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get("Content-Length","0")))
        type(self).calls.append({"path":self.path,"headers":dict(self.headers),"body":json.loads(raw)})
        self.send_response(type(self).response_status)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(type(self).response_body)
    def log_message(self,*args): pass

class N8nLocalHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),LocalReceiver)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}/webhook/test"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=2)
    def setUp(self):
        self.old={k:os.environ.get(k) for k in ["ENABLE_N8N_EXECUTION","N8N_WEBHOOK_URL","N8N_TIMEOUT_SECONDS","N8N_WEBHOOK_TOKEN"]}
        os.environ.update({"ENABLE_N8N_EXECUTION":"true","N8N_WEBHOOK_URL":self.url,"N8N_TIMEOUT_SECONDS":"3","N8N_WEBHOOK_TOKEN":"local-test-secret"})
        LocalReceiver.calls=[]; LocalReceiver.response_status=202; LocalReceiver.response_body=b'{"accepted":true}'
    def tearDown(self):
        for k,v in self.old.items():
            if v is None: os.environ.pop(k,None)
            else: os.environ[k]=v
    def test_real_local_http_delivery_sends_payload_and_idempotency(self):
        result=deliver_approved_payload(run_id="run-local-1",workflow="test.echo",payload={"symbol":"BTCUSDT"},idempotency_key="run-local-1")
        self.assertEqual(result.status_code,202)
        self.assertEqual(len(LocalReceiver.calls),1)
        call=LocalReceiver.calls[0]
        self.assertEqual(call["path"],"/webhook/test")
        self.assertEqual(call["body"],{"run_id":"run-local-1","workflow":"test.echo","input":{"symbol":"BTCUSDT"}})
        self.assertEqual(call["headers"]["Idempotency-Key"],"run-local-1")
        self.assertEqual(call["headers"]["X-Webhook-Token"],"local-test-secret")
    def test_non_2xx_is_failure_and_not_silently_accepted(self):
        LocalReceiver.response_status=500
        with self.assertRaises(IntegrationDeliveryError):
            deliver_approved_payload(run_id="run-local-2",workflow="test.echo",payload={},idempotency_key="run-local-2")
    def test_adapter_stays_disabled_by_default(self):
        os.environ["ENABLE_N8N_EXECUTION"]="false"
        from app.integrations.n8n import IntegrationDisabled
        with self.assertRaises(IntegrationDisabled):
            deliver_approved_payload(run_id="run-local-3",workflow="test.echo",payload={},idempotency_key="run-local-3")
if __name__=="__main__": unittest.main()
