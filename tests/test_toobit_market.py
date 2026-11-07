import time
import unittest
import httpx

from app.integrations.toobit_market import ToobitPublicMarketData
from app.signals import contract_sized_risk


class ToobitAdapterTests(unittest.TestCase):
    def setUp(self):
        self.now = int(time.time() * 1000)
        self.hour = self.now // 3_600_000 * 3_600_000
        self.contract = {
            "symbol": "HANA-SWAP-USDT",
            "status": "TRADING",
            "inverse": False,
            "quoteAsset": "USDT",
            "marginToken": "USDT",
            "underlying": "HANA",
            "contractMultiplier": "1",
            "minTradePrecision": "1",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.00001"},
                {"filterType": "LOT_SIZE", "minQty": "30", "maxQty": "500000", "stepSize": "1"},
                {"filterType": "MIN_NOTIONAL", "minNotional": "0"},
            ],
            "riskLimits": [
                {"value": "10000", "maxLeverage": "10"},
                {"value": "50000", "maxLeverage": "5"},
            ],
        }

    def make_provider(self, stale_depth=False):
        def handler(request):
            path = request.url.path
            if path == "/api/v1/exchangeInfo":
                return httpx.Response(200, json={"serverTime": self.now, "contracts": [self.contract]})
            if path == "/quote/v1/contract/ticker/24hr":
                return httpx.Response(200, json=[{"s": "HANA-SWAP-USDT", "c": "0.01374", "h": "0.01449",
                    "l": "0.01326", "v": "30314432", "qv": "422908.01953", "pcp": "-0.0472", "t": self.now}])
            if path == "/quote/v1/contract/ticker/bookTicker":
                return httpx.Response(200, json=[{"s": "HANA-SWAP-USDT", "b": "0.01374", "bq": "84521",
                    "a": "0.01375", "aq": "207878", "t": self.now}])
            if path == "/quote/v1/depth":
                depth_time = self.now - 16 * 60_000 if stale_depth else self.now
                return httpx.Response(200, json={"t": depth_time, "b": [["0.01374", "100000"], ["0.01373", "100000"]],
                    "a": [["0.01375", "100000"], ["0.01376", "100000"]]})
            if path == "/quote/v1/markPrice":
                return httpx.Response(200, json=[{"symbolId": "HANA-SWAP-USDT", "price": "0.01374", "time": self.now}])
            if path == "/quote/v1/index":
                return httpx.Response(200, json={"index": {"HANAUSDT": "0.01372"}})
            if path == "/api/v1/futures/fundingRate":
                return httpx.Response(200, json=[{"symbol": "HANA-SWAP-USDT", "rate": "0.00005", "period": "4H",
                    "nextFundingTime": str(self.now + 3_600_000)}])
            if path == "/quote/v1/openInterest":
                return httpx.Response(200, json={"openInterestList": [{"symbol": "HANA-SWAP-USDT", "size": "18542254.77"}]})
            if path == "/quote/v1/globalLongShortAccountRatio":
                return httpx.Response(200, json=[{"symbol": "HANA-SWAP-USDT", "timeStamp": self.now,
                    "longShortRatio": "2.1429", "longAccount": "0.6818", "shortAccount": "0.3182"}])
            if path == "/quote/v1/klines":
                start = self.hour - 2 * 3_600_000
                return httpx.Response(200, json=[
                    [start, "0.0138", "0.0139", "0.0137", "0.01385", "100000", 0, "1385", 100, "60000", "831"],
                    [start + 3_600_000, "0.01385", "0.0139", "0.0137", "0.0138", "100000", 0, "1380", 100, "55000", "759"],
                ])
            if path == "/api/v1/time":
                return httpx.Response(200, json={"serverTime": self.now})
            return httpx.Response(404, json={"msg": "not found"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        return ToobitPublicMarketData(client=client), client

    def test_only_live_linear_usdt_contract_is_discovered_and_sized(self):
        provider, client = self.make_provider()
        try:
            self.assertEqual(provider.tracked_symbols(), {"HANAUSDT"})
            spec = provider.contract_specs(["HANAUSDT"])["HANAUSDT"]
            self.assertEqual(spec["venue_symbol"], "HANA-SWAP-USDT")
            self.assertEqual(spec["quantity_unit"], "contracts")
            self.assertEqual(spec["contract_multiplier"], 1.0)
            self.assertEqual(spec["min_qty"], 30.0)
            self.assertEqual(spec["step_size"], 1.0)
            self.assertEqual(spec["max_qty"], 500000.0)
            risk = contract_sized_risk("LONG", 1, 0.99, spec)
            self.assertTrue(risk["valid"])
            self.assertLessEqual(risk["planned_loss_usd"], 4.0)
            self.assertLessEqual(risk["required_leverage"], 5.0)
            self.assertGreaterEqual(risk["quantity_contracts_reference"], 30)
        finally:
            client.close()

    def test_prices_include_spread_and_verified_depth(self):
        provider, client = self.make_provider()
        try:
            provider.contract_specs(["HANAUSDT"])
            price = provider.prices(["HANAUSDT"])["HANAUSDT"]
            self.assertAlmostEqual(price["price"], 0.01374)
            self.assertGreater(price["quoteVolume24h"], 100000)
            self.assertLess(price["spreadBps"], 30)
            self.assertGreater(price["bidDepthUsd"], 500)
            self.assertGreater(price["askDepthUsd"], 500)
        finally:
            client.close()

    def test_stale_orderbook_depth_is_rejected(self):
        provider, client = self.make_provider(stale_depth=True)
        try:
            provider.contract_specs(["HANAUSDT"])
            self.assertNotIn("HANAUSDT", provider.prices(["HANAUSDT"]))
        finally:
            client.close()

    def test_derivatives_are_normalized_without_account_credentials(self):
        provider, client = self.make_provider()
        try:
            row = provider.derivatives(["HANAUSDT"])["HANAUSDT"]
            self.assertEqual(row["funding"]["intervalHours"], 4)
            self.assertAlmostEqual(row["funding"]["rate"], 0.00005)
            self.assertGreater(row["openInterest"]["valueUsd"], 100000)
            self.assertAlmostEqual(row["positioning"]["globalLongShortRatio"], 2.1429)
            self.assertEqual(row["indexPrice"], 0.01372)
            self.assertFalse(hasattr(provider, "api_key"))
        finally:
            client.close()

    def test_candles_keep_closed_bar_and_taker_buy_quote_volume(self):
        provider, client = self.make_provider()
        try:
            candles = provider.candles("HANAUSDT", "1h", 2)
            self.assertEqual(len(candles), 2)
            self.assertEqual(candles[-1].taker_buy_quote_volume, 759.0)
            self.assertTrue(all(c.is_final for c in candles))
        finally:
            client.close()

    def test_venue_leverage_tier_can_reject_position(self):
        contract = {
            "tick_size": 0.01, "step_size": 1, "min_qty": 1, "max_qty": 10000,
            "quantity_unit": "contracts", "contract_multiplier": 1,
            "risk_limits": [{"value": 10000, "max_leverage": 1}],
        }
        result = contract_sized_risk("LONG", 100, 99, contract)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "rounded_quantity_exceeds_venue_or_user_leverage_cap")


if __name__ == "__main__":
    unittest.main()
