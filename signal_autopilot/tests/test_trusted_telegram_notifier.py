"""Unit tests for trusted Stage 1B Telegram report delivery."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "notify_stage1b_telegram.py"
SPEC = importlib.util.spec_from_file_location("notify_stage1b_telegram", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def report():
    rows = [
        {"symbol": f"COIN{i}USDT", "decision": "NO_TRADE", "veto": "PASS"}
        for i in range(27)
    ]
    rows[0] = {
        "symbol": "BTCUSDT", "decision": "WATCHLIST", "veto": "PASS",
        "direction": "BUY", "entry": 100.0, "stop_loss": 98.0,
        "take_profit": 104.0, "rr": 2.0,
    }
    return {
        "stage": "STAGE_1_UNCALIBRATED",
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW",
        "universe_count": 27,
        "symbols_reported": 27,
        "generated_at_utc": "2026-11-11T12:00:00+00:00",
        "symbols": rows,
    }


class TrustedNotifierTests(unittest.TestCase):
    def test_validates_27_symbols_and_formats_watchlist_only(self):
        payload = report()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            checked = MODULE.validate_report(path)
        message = MODULE.build_message(checked)
        self.assertIn("NOT_CALIBRATED", message)
        self.assertIn("WATCHLIST فقط", message)
        self.assertIn("BTCUSDT | BUY", message)
        self.assertIn("Entry 100", message)
        self.assertIn("BUY_NOW/SELL_NOW صادر نمی‌شود", message)

    def test_rejects_incomplete_universe(self):
        payload = report()
        payload["symbols"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "UNIVERSE_COVERAGE_INVALID|SYMBOL_ROWS_INVALID"):
                MODULE.validate_report(path)

    def test_no_candidates_still_produces_daily_report(self):
        payload = report()
        payload["symbols"] = [
            {"symbol": f"COIN{i}USDT", "decision": "NO_TRADE", "veto": "PASS"}
            for i in range(27)
        ]
        message = MODULE.build_message(payload)
        self.assertIn("نامزدهای زیرنظر: 0", message)
        self.assertIn("هیچ موقعیت WATCHLIST", message)

    def test_rejects_non_finite_levels(self):
        payload = report()
        payload["symbols"][0]["entry"] = float("nan")
        self.assertEqual(MODULE.candidate_rows(payload), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
