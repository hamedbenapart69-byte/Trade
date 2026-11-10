import unittest
from modules.orderbook_l2 import apply_bybit_update, _metrics, _sorted_book


class OrderBookParserTests(unittest.TestCase):
    def test_bybit_snapshot_and_delta_update(self):
        book = {"bids": {}, "asks": {}, "has_snapshot": False}
        snapshot = {"type": "snapshot", "ts": 1000, "data": {
            "u": 10, "seq": 100, "b": [["100", "2"], ["99", "3"]],
            "a": [["101", "4"], ["102", "5"]]}}
        self.assertTrue(apply_bybit_update(book, snapshot))
        delta = {"type": "delta", "ts": 1100, "data": {
            "u": 11, "seq": 101, "b": [["100", "0"], ["98", "1"]],
            "a": [["101", "6"]]}}
        self.assertTrue(apply_bybit_update(book, delta))
        self.assertNotIn("100", book["bids"])
        self.assertEqual(book["bids"]["98"], "1")
        self.assertEqual(book["asks"]["101"], "6")

    def test_delta_without_snapshot_is_rejected(self):
        book = {"bids": {}, "asks": {}, "has_snapshot": False}
        self.assertFalse(apply_bybit_update(book, {
            "type": "delta", "data": {"b": [["100", "1"]], "a": []}}))

    def test_metrics_use_native_units_and_midpoint_spread(self):
        bids, asks = _sorted_book([["99", "2"]], [["101", "3"]], 5)
        metrics = _metrics(bids, asks)
        self.assertAlmostEqual(metrics["mid_price"], 100)
        self.assertAlmostEqual(metrics["spread_bps"], 200)
        self.assertAlmostEqual(metrics["imbalance_native"], -0.2)


if __name__ == "__main__":
    unittest.main()
