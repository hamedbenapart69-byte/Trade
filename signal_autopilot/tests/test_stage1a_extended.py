import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_funding_unit import classify_unit
from download_stage1a_extended_history import archive_urls, month_starts
from datetime import date


class FundingUnitTests(unittest.TestCase):
    def test_decimal_rate_is_detected(self):
        result = classify_unit(0.000126, 0.000125)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["unit"], "DECIMAL")

    def test_percent_rate_is_detected(self):
        result = classify_unit(0.0126, 0.000126)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["unit"], "PERCENT")

    def test_ambiguous_rate_is_not_guessed(self):
        result = classify_unit(0.0001, 0.0001)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["unit"], "DECIMAL")

    def test_near_zero_is_unverified(self):
        result = classify_unit(0.0, 0.0)
        self.assertEqual(result["status"], "UNVERIFIED")


class ArchiveWindowTests(unittest.TestCase):
    def test_months_cover_two_year_window(self):
        months = month_starts(date(2024, 11, 9), date(2026, 11, 9))
        self.assertEqual(len(months), 24)
        self.assertEqual(months[0], date(2024, 11, 1))
        self.assertEqual(months[-1], date(2026, 10, 1))

    def test_daily_tail_covers_partial_end_month(self):
        urls = list(archive_urls("BTCUSDT", date(2024, 11, 9), date(2026, 11, 9)))
        daily = [url for url, kind in urls if kind == "daily"]
        self.assertEqual(len(daily), 8)
        self.assertIn("BTCUSDT-1h-2026-11-08.zip", daily[-1])


if __name__ == "__main__":
    unittest.main()
