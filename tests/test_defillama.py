import unittest
import httpx
from app.integrations.defillama import fetch_protocols, DeFiLlamaError


class DeFiLlamaTests(unittest.TestCase):
    def test_parses_protocol_and_keeps_missing_fields_empty(self):
        def handler(request):
            self.assertEqual(request.url.host, "api.llama.fi")
            return httpx.Response(200, json=[{
                "slug": "sample-protocol", "name": "Sample", "category": "Dexes",
                "chains": ["Ethereum", "Arbitrum"], "tvl": 1250000,
                "change_1d": 1.5, "change_7d": -3.0
            }])
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            rows = fetch_protocols(client=client)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].provider, "defillama")
        self.assertEqual(rows[0].tvl_usd, 1250000.0)
        self.assertEqual(rows[0].chains, ("Ethereum", "Arbitrum"))
        self.assertEqual(rows[0].change_7d_pct, -3.0)
        self.assertIsNone(rows[0].market_cap_usd)

    def test_rejects_wrong_top_level_shape(self):
        def handler(request):
            return httpx.Response(200, json={"protocols": []})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(DeFiLlamaError, "provider_response_not_a_list"):
                fetch_protocols(client=client)


if __name__ == "__main__":
    unittest.main()
