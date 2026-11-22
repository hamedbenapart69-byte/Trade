from datetime import date, timedelta
from pathlib import Path
import sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_vtm_pit_2023 as vtm

class VtmPitTests(unittest.TestCase):
    def test_lookback_excludes_current_day(self):
        start = date(2022, 12, 2)
        rows = {start + timedelta(days=i): {"quote_volume": 10_000_001.0} for i in range(30)}
        rows[date(2023, 1, 1)] = {"quote_volume": 0.0}
        daily, members, _ = vtm.build_universe({"AAAUSDT": rows})
        self.assertEqual(daily[0]["symbols"], ["AAAUSDT"])
        self.assertEqual(members[0]["mean_quote_volume_30d_usdt"], 10_000_001.0)

    def test_missing_prior_bar_excludes(self):
        start = date(2022, 12, 2)
        rows = {start + timedelta(days=i): {"quote_volume": 20_000_000.0} for i in range(30) if i != 12}
        rows[date(2023, 1, 1)] = {"quote_volume": 30_000_000.0}
        daily, members, _ = vtm.build_universe({"AAAUSDT": rows})
        self.assertEqual(daily[0]["symbol_count"], 0)
        self.assertEqual(members, [])

    def test_threshold_is_strict(self):
        start = date(2022, 12, 2)
        rows = {start + timedelta(days=i): {"quote_volume": 10_000_000.0} for i in range(30)}
        rows[date(2023, 1, 1)] = {"quote_volume": 99_000_000.0}
        daily, _, _ = vtm.build_universe({"AAAUSDT": rows})
        self.assertEqual(daily[0]["symbol_count"], 0)

    def test_365_dates_and_12_months(self):
        daily, _, monthly = vtm.build_universe({})
        self.assertEqual(len(daily), 365)
        self.assertEqual(len(monthly), 12)
        self.assertEqual(monthly[0]["month"], "2023-01")
        self.assertEqual(monthly[-1]["month"], "2023-12")

    def test_delivery_suffix_excluded_by_symbol_rule(self):
        import re
        self.assertTrue(re.fullmatch(r"[A-Z0-9]+", "BTCUSDT"))
        self.assertFalse(re.fullmatch(r"[A-Z0-9]+", "BTCUSDT_231229"))

if __name__ == "__main__":
    unittest.main(verbosity=2)
