from datetime import date, timedelta
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_pit_universe as pit


class PitUniverseTests(unittest.TestCase):
    def test_lookback_excludes_current_day(self):
        start = date(2023, 1, 1)
        first = start - timedelta(days=30)
        rows = {first + timedelta(days=i): {"quote_volume": 10_000_001.0} for i in range(30)}
        rows[start] = {"quote_volume": 0.0}
        daily, members, monthly = pit.build_universe({"AAAUSDT": rows}, start, start)
        self.assertEqual(daily[0]["symbols"], ["AAAUSDT"])
        self.assertEqual(members[0]["mean_quote_volume_30d_usdt"], 10_000_001.0)
        self.assertEqual(monthly[0]["days_observed"], 1)

    def test_missing_prior_bar_excludes(self):
        start = date(2023, 1, 1)
        first = start - timedelta(days=30)
        rows = {first + timedelta(days=i): {"quote_volume": 20_000_000.0} for i in range(30) if i != 12}
        rows[start] = {"quote_volume": 30_000_000.0}
        daily, members, _ = pit.build_universe({"AAAUSDT": rows}, start, start)
        self.assertEqual(daily[0]["symbol_count"], 0)
        self.assertEqual(members, [])

    def test_threshold_is_strict(self):
        start = date(2023, 1, 1)
        first = start - timedelta(days=30)
        rows = {first + timedelta(days=i): {"quote_volume": 10_000_000.0} for i in range(30)}
        rows[start] = {"quote_volume": 99_000_000.0}
        daily, _, _ = pit.build_universe({"AAAUSDT": rows}, start, start)
        self.assertEqual(daily[0]["symbol_count"], 0)

    def test_date_range_and_leap_year(self):
        daily, _, monthly = pit.build_universe({}, date(2024, 1, 1), date(2024, 12, 31))
        self.assertEqual(len(daily), 366)
        self.assertEqual(len(monthly), 12)
        self.assertEqual(monthly[0]["month"], "2024-01")
        self.assertEqual(monthly[-1]["month"], "2024-12")

    def test_october_2026_range(self):
        daily, _, monthly = pit.build_universe({}, date(2026, 1, 1), date(2026, 10, 31))
        self.assertEqual(len(daily), 304)
        self.assertEqual(len(monthly), 10)
        self.assertEqual(monthly[-1]["month"], "2026-10")

    def test_months_cross_year(self):
        self.assertEqual(pit.months_between(date(2023, 12, 2), date(2024, 2, 3)),
                         ["2023-12", "2024-01", "2024-02"])

    def test_delivery_suffix_excluded(self):
        import re
        self.assertTrue(re.fullmatch(r"[A-Z0-9]+", "BTCUSDT"))
        self.assertFalse(re.fullmatch(r"[A-Z0-9]+", "BTCUSDT_231229"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
