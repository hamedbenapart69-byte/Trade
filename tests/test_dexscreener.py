import unittest
import httpx
from app.integrations.dexscreener import search_dex_pools, DexScreenerError


class DexScreenerTests(unittest.TestCase):
    def test_normalizes_pool_and_preserves_missing_values(self):
        def handler(request):
            self.assertEqual(request.url.host, "api.dexscreener.com")
            return httpx.Response(200, json={"pairs": [{
                "chainId": "ethereum", "dexId": "uniswap", "pairAddress": "0xpair",
                "baseToken": {"symbol": "ABC", "name": "Alpha", "address": "0xabc"},
                "quoteToken": {"symbol": "WETH"}, "priceUsd": "0.25",
                "liquidity": {"usd": 120000}, "volume": {"h24": 40000},
                "priceChange": {"h24": -2.5}, "txns": {"h24": {"buys": 80, "sells": 60}},
                "pairCreatedAt": 1700000000000
            }]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            pools = search_dex_pools(query="ABC", client=client)
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0].provider, "dexscreener")
        self.assertEqual(pools[0].price_usd, 0.25)
        self.assertEqual(pools[0].liquidity_usd, 120000.0)
        self.assertEqual(pools[0].buys_24h, 80)
        self.assertIsNone(pools[0].fdv_usd)
        self.assertTrue(pools[0].retrieved_at)

    def test_rejects_empty_query_before_network(self):
        with self.assertRaisesRegex(DexScreenerError, "invalid_search_query"):
            search_dex_pools(query="  ")

    def test_rejects_invalid_provider_shape(self):
        def handler(request):
            return httpx.Response(200, json={"unexpected": []})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(DexScreenerError, "provider_response_missing_pairs"):
                search_dex_pools(query="ABC", client=client)


if __name__ == "__main__":
    unittest.main()
