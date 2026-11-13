"""تست import ماژول‌های واقعی موجود در مخزن، در محیط CI."""

import unittest


class ModuleImportTests(unittest.TestCase):
    def test_all_module_imports(self) -> None:
        # CI و Stage 1b این تست را از working-directory=signal_autopilot اجرا می‌کنند.
        from modules.lrt15m_engine import evaluate_stage1_symbol, detect_sweep, run
        from modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy
        from modules.live_data_adapter import LiveOHLCVFetcher, is_closed_candle

        self.assertTrue(callable(evaluate_stage1_symbol))
        self.assertTrue(callable(detect_sweep))
        self.assertTrue(callable(run))
        self.assertEqual(CVD_SOURCE, "PROXY_OHLCV")
        self.assertTrue(callable(calculate_cvd_proxy))
        self.assertTrue(callable(LiveOHLCVFetcher))
        self.assertTrue(callable(is_closed_candle))


if __name__ == "__main__":
    unittest.main()
