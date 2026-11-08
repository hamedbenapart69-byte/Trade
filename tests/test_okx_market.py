import unittest
import httpx

from app.integrations.okx_market import OkxPublicMarketData
from app.signals import Candle, contract_sized_risk


class OkxAdapterTests(unittest.TestCase):
    def make_provider(self, handler):
        client=httpx.Client(transport=httpx.MockTransport(handler))
        return OkxPublicMarketData(client=client)

    def test_coingecko_discovery_requests_250_market_assets(self):
        def handler(request):
            self.assertEqual(request.url.host,"api.coingecko.com")
            self.assertEqual(request.url.path,"/api/v3/coins/markets")
            self.assertEqual(request.url.params.get("per_page"),"250")
            return httpx.Response(200,json=[{"id":"bitcoin","symbol":"btc","name":"Bitcoin",
                "total_volume":1000,"market_cap_rank":1,"current_price":50000,"market_cap":1000000}])
        p=self.make_provider(handler)
        try:
            rows=p.discover()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["symbol"],"BTC")
        finally:
            p.close()

    def test_linear_usdt_swap_contract_metadata_is_normalized(self):
        def handler(request):
            self.assertEqual(request.url.path,"/api/v5/public/instruments")
            return httpx.Response(200,json={"code":"0","data":[{
                "instId":"BTC-USDT-SWAP","instType":"SWAP","ctType":"linear","state":"live",
                "settleCcy":"USDT","ctVal":"0.01","ctValCcy":"BTC","tickSz":"0.1","lotSz":"0.01","minSz":"0.01","lever":"125","maxLmtSz":"1000","maxMktSz":"500"}]})
        p=self.make_provider(handler)
        try:
            self.assertEqual(p.tracked_symbols(),{"BTCUSDT"})
            spec=p.contract_specs(["BTCUSDT"])["BTCUSDT"]
            self.assertEqual(spec["quantity_unit"],"contracts")
            self.assertEqual(spec["contract_multiplier"],0.01)
            self.assertEqual(spec["tick_size"],0.1)
            self.assertEqual(spec["step_size"],0.01)
            self.assertEqual(spec["max_leverage"],125.0)
            self.assertEqual(spec["max_qty"],500.0)
        finally:
            p.close()

    def test_venue_max_leverage_is_enforced_after_contract_sizing(self):
        contract={"symbol":"BTCUSDT","contract_type":"PERPETUAL","status":"TRADING",
            "base_asset":"BTC","quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"contracts",
            "contract_multiplier":0.01,"tick_size":0.1,"step_size":0.01,"min_qty":0.01,
            "min_notional":0,"max_leverage":3}
        result=contract_sized_risk("LONG",100000,99500,contract)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"],"rounded_quantity_exceeds_venue_or_user_leverage_cap")

    def test_global_positioning_ratio_carries_its_observation_timestamp(self):
        now=1_800_000_000_000
        def handler(request):
            path=request.url.path
            if path=="/api/v5/public/funding-rate":
                data=[{"fundingRate":"0.0001","fundingTime":str(now),"nextFundingTime":str(now+8*3_600_000),"ts":str(now)}]
            elif path=="/api/v5/public/open-interest":
                data=[{"oi":"100","oiUsd":"1000000","ts":str(now)}]
            elif path=="/api/v5/rubik/stat/contracts/open-interest-history":
                data=[[str(now-24*3_600_000),"90","90","900000"],[str(now-4*3_600_000),"95","95","950000"]]
            elif path=="/api/v5/rubik/stat/contracts/long-short-account-ratio":
                data=[[str(now-3_600_000),"1.23"]]
            elif path=="/api/v5/public/mark-price":
                data=[{"markPx":"100","ts":str(now)}]
            elif path=="/api/v5/market/tickers":
                data=[{"instId":"BTC-USDT-SWAP","last":"100","open24h":"99","ts":str(now)}]
            elif path=="/api/v5/market/index-tickers":
                data=[{"idxPx":"100","ts":str(now)}]
            else:
                self.fail(f"Unexpected OKX endpoint: {path}")
            return httpx.Response(200,json={"code":"0","data":data})
        p=self.make_provider(handler)
        try:
            result=p.derivatives(["BTCUSDT"])["BTCUSDT"]
            self.assertEqual(result["positioning"]["globalLongShortRatio"],1.23)
            self.assertEqual(result["positioning"]["globalLongShortRatioObservedAtMs"],now-3_600_000)
            self.assertEqual(result["source"],"OKX public market-data API")
        finally:
            p.close()

    def test_okx_candles_are_reversed_and_finality_preserved(self):
        rows=[
            ["2000","2","3","1","2.5","10","10","25","1"],
            ["1000","1","2","0.5","1.5","8","8","12","0"],
        ]
        def handler(request):
            return httpx.Response(200,json={"code":"0","data":rows})
        p=self.make_provider(handler)
        try:
            candles=p.candles("BTCUSDT","1h",2)
            self.assertEqual([c.open_time for c in candles],[1000,2000])
            self.assertEqual(candles[0].volume,12.0)
            self.assertFalse(candles[0].is_final)
            self.assertTrue(candles[1].is_final)
        finally:
            p.close()

    def test_risk_sizing_uses_contract_multiplier_and_contract_step(self):
        contract={"symbol":"BTCUSDT","contract_type":"PERPETUAL","status":"TRADING",
            "base_asset":"BTC","quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"contracts",
            "contract_multiplier":0.01,"tick_size":0.1,"step_size":0.01,"min_qty":0.01,"min_notional":0}
        result=contract_sized_risk("LONG",100000,99000,contract)
        self.assertTrue(result["contract_spec_verified"])
        self.assertEqual(result["quantity_unit"],"contracts")
        self.assertIsNotNone(result["quantity_contracts_reference"])
        self.assertAlmostEqual(result["quantity_base"],result["quantity_contracts_reference"]*0.01)
        self.assertLessEqual(result["planned_loss_usd"],4.0)
        self.assertLessEqual(result["required_leverage"],5.0)
        self.assertGreaterEqual(result["reward_to_risk"],2.0)


if __name__=="__main__":
    unittest.main()
