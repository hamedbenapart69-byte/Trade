import sys
import unittest
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_stage1a_extended_v3 import (
    build_universe,
    parse_tickers,
    strict_request_bytes,
)


def ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


class FullBinanceUniverseTests(unittest.TestCase):
    def test_filters_full_usdtm_perpetuals_by_volume_and_listing_age(self):
        symbols = [
            {
                "symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                "quoteAsset": "USDT", "marginAsset": "USDT", "onboardDate": ms("2019-09-08"),
            },
            {
                "symbol": "ETHUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                "quoteAsset": "USDT", "marginAsset": "USDT", "onboardDate": ms("2025-01-01"),
            },
            {
                "symbol": "LOWUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                "quoteAsset": "USDT", "marginAsset": "USDT", "onboardDate": ms("2019-01-01"),
            },
            {
                "symbol": "NODATEUSDT", "status": "TRADING", "contractType": "PERPETUAL",
                "quoteAsset": "USDT", "marginAsset": "USDT",
            },
            {
                "symbol": "INACTIVEUSDT", "status": "SETTLING", "contractType": "PERPETUAL",
                "quoteAsset": "USDT", "marginAsset": "USDT", "onboardDate": ms("2018-01-01"),
            },
            {
                "symbol": "BTCUSDC", "status": "TRADING", "contractType": "PERPETUAL",
                "quoteAsset": "USDC", "marginAsset": "USDC", "onboardDate": ms("2018-01-01"),
            },
        ]
        volumes = {
            "BTCUSDT": 90_000_000,
            "ETHUSDT": 60_000_000,
            "LOWUSDT": 49_999_999,
            "NODATEUSDT": 70_000_000,
        }
        metadata, candidates, inventory, counts = build_universe(
            symbols, volumes, date(2024, 11, 9)
        )

        self.assertEqual(counts["binance_usdtm_perpetuals_total"], 4)
        self.assertEqual(counts["symbols_volume_50m"], 3)
        self.assertEqual(counts["symbols_listing_730d"], 1)
        self.assertEqual(counts["listing_metadata_missing"], 1)
        self.assertEqual(candidates, ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(metadata["BTCUSDT"]["quote_volume_24h_usd"], 90_000_000)
        classes = {row["symbol"]: row["classification"] for row in inventory}
        self.assertEqual(classes["LOWUSDT"], "EXCLUDED_VOLUME_BELOW_50M")
        self.assertEqual(classes["BTCUSDT"], "QUALIFYING_VOLUME_AND_LISTING_AGE")
        self.assertEqual(classes["ETHUSDT"], "EXCLUDED_LISTED_WITHIN_730D")
        self.assertEqual(classes["NODATEUSDT"], "EXCLUDED_LISTING_DATE_UNAVAILABLE")

    def test_ticker_parser_uses_quote_volume_only(self):
        parsed = parse_tickers([
            {"symbol": "BTCUSDT", "quoteVolume": "51000000", "volume": "1000"},
            {"symbol": "ETHUSDT", "quoteVolume": "49000000", "volume": "2000"},
        ])
        self.assertEqual(parsed["BTCUSDT"], 51_000_000)
        self.assertEqual(parsed["ETHUSDT"], 49_000_000)

    def test_404_is_not_retried(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            status, payload = strict_request_bytes("https://example.invalid/file.zip", "HEAD")

        self.assertEqual(status, 404)
        self.assertEqual(payload, b"")
        self.assertEqual(calls["count"], 1)

    def test_429_is_not_retried(self):
        calls = {"count": 0}

        def fake_urlopen(request, timeout=0):
            calls["count"] += 1
            raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, None)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            status, _ = strict_request_bytes("https://example.invalid/api", "GET")

        self.assertEqual(status, 429)
        self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
