import unittest
from modules.signal_engine import C10,build_signal,generate_signals
class PlaceholderEngineTests(unittest.TestCase):
    def test_missing_futures_data_is_degraded_not_fake_score(self):
        r=build_signal({"symbol":"BTC/USDT:USDT","ohlcv":None,"funding_rate":None,
          "availability":{"ohlcv":"UNAVAILABLE","funding":"UNAVAILABLE"}},"2026-11-08T00:00:00+00:00")
        self.assertEqual(r["status"],"MARKET_DATA_DEGRADED")
        self.assertEqual(r["lfs"],"NOT_CALCULABLE (missing order book)")
        self.assertNotEqual(r.get("lfs"),0.5)
    def test_exactly_seven_c10_states(self): self.assertEqual(len(C10),7)
    def test_empty_market_is_degraded(self):
        r=generate_signals({"generated_at_utc":"2026-11-08T00:00:00+00:00","symbols":[]})
        self.assertEqual(r["signals"][0]["status"],"MARKET_DATA_DEGRADED")
if __name__=="__main__": unittest.main()
