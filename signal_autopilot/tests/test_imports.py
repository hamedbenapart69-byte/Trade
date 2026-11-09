"""تست import ماژول‌های کلیدی در محیط CI و اجرای مستقیم."""

import unittest


class ModuleImportTests(unittest.TestCase):
    def test_all_module_imports(self) -> None:
        from signal_autopilot.modules.lrt15m_engine import IntegratedLRT15mEngine  # noqa: F401
        from signal_autopilot.modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy  # noqa: F401
        from signal_autopilot.modules.live_data_adapter import LiveOHLCVFetcher  # noqa: F401


if __name__ == "__main__":
    unittest.main()
