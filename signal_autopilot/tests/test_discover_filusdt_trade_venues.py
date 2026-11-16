"""آزمون‌های آفلاین فیلتر پوشش نماد در منابع مستقل."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "discover_filusdt_trade_venues.py"
SPEC = importlib.util.spec_from_file_location("discover_filusdt_trade_venues", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VenueDiscoveryTests(unittest.TestCase):
    def test_exact_symbol_is_distinguished_from_candidates(self):
        result = MODULE.summarize_symbol_coverage(
            "bybit",
            ["BTCUSDT", "FILUSDT", "FIL-USDT-SWAP", "1000PEPEUSDT"],
        )
        self.assertTrue(result["exact_target_symbol"])
        self.assertEqual(result["fil_related_candidates"], ["FIL-USDT-SWAP", "FILUSDT"])
        self.assertEqual(result["instrument_equivalence"], "NOT_ESTABLISHED")

    def test_candidate_only_does_not_claim_exact_match(self):
        result = MODULE.summarize_symbol_coverage("okx_futures", ["FIL-USDT-SWAP"])
        self.assertFalse(result["exact_target_symbol"])
        self.assertEqual(result["fil_related_candidates"], ["FIL-USDT-SWAP"])


if __name__ == "__main__":
    unittest.main()
