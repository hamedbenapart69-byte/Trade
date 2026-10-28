import json, os, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from fastapi.testclient import TestClient
import httpx
from app import store
from app.main import app
from worker import run_once

class Receiver(BaseHTTPRequestHandler):
    calls=[]
    def do_POST(self):
        raw=self.rfile.read(int(self.headers.get("Content-Length","0")))
        type(self).calls.append({"path":self.path,"headers":dict(self.headers),"body":json.loads(raw)})
        self.send_response(202); self.send_header("Content-Type","application/json"); self.end_headers()
        self.wfile.write(b'{"accepted":true}')
    def log_message(self,*args): pass

class LocalEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receiver=ThreadingHTTPServer(("127.0.0.1",0),Receiver)
        cls.thread=threading.Thread(target=cls.receiver.serve_forever,daemon=True); cls.thread.start()
        cls.webhook=f"http://127.0.0.1:{cls.receiver.server_port}/webhook/authorized-test"
    @classmethod
    def tearDownClass(cls):
        cls.receiver.shutdown(); cls.receiver.server_close(); cls.thread.join(timeout=2)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ.update({
            "CONTROL_DB_PATH":str(Path(self.tmp.name)/"e2e.db"),
            "CONTROL_API_TOKEN":"e2e-control-token-long-enough-123456",
            "WORKER_API_TOKEN":"e2e-worker-token-long-enough-123456",
            "ENABLE_WORKER_EXECUTION":"true",
            "WORKER_ALLOWED_WORKFLOWS":"research.scan",
            "ENABLE_N8N_EXECUTION":"true",
            "N8N_WEBHOOK_URL":self.webhook,
            "N8N_WEBHOOK_TOKEN":"e2e-receiver-secret",
            "CONTROL_API_URL":"https://control.test"
        })
        self.client=TestClient(app); store.init_db(); Receiver.calls=[]
        self.control_headers={"X-API-Key":os.environ["CONTROL_API_TOKEN"]}
    def tearDown(self):
        self.client.close(); self.tmp.cleanup()
        for key in ["CONTROL_DB_PATH","CONTROL_API_TOKEN","WORKER_API_TOKEN","ENABLE_WORKER_EXECUTION","WORKER_ALLOWED_WORKFLOWS","ENABLE_N8N_EXECUTION","N8N_WEBHOOK_URL","N8N_WEBHOOK_TOKEN","CONTROL_API_URL"]:
            os.environ.pop(key,None)
    def test_approved_research_run_reaches_local_receiver_and_persists_completion(self):
        created=self.client.post("/runs",headers={**self.control_headers,"Idempotency-Key":"e2e-research-run-0001"},json={
            "workflow":"research.scan","input":{"symbol":"BTCUSDT","market":"spot","timeframe":"4h"}})
        self.assertEqual(created.status_code,201)
        run_id=created.json()["id"]
        self.assertEqual(self.client.post(f"/runs/{run_id}/approve",headers=self.control_headers,json={"decided_by":"test-owner"}).status_code,200)
        self.assertEqual(self.client.post(f"/runs/{run_id}/queue",headers=self.control_headers).status_code,202)
        def route_control(req):
            response=self.client.request(req.method,req.url.path+("?"+req.url.query.decode() if req.url.query else ""),headers=dict(req.headers),content=req.content)
            return httpx.Response(response.status_code,headers={"content-type":"application/json"},content=response.content)
        control=httpx.Client(transport=httpx.MockTransport(route_control))
        try:
            self.assertEqual(run_once(client=control),"completed")
        finally: control.close()
        self.assertEqual(len(Receiver.calls),1)
        self.assertEqual(Receiver.calls[0]["body"]["workflow"],"research.scan")
        self.assertEqual(Receiver.calls[0]["body"]["input"]["symbol"],"BTCUSDT")
        self.assertEqual(Receiver.calls[0]["headers"]["Idempotency-Key"],run_id)
        self.assertEqual(self.client.get(f"/runs/{run_id}",headers=self.control_headers).json()["outbox_status"],"completed")
if __name__=="__main__": unittest.main()
