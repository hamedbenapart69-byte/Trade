"""تست import ماژول‌های واقعی موجود در مخزن، در محیط CI."""

import unittest


class ModuleImportTests(unittest.TestCase):
    def test_all_module_imports(self) -> None:
        from signal_autopilot.modules.lrt15m_engine import analyze_symbol, detect_sweep, run
        from signal_autopilot.modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy
        from signal_autopilot.modules.live_data_adapter import LiveOHLCVFetcher, is_closed_candle

        self.assertTrue(callable(analyze_symbol))
        self.assertTrue(callable(detect_sweep))
        self.assertTrue(callable(run))
        self.assertEqual(CVD_SOURCE, "PROXY_OHLCV")
        self.assertTrue(callable(calculate_cvd_proxy))
        self.assertTrue(callable(LiveOHLCVFetcher))
        self.assertTrue(callable(is_closed_candle))


if __name__ == "__main__":
    unittest.main()
