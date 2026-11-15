"""Unit tests for trusted Stage 1B Telegram report delivery."""
import importlib.util
import json
import os
import sys
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
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
        "symbol": "BTCUSDT", "mode": "PRODUCTION", "decision": "WATCHLIST", "veto": "PASS",
        "direction": "BUY", "entry": 100.0, "stop_loss": 98.0,
        "take_profit_1": 102.0, "take_profit": 104.0, "rr": 2.0,
        "hypothesis": "Liquidity sweep and reclaim support a mean-reversion move.",
        "falsification": "A 15m close below the stop invalidates the setup.",
    }
    return {
        "stage": "STAGE_1_UNCALIBRATED",
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW",
        "universe_count": 27,
        "symbols_reported": 27,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbols": rows,
    }


def validate_in_temp(payload, now=None, universe_symbols=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_path = root / "report.json"
        universe_path = root / "universe.json"
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        symbols = universe_symbols or [row["symbol"] for row in payload["symbols"]]
        universe_path.write_text(json.dumps({"symbols": symbols}), encoding="utf-8")
        return MODULE.validate_report(report_path, universe_path, now=now)


class TrustedNotifierTests(unittest.TestCase):
    def test_validates_exact_universe_and_formats_watchlist_only(self):
        checked = validate_in_temp(report())
        messages = MODULE.build_messages(checked, "https://trade.example.pages.dev")
        message = "\n".join(messages)
        self.assertIn("NOT_CALIBRATED", message)
        self.assertIn("WATCHLIST فقط", message)
        self.assertIn("BTCUSDT | BUY", message)
        self.assertIn("Entry: 100", message)
        self.assertIn("TP1: 102", message)
        self.assertIn("TP2: 104", message)
        self.assertIn("Confidence: NOT_CALIBRATED", message)
        self.assertIn("Hypothesis:", message)
        self.assertIn("Falsification:", message)
        self.assertIn("https://trade.example.pages.dev", message)
        self.assertIn("BUY_NOW/SELL_NOW صادر نمی‌شود", message)

    def test_rejects_incomplete_universe(self):
        payload = report()
        expected_symbols = [row["symbol"] for row in payload["symbols"]]
        payload["symbols"].pop()
        with self.assertRaisesRegex(ValueError, "UNIVERSE_COVERAGE_INVALID|SYMBOL_ROWS_INVALID"):
            validate_in_temp(payload, universe_symbols=expected_symbols)

    def test_rejects_wrong_symbol_set_even_when_count_is_27(self):
        payload = report()
        expected_symbols = [row["symbol"] for row in payload["symbols"]]
        payload["symbols"][-1]["symbol"] = "NOTINUNIVERSE"
        with self.assertRaisesRegex(ValueError, "UNIVERSE_SYMBOL_SET_MISMATCH"):
            validate_in_temp(payload, universe_symbols=expected_symbols)

    def test_rejects_stale_report(self):
        payload = report()
        payload["generated_at_utc"] = (datetime.now(timezone.utc) - timedelta(hours=4, minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "REPORT_STALE"):
            validate_in_temp(payload)

    def test_rejects_timestamp_too_far_in_future(self):
        payload = report()
        payload["generated_at_utc"] = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        with self.assertRaisesRegex(ValueError, "REPORT_TIMESTAMP_TOO_FAR_IN_FUTURE"):
            validate_in_temp(payload)

    def test_no_candidates_still_produces_daily_report(self):
        payload = report()
        payload["symbols"] = [
            {"symbol": f"COIN{i}USDT", "decision": "NO_TRADE", "veto": "PASS"}
            for i in range(27)
        ]
        message = "\n".join(MODULE.build_messages(payload, "https://trade.example.pages.dev"))
        self.assertIn("نامزدهای زیرنظر: 0", message)
        self.assertIn("هیچ موقعیت WATCHLIST", message)

    def test_rejects_non_finite_levels(self):
        payload = report()
        payload["symbols"][0]["entry"] = float("nan")
        with self.assertRaisesRegex(ValueError, "WATCHLIST_LEVELS_INVALID"):
            MODULE.candidate_rows(payload)

    def test_rejects_directionally_inverted_levels(self):
        payload = report()
        payload["symbols"][0]["stop_loss"] = 101.0
        with self.assertRaisesRegex(ValueError, "WATCHLIST_LEVEL_DIRECTION_INVALID"):
            MODULE.candidate_rows(payload)

    def test_rejects_declared_risk_reward_mismatch(self):
        payload = report()
        payload["symbols"][0]["rr"] = 3.0
        with self.assertRaisesRegex(ValueError, "WATCHLIST_RR_MISMATCH"):
            MODULE.candidate_rows(payload)

    def test_research_mode_is_never_sent_as_production_watchlist(self):
        payload = report()
        payload["symbols"][0]["mode"] = "RESEARCH"
        self.assertEqual(MODULE.candidate_rows(payload), [])

    def test_rejects_placeholder_hypothesis_and_falsification(self):
        payload = report()
        payload["symbols"][0]["hypothesis"] = "UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "WATCHLIST_HYPOTHESIS_MISSING"):
            MODULE.candidate_rows(payload)
        payload = report()
        payload["symbols"][0]["falsification"] = "N/A"
        with self.assertRaisesRegex(ValueError, "WATCHLIST_FALSIFICATION_MISSING"):
            MODULE.candidate_rows(payload)

    def test_dashboard_url_must_be_https_and_configured(self):
        with self.assertRaisesRegex(ValueError, "DASHBOARD_URL_UNAVAILABLE_OR_INVALID"):
            MODULE.validate_dashboard_url("")
        with self.assertRaisesRegex(ValueError, "DASHBOARD_URL_UNAVAILABLE_OR_INVALID"):
            MODULE.validate_dashboard_url("http://example.com")

    def test_validate_only_never_sends_telegram(self):
        payload = report()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / "report.json"
            universe_path = root / "universe.json"
            report_path.write_text(json.dumps(payload), encoding="utf-8")
            universe_path.write_text(
                json.dumps({"symbols": [row["symbol"] for row in payload["symbols"]]}),
                encoding="utf-8",
            )
            args = [
                "notify_stage1b_telegram.py", "--report", str(report_path),
                "--universe", str(universe_path), "--validate-only",
            ]
            with patch.object(sys, "argv", args), patch.dict(os.environ, {"DASHBOARD_URL": "https://trade.example.pages.dev"}), patch.object(MODULE, "send_message") as sender:
                self.assertEqual(MODULE.main(), 0)
                sender.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
