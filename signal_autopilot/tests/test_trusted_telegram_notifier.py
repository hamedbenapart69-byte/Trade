"""Unit tests for trusted Stage 1B Telegram report delivery."""
import importlib.util
import io
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
    generated = datetime.now(timezone.utc)
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
        "cvd": {"source": "PROXY_OHLCV"},
        "lfs_score": 0.72,
        "lfs_status": "FULL",
        "lfs_coverage_pct": 100.0,
        "lfs_veto": "PASS",
        "lfs_threshold": 0.70,
        "lfs_threshold_reason": "PROXY_OR_PARTIAL_DATA",
        "last_closed_candle_utc": (generated - timedelta(minutes=15)).isoformat(),
    }
    return {
        "stage": "STAGE_1_UNCALIBRATED",
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW",
        "universe_count": 27,
        "symbols_reported": 27,
        "production_watchlist_count": 1,
        "generated_at_utc": generated.isoformat(),
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
        self.assertIn("CVD: PROXY_OHLCV", message)
        self.assertIn("LFS: 0.720 | status=FULL | coverage=100.0% | gate=PASS | threshold=0.70 (PROXY_OR_PARTIAL_DATA)", message)
        self.assertIn("Hypothesis:", message)
        self.assertIn("Falsification:", message)
        self.assertIn("https://trade.example.pages.dev", message)
        self.assertIn("BUY_NOW/SELL_NOW صادر نمی‌شود", message)

    def test_rejects_production_watchlist_count_mismatch(self):
        payload = report()
        payload["production_watchlist_count"] = 0
        with self.assertRaisesRegex(ValueError, "PRODUCTION_WATCHLIST_COUNT_MISMATCH"):
            validate_in_temp(payload)

    def test_rejects_executable_production_decisions(self):
        payload = report()
        payload["symbols"][0]["decision"] = "BUY_NOW"
        payload["production_watchlist_count"] = 0
        with self.assertRaisesRegex(ValueError, "PRODUCTION_EXECUTABLE_DECISION_FORBIDDEN"):
            validate_in_temp(payload)

    def test_rejects_stale_or_unclosed_watchlist_candle(self):
        payload = report()
        payload["symbols"][0]["last_closed_candle_utc"] = (
            datetime.now(timezone.utc) - timedelta(minutes=46)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "WATCHLIST_CANDLE_STALE"):
            validate_in_temp(payload)
        payload = report()
        payload["symbols"][0]["last_closed_candle_utc"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        ).isoformat()
        with self.assertRaisesRegex(ValueError, "WATCHLIST_CANDLE_NOT_CLOSED_AT_REPORT_TIME"):
            validate_in_temp(payload)

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
        payload["production_watchlist_count"] = 0
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

    def test_rejects_watchlist_with_non_pass_veto(self):
        payload = report()
        payload["symbols"][0]["veto"] = "DATA_UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "WATCHLIST_VETO_NOT_PASS"):
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

    def test_large_candidate_set_is_split_under_telegram_limit(self):
        payload = report()
        long_text = "x" * 600
        for row in payload["symbols"]:
            row.update({
                "mode": "PRODUCTION",
                "decision": "WATCHLIST",
                "veto": "PASS",
                "direction": "BUY",
                "entry": 100.0,
                "stop_loss": 98.0,
                "take_profit_1": 102.0,
                "take_profit": 104.0,
                "rr": 2.0,
                "lfs_score": 0.72,
                "lfs_status": "FULL",
                "lfs_coverage_pct": 100.0,
                "lfs_veto": "PASS",
                "lfs_threshold": 0.70,
                "lfs_threshold_reason": "PROXY_OR_PARTIAL_DATA",
                "hypothesis": long_text,
                "falsification": long_text,
            })
        messages = MODULE.build_messages(payload, "https://trade.example.pages.dev")
        self.assertGreater(len(messages), 1)
        self.assertTrue(all(len(message) <= MODULE.MAX_MESSAGE_LENGTH for message in messages))

    def test_rejects_placeholder_hypothesis_and_falsification(self):
        payload = report()
        payload["symbols"][0]["hypothesis"] = "UNAVAILABLE"
        with self.assertRaisesRegex(ValueError, "WATCHLIST_HYPOTHESIS_MISSING"):
            MODULE.candidate_rows(payload)
        payload = report()
        payload["symbols"][0]["falsification"] = "N/A"
        with self.assertRaisesRegex(ValueError, "WATCHLIST_FALSIFICATION_MISSING"):
            MODULE.candidate_rows(payload)

    def test_rejects_watchlist_below_effective_lfs_threshold(self):
        payload = report()
        payload["symbols"][0]["lfs_score"] = 0.65
        with self.assertRaisesRegex(ValueError, "WATCHLIST_LFS_GATE_MISMATCH"):
            MODULE.candidate_rows(payload)

    def test_rejects_lfs_score_or_coverage_outside_valid_range(self):
        payload = report()
        payload["symbols"][0]["lfs_score"] = 1.2
        with self.assertRaisesRegex(ValueError, "WATCHLIST_LFS_SCORE_OUT_OF_RANGE"):
            MODULE.candidate_rows(payload)
        payload = report()
        payload["symbols"][0]["lfs_coverage_pct"] = 101.0
        with self.assertRaisesRegex(ValueError, "WATCHLIST_LFS_COVERAGE_OUT_OF_RANGE"):
            MODULE.candidate_rows(payload)

    def test_dashboard_url_must_be_https_and_configured(self):
        with self.assertRaisesRegex(ValueError, "DASHBOARD_URL_UNAVAILABLE_OR_INVALID"):
            MODULE.validate_dashboard_url("")
        with self.assertRaisesRegex(ValueError, "DASHBOARD_URL_UNAVAILABLE_OR_INVALID"):
            MODULE.validate_dashboard_url("http://example.com")

    def test_verify_destination_only_runs_without_report_artifact(self):
        args = ["notify_stage1b_telegram.py", "--verify-destination-only"]
        env = {
            "TELEGRAM_TOKEN": "12345:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "-1001234567890",
            "TELEGRAM_EXPECTED_CHANNEL_TITLE": "Trade Alerts",
        }
        with patch.object(sys, "argv", args), patch.dict(os.environ, env, clear=True), patch.object(MODULE, "verify_telegram_destination") as verify:
            self.assertEqual(MODULE.main(), 0)
            verify.assert_called_once()

    def test_telegram_config_rejects_missing_or_malformed_credentials(self):
        with self.assertRaisesRegex(ValueError, "TELEGRAM_TOKEN_INVALID_OR_MISSING"):
            MODULE.validate_telegram_config("", "-1001234567890", "Trade Alerts")
        with self.assertRaisesRegex(ValueError, "TELEGRAM_CHAT_ID_INVALID_OR_MISSING"):
            MODULE.validate_telegram_config("12345:abcdefghijklmnopqrstuvwxyz", "not-a-chat", "Trade Alerts")

    def test_telegram_delivery_confirms_returned_chat_id(self):
        response = {
            "ok": True,
            "result": {
                "message_id": 42,
                "chat": {"id": -1001234567890, "type": "channel"},
            },
        }
        with patch.dict(os.environ, {"TELEGRAM_EXPECTED_CHANNEL_TITLE": "Trade Alerts"}), patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode("utf-8"))):
            MODULE.send_message("12345:abcdefghijklmnopqrstuvwxyz", "-1001234567890", "test message")

    def test_telegram_delivery_rejects_destination_mismatch(self):
        response = {
            "ok": True,
            "result": {
                "message_id": 42,
                "chat": {"id": 999999, "type": "channel"},
            },
        }
        with patch.dict(os.environ, {"TELEGRAM_EXPECTED_CHANNEL_TITLE": "Trade Alerts"}), patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode("utf-8"))):
            with self.assertRaisesRegex(RuntimeError, "TELEGRAM_DESTINATION_MISMATCH"):
                MODULE.send_message("12345:abcdefghijklmnopqrstuvwxyz", "-1001234567890", "test message")

    def test_destination_preflight_verifies_channel_without_sending(self):
        args = ["notify_stage1b_telegram.py", "--verify-destination-only"]
        environment = {
            "TELEGRAM_TOKEN": "12345:abcdefghijklmnopqrstuvwxyz",
            "TELEGRAM_CHAT_ID": "-1001234567890",
            "TELEGRAM_EXPECTED_CHANNEL_TITLE": "Trade Alerts",
        }
        with patch.object(sys, "argv", args), patch.dict(os.environ, environment, clear=True), patch.object(MODULE, "verify_telegram_destination") as verify, patch.object(MODULE, "send_message") as sender:
            self.assertEqual(MODULE.main(), 0)
            verify.assert_called_once()
            sender.assert_not_called()

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
            with patch.object(sys, "argv", args), patch.dict(os.environ, {"DASHBOARD_URL": "https://trade.example.pages.dev"}, clear=True), patch.object(MODULE, "verify_telegram_destination") as verify, patch.object(MODULE, "send_message") as sender:
                self.assertEqual(MODULE.main(), 0)
                verify.assert_not_called()
                sender.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
