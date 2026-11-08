import json
import tempfile
import unittest
from pathlib import Path

from modules.data_fetcher import MarketDataFetcher


class FakeExchange:
    def __init__(self, markets, tickers):
        self.markets = markets
        self._tickers = tickers

    def load_markets(self):
        return self.markets

    def fetch_tickers(self):
        return self._tickers


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


if __name__ == "__main__":
    unittest.main()
