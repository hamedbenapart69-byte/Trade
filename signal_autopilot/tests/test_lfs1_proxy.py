import unittest

from modules.lfs1_proxy import calculate_lfs1_proxy, aggregate_lfs_v2


class LFS1ProxyTests(unittest.TestCase):
    def candles(self, count=70):
        rows = []
        price = 100.0
        for i in range(count):
            price *= 1.001
            rows.append({"timestamp": i * 3_600_000, "open": price * 0.999,
                         "high": price * 1.005, "low": price * 0.995,
                         "close": price, "volume": 1000 + (i % 7) * 10})
        return rows

    def test_proxy_is_explicitly_labeled_and_not_real(self):
        result = calculate_lfs1_proxy(self.candles())
        self.assertEqual(result["data_class"], "PROXY")
        self.assertFalse(result["real_orderbook_used"])
        self.assertEqual(result["calibration"], "NOT_CALIBRATED")

    def test_insufficient_data_is_unavailable_not_zero(self):
        result = calculate_lfs1_proxy(self.candles(30))
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertNotIn("score", result)

    def test_lfs_v2_does_not_fill_missing_components_with_zero(self):
        result = aggregate_lfs_v2({"LFS1": 0.9, "LFS2": 0.2})
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(set(result["missing_components"]), {"LFS3", "LFS4", "LFS5"})


if __name__ == "__main__":
    unittest.main()
