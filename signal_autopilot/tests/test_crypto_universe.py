import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from modules.data_fetcher import MarketDataFetcher


class FakeExchange:
    def __init__(self, markets, tickers, candles=None):
        self.markets = markets
        self._tickers = tickers
        self._candles = candles or {}

    def load_markets(self):
        return self.markets

    def fetch_tickers(self):
        return self._tickers

    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=1):
        return self._candles.get(symbol, [])[:limit]


class CryptoUniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp.name) / "config.json"
        self.config_path.write_text(json.dumps({
            "market_data": {"universe": {
                "whitelist_count": 200, "quote": "USDT", "settle": "USDT",
                "min_listing_age_days": 730, "min_quote_volume_24h_usd": 10_000_000,
                "blacklist_patterns": ["GOOGL", "NVDA", "QQQ", "MSTR", "SKHYNIX", "SNDK", "SOXL", "SOXS"]
            }}
        }), encoding="utf-8")
        self.fetcher = MarketDataFetcher(limit=100, config_path=self.config_path)

    def tearDown(self):
        self.tmp.cleanup()

    def market(self, base, listing_ms, **overrides):
        market = {
            "active": True, "swap": True, "linear": True, "quote": "USDT",
            "settle": "USDT", "contract": True, "base": base, "id": base + "USDT",
            "info": {"listTime": str(listing_ms)}
        }
        market.update(overrides)
        return market

    def test_only_whitelisted_old_high_volume_usdt_perpetuals_pass(self):
        now = 1_800_000_000_000
        old = now - 800 * 86_400_000
        new = now - 100 * 86_400_000
        markets = {
            "BTC/USDT:USDT": self.market("BTC", old),
            "ETH/USDT:USDT": self.market("ETH", old),
            "GOOGL/USDT:USDT": self.market("GOOGL", old),
            "NVDA/USDT:USDT": self.market("NVDA", old),
            "NEW/USDT:USDT": self.market("NEW", new),
            "SMALL/USDT:USDT": self.market("SMALL", old),
            "BTC/USDC:USDC": self.market("BTC", old, quote="USDC", settle="USDC"),
            "BTC/USDT": self.market("BTC", old, swap=False),
        }
        tickers = {
            "BTC/USDT:USDT": {"quoteVolume": 30_000_000, "last": 60_000},
            "ETH/USDT:USDT": {"quoteVolume": 20_000_000, "last": 3_000},
            "GOOGL/USDT:USDT": {"quoteVolume": 30_000_000, "last": 100},
            "NVDA/USDT:USDT": {"quoteVolume": 30_000_000, "last": 100},
            "NEW/USDT:USDT": {"quoteVolume": 30_000_000, "last": 1},
            "SMALL/USDT:USDT": {"quoteVolume": 9_999_999, "last": 1},
            "BTC/USDC:USDC": {"quoteVolume": 30_000_000, "last": 60_000},
            "BTC/USDT": {"quoteVolume": 30_000_000, "last": 60_000},
        }
        exchange = FakeExchange(markets, tickers)
        selected = self.fetcher._eligible_markets(exchange, "okx", {"BTC", "ETH", "NEW", "SMALL"}, now)
        self.assertEqual([row[1] for row in selected], ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        self.assertEqual(self.fetcher.universe_diagnostics["okx"]["eligible_before_limit"], 2)

    def test_missing_listing_timestamp_is_rejected(self):
        now = 1_800_000_000_000
        market = self.market("BTC", now - 900 * 86_400_000)
        market["info"] = {}
        exchange = FakeExchange({"BTC/USDT:USDT": market},
                                {"BTC/USDT:USDT": {"quoteVolume": 50_000_000}})
        selected = self.fetcher._eligible_markets(exchange, "okx", {"BTC"}, now)
        self.assertEqual(selected, [])
        self.assertEqual(self.fetcher.universe_diagnostics["okx"]["rejected"]["listing_time_missing"], 1)


    def test_missing_listing_metadata_can_pass_with_two_year_ohlcv_evidence(self):
        now = 1_800_000_000_000
        cutoff = now - 730 * 86_400_000
        market = self.market("BTC", 0)
        market["info"] = {}
        exchange = FakeExchange(
            {"BTC/USDT:USDT": market},
            {"BTC/USDT:USDT": {"quoteVolume": 50_000_000}},
            {"BTC/USDT:USDT": [[cutoff, 10, 11, 9, 10, 100]]},
        )
        selected = self.fetcher._eligible_markets(exchange, "bitget", {"BTC"}, now)
        self.assertEqual(len(selected), 1)
        self.assertEqual(self.fetcher.universe_diagnostics["bitget"]["rejected"]["history_verified"], 1)

    def test_bybit_launch_time_is_supported(self):
        now = 1_800_000_000_000
        market = self.market("BTC", 0)
        market["info"] = {"launchTime": str(now - 900 * 86_400_000)}
        self.assertEqual(MarketDataFetcher._listing_time_ms(market, "bybit"), now - 900 * 86_400_000)

    def test_binance_onboard_date_is_supported(self):
        now = 1_800_000_000_000
        market = self.market("BTC", 0)
        market["info"] = {"onboardDate": str(now - 900 * 86_400_000)}
        self.assertEqual(MarketDataFetcher._listing_time_ms(market, "binance"), now - 900 * 86_400_000)



    def test_debug_block_okx_forces_fallback_without_touching_okx(self):
        self.fetcher._coingecko_top_symbols = lambda: {"BTC"}
        fallback_rows = [(20_000_000, f"BTC{i}/USDT:USDT", {}) for i in range(60)]

        def fake_provider(provider, whitelist):
            if provider == "okx":
                self.fail("OKX must be skipped while DEBUG_BLOCK_OKX=1")
            if provider == "bybit":
                return fallback_rows
            self.fail(f"unexpected provider after successful Bybit fallback: {provider}")

        self.fetcher._fetch_from_provider = fake_provider
        with patch.dict(os.environ, {"DEBUG_BLOCK_OKX": "1"}):
            result = self.fetcher.fetch()
        self.assertEqual(result["provider"], "bybit")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["primary_error"], "DEBUG_BLOCK_OKX_FORCED")

    def test_fallback_continues_after_bybit_block_and_selects_binance(self):
        self.fetcher._coingecko_top_symbols = lambda: {"BTC"}
        okx_rows = [(20_000_000, f"BTC{i}/USDT:USDT", {}) for i in range(20)]
        binance_rows = [(20_000_000, f"ETH{i}/USDT:USDT", {}) for i in range(60)]

        def fake_provider(provider, whitelist):
            if provider == "okx":
                return okx_rows
            if provider == "bybit":
                raise RuntimeError("403 blocked")
            if provider == "binance":
                return binance_rows
            self.fail(f"unexpected provider call after qualifying Binance fallback: {provider}")

        self.fetcher._fetch_from_provider = fake_provider
        result = self.fetcher.fetch()
        self.assertEqual(result["provider"], "binance")
        self.assertEqual(result["symbols_processed"], 60)
        self.assertTrue(result["fallback_used"])


    def test_gateio_seconds_listing_timestamp_is_normalized(self):
        seconds = 1_600_000_000
        market = self.market("BTC", 0)
        market["info"] = {"create_time": str(seconds)}
        self.assertEqual(MarketDataFetcher._listing_time_ms(market, "gateio"), seconds * 1000)

    def test_kucoin_first_open_date_is_supported(self):
        now = 1_800_000_000_000
        market = self.market("BTC", 0)
        market["info"] = {"firstOpenDate": str(now - 900 * 86_400_000)}
        self.assertEqual(MarketDataFetcher._listing_time_ms(market, "kucoinfutures"), now - 900 * 86_400_000)


if __name__ == "__main__":
    unittest.main()
