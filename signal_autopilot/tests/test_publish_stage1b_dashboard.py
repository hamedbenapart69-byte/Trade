"""آزمون‌های انتشار امن گزارش Stage 1B به داشبورد عمومی."""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.publish_stage1b_dashboard import (
    HISTORY_FIELDS,
    publish_dashboard,
)


def make_report(now=None):
    now = now or datetime.now(timezone.utc)
    symbols = ["BTCUSDT"] + [f"COIN{i}USDT" for i in range(26)]
    rows = []
    for index, symbol in enumerate(symbols):
        rows.append({
            "symbol": symbol,
            "mode": "PRODUCTION",
            "decision": "WATCHLIST" if index == 0 else "NO_TRADE",
            "veto": "PASS",
            "reason": "QUALIFIED_WATCHLIST" if index == 0 else "NO_SETUP",
            "direction": "SELL" if index == 0 else None,
            "tier": "B" if index == 0 else None,
            "higher_timeframe_bias": {"4h_kumo": "BEARISH", "1h_kijun": "BEARISH"},
            "cvd": {"source": "PROXY_OHLCV"},
            "rows_available": 500,
            "stats_1h_rows_available": 2500,
            "lfs_score": 0.41,
            "lfs_status": "FULL",
            "lfs_coverage_pct": 100.0,
            "entry": 100.0 if index == 0 else None,
            "stop_loss": 101.0 if index == 0 else None,
            "take_profit": 98.0 if index == 0 else None,
            "rr": 2.0 if index == 0 else None,
            "hypothesis": "test hypothesis" if index == 0 else None,
            "falsification": "test falsification" if index == 0 else None,
            "data_sources": ["OKX_PUBLIC_SWAP_CANDLE"],
            "last_closed_candle_utc": now.isoformat(),
        })
    return {
        "generated_at_utc": now.isoformat(),
        "stage": "STAGE_1_UNCALIBRATED",
        "production_watchlist_count": 1,
        "research_candidate_count": 0,
        "universe_count": 27,
        "symbols_reported": 27,
        "symbols": rows,
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW",
    }, symbols


def write_inputs(root, report, symbols):
    report_path = root / "stage1_lrt_report.json"
    universe_path = root / "universe.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    universe_path.write_text(json.dumps({"symbols": symbols}), encoding="utf-8")
    return report_path, universe_path


class PublishStage1BDashboardTests(unittest.TestCase):
    def test_publishes_27_symbols_and_history_in_dashboard_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report_path, universe_path = write_inputs(root, report, symbols)
            result = publish_dashboard(report_path, universe_path, root)
            self.assertEqual(result["status"], "PUBLISHED")
            self.assertEqual(result["symbols"], 27)
            self.assertEqual(result["candidate_setups"], 1)

            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(len(dashboard["signals"]), 27)
            self.assertEqual(dashboard["signals"][0]["decision"], "WATCHLIST")
            self.assertEqual(dashboard["signals"][1]["decision"], "NO_QUALIFIED_SETUP")
            self.assertEqual(dashboard["data_gate_status"], "NOT_REPORTED")
            self.assertEqual(dashboard["calibration_status"], "UNCALIBRATED")
            with (root / "lrt15m_history.csv").open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), HISTORY_FIELDS)
                rows = list(reader)
            self.assertEqual(len(rows), 27)

    def test_research_candidate_never_becomes_production_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["mode"] = "RESEARCH"
            report["symbols"][0]["decision"] = "RESEARCH_WATCHLIST"
            report["production_watchlist_count"] = 0
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["candidate_setups"], 0)
            self.assertEqual(dashboard["signals"][0]["decision"], "NO_QUALIFIED_SETUP")
            self.assertTrue(dashboard["signals"][0]["research_candidate"])

    def test_rejects_wrong_symbol_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][-1]["symbol"] = "NOTINUNIVERSE"
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_UNIVERSE_SET_MISMATCH"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_stale_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report(datetime.now(timezone.utc) - timedelta(hours=7))
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_STALE"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_future_report_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report(datetime.now(timezone.utc) + timedelta(minutes=10))
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_TIMESTAMP_TOO_FAR_IN_FUTURE"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_older_report_from_replacing_newer_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime.now(timezone.utc)
            report, symbols = make_report(now)
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            older, _ = make_report(now - timedelta(hours=1))
            report_path.write_text(json.dumps(older), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "OLDER_REPORT_CANNOT_REPLACE_NEWER_DASHBOARD"):
                publish_dashboard(report_path, universe_path, root)

    def test_republishing_same_report_does_not_duplicate_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            publish_dashboard(report_path, universe_path, root)
            with (root / "lrt15m_history.csv").open(encoding="utf-8", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 27)

    def test_rejects_watchlist_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["production_watchlist_count"] = 2
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_COUNT_MISMATCH"):
                publish_dashboard(report_path, universe_path, root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
