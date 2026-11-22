import unittest
from datetime import date
from scripts.binance_vision_derivatives_1d import SYMBOLS, months

class DerivativesArchiveTests(unittest.TestCase):
    def test_universe_has_25_symbols(self):
        self.assertEqual(len(SYMBOLS),25)
        self.assertEqual(len(set(SYMBOLS)),25)
    def test_months_are_inclusive(self):
        self.assertEqual([x.isoformat() for x in months(date(2024,11,12),date(2025,1,2))],
                         ["2024-11-01","2024-12-01","2025-01-01"])

if __name__=="__main__": unittest.main()
