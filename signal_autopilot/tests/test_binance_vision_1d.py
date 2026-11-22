import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from scripts.binance_vision_1d import ArchiveResult, SYMBOLS, archive_url, month_starts, run

class BinanceVision1DTests(unittest.TestCase):
    def test_universe_is_25_unique_symbols(self):
        self.assertEqual(len(SYMBOLS), 25)
        self.assertEqual(len(set(SYMBOLS)), 25)
        self.assertNotIn("HOTUSDT", SYMBOLS)
        self.assertNotIn("1000PEPEUSDT", SYMBOLS)

    def test_month_range_inclusive(self):
        self.assertEqual([d.isoformat() for d in month_starts(date(2024,11,20),date(2025,1,2))],
                         ["2024-11-01","2024-12-01","2025-01-01"])

    def test_archive_url(self):
        self.assertEqual(archive_url("BTCUSDT",date(2025,2,1)),
          "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-02.zip")

    def test_missing_archive_is_partial_not_fabricated(self):
        fake=ArchiveResult("BTCUSDT","2025-01","u","FAIL",404,0,None,0,"HTTP_404")
        with tempfile.TemporaryDirectory() as tmp, patch("scripts.binance_vision_1d.fetch_archive",return_value=(fake,pd.DataFrame())), patch("scripts.binance_vision_1d.SYMBOLS",("BTCUSDT",)):
            report=run(date(2025,1,1),date(2025,1,31),Path(tmp),1)
        self.assertEqual(report["overall_status"],"PARTIAL")
        self.assertEqual(report["symbols"][0]["rows"],0)

if __name__ == "__main__":
    unittest.main()
