import csv
import io
import json
import sys
import zipfile
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

    def test_aggregates_exactly_15_one_minute_bars_to_one_15m_bar(self):
        one = {}
        for i in range(15):
            ts = i * 60_000
            one[ts] = {
                "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
                "close": 100.5 + i, "volume": 2.0, "quote_volume": 200.0,
                "trades": 3.0, "taker_buy_base": 1.2, "taker_buy_quote": 120.0,
            }
        bars = downloader.aggregate_1m_to_15m(one, {})
        self.assertEqual(list(bars), [0])
        bar = bars[0]
        self.assertEqual(bar["open"], 100.0)
        self.assertEqual(bar["high"], 115.0)
        self.assertEqual(bar["low"], 99.0)
        self.assertEqual(bar["close"], 114.5)
        self.assertEqual(bar["volume"], 30.0)
        self.assertEqual(bar["quote_volume"], 3000.0)
        self.assertEqual(bar["trades"], 45.0)
        self.assertEqual(bar["taker_buy_base"], 18.0)
        self.assertEqual(bar["data_source"], "BINANCE_VISION_1M_AGGREGATED")

    def test_rejects_incomplete_1m_group(self):
        one = {
            i * 60_000: {
                "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                "volume": 1.0, "quote_volume": 1.5, "trades": 1.0,
                "taker_buy_base": 0.5, "taker_buy_quote": 0.75,
            }
            for i in range(14)
        }
        self.assertEqual(downloader.aggregate_1m_to_15m(one, {}), {})

    def test_parses_bybit_kline_and_marks_cvd_as_neutral_proxy(self):
        ts = 1_798_156_800_000
        payload = {
            "retCode": 0, "retMsg": "OK",
            "result": {"list": [[str(ts), "100", "105", "99", "103", "12.5", "1280"]]},
        }
        bars = downloader.parse_bybit_klines(
            json.dumps(payload).encode("utf-8"), ts, ts + 900_000, "linear"
        )
        self.assertEqual(list(bars), [ts])
        self.assertEqual(bars[ts]["volume"], 12.5)
        self.assertEqual(bars[ts]["quote_volume"], 1280.0)
        self.assertEqual(bars[ts]["taker_buy_base"], 6.25)
        self.assertEqual(bars[ts]["data_source"], "BYBIT_LINEAR_15M")
        self.assertEqual(bars[ts]["cvd_source"], "BYBIT_CVD_UNAVAILABLE_NEUTRAL_PROXY")

    def test_parses_okx_swap_candle_and_marks_cvd_as_proxy(self):
        ts = 1_798_156_800_000
        payload = {
            "code": "0",
            "msg": "",
            "data": [[str(ts), "100", "105", "99", "103", "12", "12.5",
                      "1280", "1"]],
        }
        bars = downloader.parse_okx_history_candles(
            json.dumps(payload).encode("utf-8"), ts, ts + 900_000
        )
        self.assertEqual(list(bars), [ts])
        self.assertEqual(bars[ts]["volume"], 12.5)
        self.assertEqual(bars[ts]["quote_volume"], 1280.0)
        self.assertEqual(bars[ts]["taker_buy_base"], 6.25)
        self.assertEqual(bars[ts]["data_source"], "OKX_PUBLIC_SWAP_CANDLE")
        self.assertEqual(bars[ts]["cvd_source"], "OKX_CVD_UNAVAILABLE_NEUTRAL_PROXY")

    def test_rebuilds_ohlcv_and_taker_buy_from_aggtrades(self):
        rows = [
            ["1", "100", "2", "1", "1", "1000", "false", "true"],
            ["2", "101", "1", "2", "2", "2000", "true", "true"],
        ]
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerows(rows)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("aggTrades.csv", csv_buffer.getvalue())
        bars = downloader.parse_aggtrades_zip(zip_buffer.getvalue(), 0, 900_000)
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar["open"], 100.0)
        self.assertEqual(bar["high"], 101.0)
        self.assertEqual(bar["low"], 100.0)
        self.assertEqual(bar["close"], 101.0)
        self.assertEqual(bar["volume"], 3.0)
        self.assertEqual(bar["quote_volume"], 301.0)
        self.assertEqual(bar["trades"], 2.0)
        self.assertEqual(bar["taker_buy_base"], 2.0)
        self.assertEqual(bar["taker_buy_quote"], 200.0)

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
