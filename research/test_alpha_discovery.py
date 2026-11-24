import unittest
import pandas as pd
from research.alpha_discovery import apply_pit_membership

class PitMembershipTests(unittest.TestCase):
    def test_only_exact_date_symbol_members_are_marked(self):
        data = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z", "2023-01-01T00:00:00Z"], utc=True),
            "symbol": ["BTCUSDT", "BTCUSDT", "ETHUSDT"],
            "close": [1.0, 2.0, 3.0],
        })
        membership = pd.DataFrame({
            "date": ["2023-01-01"],
            "symbol": ["BTCUSDT"],
        })
        result = apply_pit_membership(data, membership)
        self.assertEqual(result["_pit_member"].tolist(), [True, False, False])

    def test_duplicate_membership_keys_fail_closed(self):
        data = pd.DataFrame({
            "timestamp": pd.to_datetime(["2023-01-01T00:00:00Z"], utc=True),
            "symbol": ["BTCUSDT"],
        })
        membership = pd.DataFrame({
            "date": ["2023-01-01", "2023-01-01"],
            "symbol": ["BTCUSDT", "BTCUSDT"],
        })
        with self.assertRaisesRegex(ValueError, "duplicate"):
            apply_pit_membership(data, membership)

if __name__ == "__main__":
    unittest.main()
