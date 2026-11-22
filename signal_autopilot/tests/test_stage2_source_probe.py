import unittest\nfrom pathlib import Path
from scripts.stage2_source_probe import TARGETS, URLS
class SourceProbeTests(unittest.TestCase):
 def test_universe_is_27_unique_symbols(self):
  self.assertEqual(len(TARGETS),25)
  self.assertEqual(len(set(TARGETS)),27)
 def test_three_real_sources_configured(self):
  self.assertEqual(set(URLS),{"CoinGecko","OKX","Bybit"})
  self.assertTrue(all(u.startswith("https://") for u in URLS.values()))
 def test_no_signal_or_trading_execution_in_probe(self):
  src=(Path(__file__).resolve().parents[1] / "scripts" / "stage2_source_probe.py").read_text(encoding="utf-8").lower()
  self.assertNotIn("create_order",src)
  self.assertNotIn("place_order",src)
if __name__=="__main__": unittest.main()
