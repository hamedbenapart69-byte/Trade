import unittest
import httpx
from app.integrations.coingecko import fetch_market_snapshot, MarketDataError
from app.workflow_schemas import validate_workflow_input

class CoinGeckoIntegrationTests(unittest.TestCase):
    def test_valid_snapshot_parses_price_and_change(self):
        def handler(request):
            self.assertEqual(request.url.host, "api.coingecko.com")
            return httpx.Response(200, json={"bitcoin": {"usd": 67432.1, "usd_24h_change": -1.25}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_market_snapshot(payload={"coin_id":"bitcoin","currency":"usd"}, client=client)
        self.assertEqual(result.provider, "coingecko")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.price, 67432.1)
        self.assertEqual(result.change_24h_pct, -1.25)

    def test_rejects_unapproved_coin_before_network(self):
        with self.assertRaisesRegex(MarketDataError, "coin_id_not_allowlisted"):
            fetch_market_snapshot(payload={"coin_id":"attacker-controlled-id"})

    def test_provider_error_is_not_misreported_as_success(self):
        def handler(request):
            return httpx.Response(429, json={"error":"rate limit"})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(MarketDataError, "coingecko_transport_or_http_error"):
                fetch_market_snapshot(payload={"coin_id":"bitcoin"}, client=client)

    def test_schema_rejects_unknown_fields_and_unapproved_coins(self):
        self.assertEqual(validate_workflow_input("market.snapshot", {"coin_id":"bitcoin"}), None)
        self.assertIn("unknown_fields", validate_workflow_input("market.snapshot", {"coin_id":"bitcoin","url":"https://evil"}))
        self.assertEqual(validate_workflow_input("market.snapshot", {"coin_id":"unknown"}), "coin_id_not_allowlisted")

if __name__ == "__main__":
    unittest.main()
