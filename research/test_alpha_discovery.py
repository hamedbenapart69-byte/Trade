import unittest
import pandas as pd
from research.alpha_discovery import (apply_pit_membership, purged_training_window, ic_table,
                                      build_features, deduplicate_oos_predictions)

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


    def test_price_features_are_past_only_and_available(self):
        rows = []
        first_day = pd.Timestamp("2023-01-01", tz="UTC")
        for day_index in range(70):
            day = first_day + pd.Timedelta(days=day_index)
            btc = 100.0 + day_index
            eth = 50.0 + 1.5 * day_index
            for symbol, close, volume in [
                ("BTCUSDT", btc, 1000.0 + day_index),
                ("ETHUSDT", eth, 500.0 + 2.0 * day_index),
            ]:
                rows.append({
                    "timestamp": day, "symbol": symbol, "close": close,
                    "high": close * 1.01, "low": close * 0.99,
                    "volume": volume,
                })
        data = pd.DataFrame(rows)
        original, has_funding, has_oi = build_features(data)
        self.assertFalse(has_funding)
        self.assertFalse(has_oi)
        target_day = first_day + pd.Timedelta(days=60)
        target = original[(original.symbol == "ETHUSDT") &
                          (original.timestamp == target_day)].iloc[0]
        for feature in ["ret_1d", "ret_7d", "range_pos_20", "ema_gap_20_50",
                        "volume_ratio_20", "btc_relative_mom_7d"]:
            self.assertTrue(pd.notna(target[feature]), feature)
        self.assertGreater(target["btc_relative_mom_7d"], 0.0)

        changed = data.copy()
        future_mask = changed.timestamp > target_day
        changed.loc[future_mask, "close"] *= 1.7
        changed.loc[future_mask, "high"] *= 1.7
        changed.loc[future_mask, "low"] *= 1.7
        changed.loc[future_mask, "volume"] *= 2.0
        altered, _, _ = build_features(changed)
        altered_target = altered[(altered.symbol == "ETHUSDT") &
                                 (altered.timestamp == target_day)].iloc[0]
        for feature in ["ret_1d", "ret_7d", "range_pos_20", "ema_gap_20_50",
                        "volume_ratio_20", "btc_relative_mom_7d"]:
            self.assertAlmostEqual(float(target[feature]), float(altered_target[feature]), places=12)

    def test_overlapping_walk_forward_predictions_keep_latest_fold(self):
        rows = pd.DataFrame({
            "timestamp": pd.to_datetime([
                "2023-01-01T00:00:00Z", "2023-01-01T00:00:00Z",
                "2023-01-02T00:00:00Z"
            ], utc=True),
            "symbol": ["BTCUSDT", "BTCUSDT", "ETHUSDT"],
            "fold_index": [6, 7, 6],
            "probability": [0.55, 0.70, 0.60],
            "net_return": [0.01, 0.02, 0.03],
        })
        result = deduplicate_oos_predictions(rows)
        self.assertEqual(len(result), 2)
        btc = result[result.symbol == "BTCUSDT"].iloc[0]
        self.assertEqual(int(btc.fold_index), 7)
        self.assertAlmostEqual(float(btc.probability), 0.70)

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
