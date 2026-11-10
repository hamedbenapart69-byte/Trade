"""قرارداد ایمنی وضعیت موتور یک‌ساعته و داشبورد."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LegacyStatusContractTests(unittest.TestCase):
    def test_config_and_dashboard_status_are_consistently_quarantined(self):
        config = json.loads((ROOT / "signal_autopilot" / "config.json").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "web" / "futures" / "system_status.json").read_text(encoding="utf-8"))
        engine = config["engine"]

        self.assertEqual(engine["lifecycle"], "LEGACY_RESEARCH_ONLY")
        self.assertIs(engine["production_enabled"], False)
        self.assertEqual(status["lifecycle"], engine["lifecycle"])
        self.assertIs(status["production_enabled"], False)
        self.assertIs(status["market_scan_enabled"], False)
        self.assertIs(status["dashboard_signal_publication_enabled"], False)
        self.assertIs(status["telegram_signal_delivery_enabled"], False)
        self.assertEqual(status["output_state"], "NO_QUALIFIED_SETUP")
        self.assertEqual(status["reason"], "LEGACY_ENGINE_QUARANTINED")

    def test_dashboard_contains_quarantine_status_mount(self):
        html = (ROOT / "web" / "futures" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "web" / "futures" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="legacy-engine-status"', html)
        self.assertIn('LEGACY_STATUS_URL = "./system_status.json"', javascript)
        self.assertIn("loadLegacyEngineStatus();", javascript)


if __name__ == "__main__":
    unittest.main()
