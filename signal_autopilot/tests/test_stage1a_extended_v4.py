import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_stage1a_extended_v4 as v4


class Stage1aV4Tests(unittest.TestCase):
    def test_coingecko_filters_binance_usdt_perpetuals(self):
        rows = [
            {"market": "Binance (Futures)", "contract_type": "perpetual",
             "symbol": "BTCUSDT", "volume": "75000000", "expired_at": None},
            {"market": "Binance (Futures)", "contract_type": "perpetual",
             "symbol": "ETHUSDT", "volume": "49000000", "expired_at": None},
            {"market": "Other", "contract_type": "perpetual",
             "symbol": "SOLUSDT", "volume": "90000000", "expired_at": None},
            {"market": "Binance (Futures)", "contract_type": "futures",
             "symbol": "XRPUSDT", "volume": "90000000", "expired_at": None},
        ]
        parsed = v4.parse_coingecko_derivatives(rows)
        self.assertEqual(set(parsed), {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(parsed["BTCUSDT"]["quote_volume_24h_usd"], 75_000_000)

    def test_snapshot_rejects_stale_data(self):
        with patch.object(v4.SNAPSHOT_PATH, "exists", return_value=True), \
             patch.object(v4.SNAPSHOT_PATH, "read_text", return_value='{"captured_at_utc":"2020-01-01T00:00:00Z","symbols":[]}'):
            with self.assertRaises(v4.downloader.FetchFailure):
                v4.load_snapshot()

    def test_s3_symbol_prefix_extraction(self):
        fake = [
            "data/futures/um/monthly/klines/BTCUSDT/",
            "data/futures/um/monthly/klines/ETHUSDT/",
            "data/futures/um/monthly/klines/ETHUSDT/",
        ]
        with patch.object(v4, "s3_list", return_value=fake):
            self.assertEqual(v4.discover_s3_symbols(), ["BTCUSDT", "ETHUSDT"])

    def test_binance_ticker_uses_quote_volume(self):
        parsed = v4.parse_binance_tickers([
            {"symbol": "BTCUSDT", "quoteVolume": "51000000", "volume": "100"},
        ])
        self.assertEqual(parsed["BTCUSDT"], 51_000_000)


if __name__ == "__main__":
    unittest.main()
