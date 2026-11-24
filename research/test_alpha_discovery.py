import unittest
import pandas as pd
from research.alpha_discovery import apply_pit_membership, purged_training_window, ic_table

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



    def test_rank_ic_is_mean_daily_cross_sectional_spearman(self):
        rows = []
        first_day = pd.Timestamp("2023-01-01", tz="UTC")
        for day_index in range(30):
            day = first_day + pd.Timedelta(days=day_index)
            offset = 100 * day_index
            for rank in range(10):
                rows.append({
                    "timestamp": day,
                    "symbol": f"SYM{rank}",
                    "feature": float(offset + rank),
                    "forward_3d_return": float(rank),
                })
        result = ic_table(pd.DataFrame(rows), ["feature"])
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0]["rank_ic"], 1.0, places=12)
        self.assertEqual(result[0]["n_dates"], 30)

    def test_training_labels_are_purged_before_test_start(self):
        data = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2023-07-27T00:00:00Z",
                "2023-07-28T00:00:00Z",
                "2023-07-29T00:00:00Z",
                "2023-07-30T00:00:00Z",
                "2023-07-31T00:00:00Z",
            ], utc=True),
            "symbol": ["BTCUSDT"] * 5,
        })
        result = purged_training_window(
            data,
            pd.Timestamp("2023-07-01T00:00:00Z"),
            pd.Timestamp("2023-08-01T00:00:00Z"),
            purge_days=3,
        )
        self.assertEqual(result.timestamp.dt.strftime("%Y-%m-%d").tolist(), ["2023-07-27", "2023-07-28"])

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
