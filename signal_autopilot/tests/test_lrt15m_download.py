import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import download_lrt15m_history as downloader


class BinanceRestKlineParsingTests(unittest.TestCase):
    def test_parses_real_futures_kline_fields_without_proxying_cvd(self):
        ts = 1_798_156_800_000
        row = [
            ts, "100.0", "105.0", "99.0", "103.0", "12.5",
            ts + 899_999, "1280.0", 42, "7.25", "742.0", "0",
        ]
        bars = downloader.parse_binance_rest_klines(
            json.dumps([row]).encode("utf-8"), ts, ts + 900_000
        )
        self.assertEqual(list(bars), [ts])
        self.assertEqual(bars[ts]["open"], 100.0)
        self.assertEqual(bars[ts]["high"], 105.0)
        self.assertEqual(bars[ts]["low"], 99.0)
        self.assertEqual(bars[ts]["close"], 103.0)
        self.assertEqual(bars[ts]["volume"], 12.5)
        self.assertEqual(bars[ts]["quote_volume"], 1280.0)
        self.assertEqual(bars[ts]["trades"], 42.0)
        self.assertEqual(bars[ts]["taker_buy_base"], 7.25)
        self.assertEqual(bars[ts]["taker_buy_quote"], 742.0)

    def test_rejects_non_list_api_error_payload(self):
        with self.assertRaises(downloader.ArchiveError):
            downloader.parse_binance_rest_klines(
                json.dumps({"code": -1000, "msg": "error"}).encode("utf-8"),
                0, 900_000,
            )

    def test_clips_rows_to_requested_window(self):
        start = 1_798_156_800_000
        rows = [
            [start - 900_000, "1", "2", "0.5", "1.5", "10", start - 1, "15", 1, "5", "7", "0"],
            [start, "1", "2", "0.5", "1.5", "10", start + 899_999, "15", 1, "5", "7", "0"],
            [start + 900_000, "1", "2", "0.5", "1.5", "10", start + 1_799_999, "15", 1, "5", "7", "0"],
        ]
        bars = downloader.parse_binance_rest_klines(
            json.dumps(rows).encode("utf-8"), start, start + 900_000
        )
        self.assertEqual(list(bars), [start])


if __name__ == "__main__":
    unittest.main()
