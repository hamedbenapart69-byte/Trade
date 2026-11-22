import unittest
from pathlib import Path
from scripts.stage2_source_probe import TARGETS, URLS

class SourceProbeTests(unittest.TestCase):
    def test_universe_is_25_unique_symbols(self):
        self.assertEqual(len(TARGETS), 25)
        self.assertEqual(len(set(TARGETS)), 25)

    def test_three_real_sources_configured(self):
        self.assertEqual(set(URLS), {"CoinGecko", "OKX", "Bybit"})
        self.assertTrue(all(url.startswith("https://") for url in URLS.values()))

    def test_no_signal_or_trading_execution_in_probe(self):
        source = (Path(__file__).resolve().parents[1] / "scripts" / "stage2_source_probe.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("create_order", source)
        self.assertNotIn("place_order", source)

if __name__ == "__main__":
    unittest.main()
