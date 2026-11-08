import unittest
from modules.signal_engine import build_signal, C10
class PlaceholderSignalTests(unittest.TestCase):
 def test_missing_inputs_degrade(self):
  row={"symbol":"BTC/USDT:USDT","availability":{"ohlcv":"UNAVAILABLE","funding":"UNAVAILABLE"},"ohlcv":[]}
  result=build_signal(row,"2026-11-08T00:00:00+00:00")
  self.assertEqual(result["status"],"MARKET_DATA_DEGRADED")
  self.assertIn("NOT_CALCULABLE",result["lfs"])
  self.assertIsNone(result.get("score"))
 def test_status_in_c10(self):
  row={"symbol":"BTC/USDT:USDT","availability":{"ohlcv":"UNAVAILABLE","funding":"UNAVAILABLE"},"ohlcv":[]}
  result=build_signal(row,"2026-11-08T00:00:00+00:00")
  self.assertIn(result["status"],C10)
if __name__=="__main__": unittest.main()
