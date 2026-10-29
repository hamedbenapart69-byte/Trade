import os
import unittest
import httpx
from app.integrations.coingecko import MarketSnapshot
from worker import run_once

class WorkerMarketSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.old = {k: os.environ.get(k) for k in (
            "ENABLE_WORKER_EXECUTION", "CONTROL_API_URL", "WORKER_API_TOKEN", "WORKER_ALLOWED_WORKFLOWS"
        )}
        os.environ.update({
            "ENABLE_WORKER_EXECUTION": "true",
            "CONTROL_API_URL": "https://control.test",
            "WORKER_API_TOKEN": "worker-test-token-at-least-24-characters",
            "WORKER_ALLOWED_WORKFLOWS": "market.snapshot",
        })
        self.finish_payload = None

    def tearDown(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_approved_market_snapshot_result_is_persisted_to_outbox(self):
        def handler(request):
            if request.url.path == "/internal/outbox/lease":
                return httpx.Response(200, json={"item": {
                    "id": "outbox-1", "lease_token": "lease-token-which-is-long-enough",
                    "run_id": "run-1", "workflow": "market.snapshot",
                    "input": {"coin_id": "bitcoin", "currency": "usd"}
                }})
            if request.url.path == "/internal/outbox/outbox-1/finish":
                import json
                self.finish_payload = json.loads(request.content)
                return httpx.Response(200, json={"status": "completed"})
            return httpx.Response(404, json={"detail": "not found"})

        def market_fetcher(*, payload):
            self.assertEqual(payload, {"coin_id": "bitcoin", "currency": "usd"})
            return MarketSnapshot("coingecko", 200, "bitcoin", "usd", 80000.5, 0.75)

        with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
            status = run_once(client=client, market_fetcher=market_fetcher)

        self.assertEqual(status, "completed")
        self.assertIsNotNone(self.finish_payload)
        self.assertTrue(self.finish_payload["succeeded"])
        self.assertEqual(self.finish_payload["result"]["provider"], "coingecko")
        self.assertEqual(self.finish_payload["result"]["price"], 80000.5)
        self.assertEqual(self.finish_payload["result"]["change_24h_pct"], 0.75)

if __name__ == "__main__":
    unittest.main()
