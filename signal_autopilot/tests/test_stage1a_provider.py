import json
import unittest
from unittest.mock import Mock

from modules.stage1a_data_provider import Stage1ADataProvider


class Stage1AProviderTests(unittest.TestCase):
    def setUp(self):
        self.config = {"market_data": {
            "provider_strategy": {
                "target_symbols": 50, "minimum_qualifying_symbols": 40,
                "candidate_scan_limit": 150, "minimum_24h_quote_volume_usd": 10_000_000
            },
            "universe": {"blacklist_patterns": ["USDC"]}
        }}

    def test_config_targets_50_and_minimum_40(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        self.assertEqual(provider.target, 50)
        self.assertEqual(provider.minimum, 40)
        self.assertEqual(provider.scan_limit, 150)

    def test_fapi_451_uses_coingecko_as_explicit_proxy(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        provider._binance_funding = Mock(return_value={
            "status": "BLOCKED_451", "rate": None, "provider": "BINANCE_FAPI"
        })
        result = provider._funding("BTCUSDT", {"BTCUSDT": 0.0001})
        self.assertEqual(result["provider"], "COINGECKO")
        self.assertEqual(result["status"], "PROXY")
        self.assertEqual(result["rate"], 0.0001)
        self.assertEqual(result["fallback_reason"], "BLOCKED_451")

    def test_fapi_and_coingecko_missing_fall_back_to_kucoin_proxy(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        provider._binance_funding = Mock(return_value={
            "status": "BLOCKED_451", "rate": None, "provider": "BINANCE_FAPI"
        })
        provider._kucoin_proxy_funding = Mock(return_value={
            "status": "PROXY", "rate": 0.0002, "provider": "KUCOIN_FUTURES"
        })
        result = provider._funding("ETHUSDT", {})
        self.assertEqual(result["provider"], "KUCOIN_FUTURES")
        self.assertEqual(result["status"], "PROXY")
        self.assertIn("COINGECKO_MISSING", result["fallback_reason"])

    def test_binance_fapi_success_is_not_downgraded_to_proxy(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        expected = {"status": "OK", "rate": 0.0003, "provider": "BINANCE_FAPI"}
        provider._binance_funding = Mock(return_value=expected)
        provider._coingecko_funding_map = Mock(side_effect=AssertionError("must not call fallback"))
        self.assertEqual(provider._funding("BTCUSDT", None), expected)

    def test_output_contract_always_has_provider_and_per_symbol_coverage(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        provider._coingecko_assets = Mock(return_value=[])
        provider._vision_symbols = Mock(return_value=set())
        report = provider.run()
        report.setdefault("provider_selected", "NONE")
        report.setdefault("coverage_per_symbol", [])
        self.assertIn("provider_selected", report)
        self.assertIn("coverage_per_symbol", report)
        self.assertEqual(report["stage1a_status"], "FAIL")

    def test_kucoin_proxy_is_counted_separately(self):
        provider = Stage1ADataProvider(self.config, client=Mock())
        provider._binance_funding = Mock(return_value={
            "status": "BLOCKED_451", "rate": None, "provider": "BINANCE_FAPI"
        })
        provider._kucoin_proxy_funding = Mock(return_value={
            "status": "PROXY", "rate": 0.0002, "provider": "KUCOIN_FUTURES"
        })
        provider._funding("SOLUSDT", {})
        self.assertEqual(provider.provider_counts["KUCOIN_PROXY"], 1)


if __name__ == "__main__":
    unittest.main()
