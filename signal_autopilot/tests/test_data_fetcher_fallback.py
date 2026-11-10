"""Tests for per-symbol public-exchange fallback and source provenance."""
import unittest

from modules.data_fetcher import MarketDataFetcher
from modules.signal_engine import generate_signals


def row(base, provider, ohlcv="OK"):
    return {
        "base": base,
        "provider": provider,
        "symbol": f"{base}/USDT:USDT",
        "availability": {"ohlcv": ohlcv, "funding": "OK", "open_interest": "OK"},
        "ohlcv": [{"timestamp": 1, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}] if ohlcv == "OK" else [],
        "last": 1.5,
        "ticker_timestamp_utc": "2026-11-10T16:00:00+00:00",
        "ticker_timestamp_source": "EXCHANGE",
    }


class MultiProviderFallbackTests(unittest.TestCase):
    def test_partial_primary_is_filled_by_next_exchange_without_duplicate_symbols(self):
        fetcher = MarketDataFetcher.__new__(MarketDataFetcher)
        fetcher.limit = 4
        fetcher.universe_diagnostics = {}

        def fake_fetch(provider, whitelist, exclude_bases=None, target_count=None):
            if provider == "okx":
                fetcher.universe_diagnostics[provider] = {"eligible_before_limit": 3}
                return [
                    row("BTC", "okx"),
                    row("ETH", "okx"),
                    row("DOGE", "okx", ohlcv="UNAVAILABLE"),
                ]
            if provider == "bybit":
                fetcher.universe_diagnostics[provider] = {"eligible_before_limit": 4}
                return [
                    row("BTC", "bybit"),  # duplicate: OKX remains preferred
                    row("DOGE", "bybit"), # primary lacked usable OHLCV
                    row("SOL", "bybit"),
                    row("XRP", "bybit"),
                ]
            raise AssertionError(f"unexpected provider request: {provider}")

        fetcher._coingecko_top_symbols = lambda: {"BTC", "ETH", "DOGE", "SOL", "XRP"}
        fetcher._fetch_from_provider = fake_fetch

        result = fetcher.fetch()

        self.assertEqual(result["symbols_processed"], 4)
        self.assertEqual(result["provider"], "multi-provider")
        self.assertEqual(result["provider_sources"], ["okx", "bybit"])
        self.assertTrue(result["fallback_used"])
        self.assertEqual(
            [(item["base"], item["provider"]) for item in result["symbols"]],
            [("BTC", "okx"), ("ETH", "okx"), ("DOGE", "bybit"), ("SOL", "bybit")],
        )
        self.assertEqual(len({item["base"] for item in result["symbols"]}), 4)
        self.assertEqual(result["universe_diagnostics"]["okx"]["ohlcv_unavailable"], 1)
        self.assertEqual(result["universe_diagnostics"]["bybit"]["duplicates_skipped"], 1)

    def test_signal_payload_keeps_provider_diagnostics_and_symbol_provenance(self):
        result = generate_signals({
            "provider": "multi-provider",
            "provider_sources": ["okx", "bybit"],
            "fallback_used": True,
            "universe_diagnostics": {"okx": {"symbols_added": 1}},
            "generated_at_utc": "2026-11-10T16:00:00+00:00",
            "symbols": [row("BTC", "okx", ohlcv="UNAVAILABLE")],
        })

        self.assertEqual(result["provider_sources"], ["okx", "bybit"])
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["universe_diagnostics"]["okx"]["symbols_added"], 1)
        self.assertEqual(result["signals"][0]["data_provider"], "okx")
        self.assertEqual(result["signals"][0]["base"], "BTC")
        self.assertEqual(result["signals"][0]["status"], "MARKET_DATA_DEGRADED")


if __name__ == "__main__":
    unittest.main()
