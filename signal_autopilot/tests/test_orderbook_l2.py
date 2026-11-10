import json
import unittest
from modules.orderbook_l2 import apply_bybit_update, _metrics, _sorted_book


class _FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))


class KuCoinHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_is_sent_when_due_without_waiting_for_market_silence(self):
        from modules.orderbook_l2 import _kucoin_heartbeat_if_due

        ws = _FakeWebSocket()
        last_ping = await _kucoin_heartbeat_if_due(ws, 100.0, 8.0, now=107.9)
        self.assertEqual(last_ping, 100.0)
        self.assertEqual(ws.sent, [])

        last_ping = await _kucoin_heartbeat_if_due(ws, last_ping, 8.0, now=108.0)
        self.assertEqual(last_ping, 108.0)
        self.assertEqual(len(ws.sent), 1)
        self.assertEqual(ws.sent[0]["type"], "ping")


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

    def test_kucoin_level5_message_uses_public_topic_and_bid_ask_schema(self):
        from modules.orderbook_l2 import _parse_kucoin_level5
        message = {
            "topic": "/contractMarket/level2Depth5:XBTUSDTM",
            "type": "message",
            "subject": "level2",
            "sn": 1731680019100,
            "data": {
                "bids": [["89720.9", 513], ["89720.8", 12]],
                "asks": [["89721", 906], ["89721.1", 203]],
                "sequence": 1709294294670,
                "timestamp": 1731680019100,
                "ts": 1731680019100,
            },
        }
        parsed = _parse_kucoin_level5(message, {"XBTUSDTM": "BTC"})
        self.assertIsNotNone(parsed)
        symbol, book = parsed
        self.assertEqual(symbol, "BTC")
        self.assertEqual(book["bids"][0], ["89720.9", "513"])
        self.assertEqual(book["asks"][0], ["89721", "906"])
        self.assertEqual(book["sequence"], "1709294294670")

    def test_kucoin_ack_or_unknown_topic_is_not_a_book(self):
        from modules.orderbook_l2 import _parse_kucoin_level5
        self.assertIsNone(_parse_kucoin_level5({"type": "ack"}, {"XBTUSDTM": "BTC"}))


if __name__ == "__main__":
    unittest.main()
