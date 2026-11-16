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
            "lfs_score": 0.75,
            "lfs_status": "FULL",
            "lfs_components": {
                "LFS1": {"status": "REAL"},
                "LFS2": {"status": "REAL"},
                "LFS3": {"status": "REAL"},
                "LFS4": {"status": "REAL"},
                "LFS5": {"status": "REAL"},
            },
            "lfs_coverage_pct": 100.0,
            "lfs_veto": "PASS",
            "lfs_threshold": 0.30,
            "lfs_threshold_reason": "ALL_FIVE_COMPONENTS_REAL",
            "lfs_threshold_method": "FIXED_BASELINE_0.30_NOT_ROLLING_90D",
            "entry": 100.0 if index == 0 else None,
            "stop_loss": 101.0 if index == 0 else None,
            "take_profit_1": 99.0 if index == 0 else None,
            "take_profit": 98.0 if index == 0 else None,
            "rr": 2.0 if index == 0 else None,
            "hypothesis": "test hypothesis" if index == 0 else None,
            "falsification": "test falsification" if index == 0 else None,
            "data_sources": ["OKX_PUBLIC_SWAP_CANDLE"],
            "last_closed_candle_utc": (now - timedelta(minutes=15)).isoformat(),
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
            self.assertEqual(dashboard["signals"][0]["take_profit_1"], 99.0)
            self.assertEqual(dashboard["signals"][0]["lfs_threshold"], 0.30)
            self.assertEqual(dashboard["signals"][0]["lfs_threshold_reason"], "ALL_FIVE_COMPONENTS_REAL")
            self.assertEqual(dashboard["signals"][0]["lfs_threshold_method"], "FIXED_BASELINE_0.30_NOT_ROLLING_90D")
            self.assertEqual(dashboard["signals"][1]["decision"], "NO_QUALIFIED_SETUP")
            self.assertEqual(dashboard["data_gate_status"], "NOT_REPORTED")
            self.assertEqual(dashboard["calibration_status"], "UNCALIBRATED")
            with (root / "lrt15m_history.csv").open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), HISTORY_FIELDS)
                rows = list(reader)
            self.assertEqual(len(rows), 27)

    def test_degraded_symbol_coverage_marks_entire_report_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][1]["decision"] = "MARKET_DATA_DEGRADED"
            report["symbols"][1]["veto"] = "DATA_UNAVAILABLE"
            report["symbols"][1]["reason"] = "UNAVAILABLE:provider_timeout"
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["report_status"], "MARKET_DATA_DEGRADED")
            self.assertEqual(dashboard["data_gate_status"], "DEGRADED")
            self.assertEqual(dashboard["market_data_degraded_count"], 1)
            self.assertEqual(dashboard["signals"][1]["decision"], "MARKET_DATA_DEGRADED")

    def test_proxy_lfs_component_is_downgraded_without_changing_engine_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["lfs_components"]["LFS3"]["status"] = "PROXY"
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            row = dashboard["signals"][0]
            self.assertEqual(dashboard["candidate_setups"], 0)
            self.assertEqual(row["decision"], "NO_QUALIFIED_SETUP")
            self.assertEqual(row["lfs_status"], "PARTIAL_PROXY")
            self.assertEqual(row["lfs_threshold"], 0.30)
            self.assertEqual(row["reason"], "PROXY_COMPONENTS_NOT_PRODUCTION_QUALIFIED")
            self.assertEqual(
                row["lfs_threshold_reason"],
                "PROXY_OR_INCOMPLETE_COMPONENTS_NOT_PRODUCTION_QUALIFIED",
            )

    def test_research_candidate_has_explicit_non_production_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["production_watchlist_count"] = 0
            report["research_candidate_count"] = 1
            report["symbols"][0]["mode"] = "RESEARCH"
            report["symbols"][0]["decision"] = "RESEARCH_WATCHLIST"
            report["symbols"][0]["reason"] = None
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["signals"][0]["decision"], "NO_QUALIFIED_SETUP")
            self.assertEqual(
                dashboard["signals"][0]["reason"],
                "RESEARCH_ONLY_NOT_PRODUCTION_QUALIFIED",
            )

    def test_missing_source_reason_uses_explicit_veto(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["production_watchlist_count"] = 0
            report["symbols"][0]["mode"] = "NONE"
            report["symbols"][0]["decision"] = "NO_TRADE"
            report["symbols"][0]["veto"] = "LFS_BELOW_THRESHOLD"
            report["symbols"][0]["lfs_veto"] = "LFS_BELOW_THRESHOLD"
            report["symbols"][0]["reason"] = None
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(dashboard["signals"][0]["reason"], "LFS_BELOW_THRESHOLD")

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

    def test_rejects_watchlist_candle_not_closed_at_report_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime.now(timezone.utc)
            report, symbols = make_report(now)
            report["symbols"][0]["last_closed_candle_utc"] = (now - timedelta(minutes=10)).isoformat()
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "WATCHLIST_CANDLE_NOT_CLOSED_AT_REPORT_TIME"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_stale_watchlist_candle_even_when_report_is_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime.now(timezone.utc)
            report, symbols = make_report(now)
            report["symbols"][0]["last_closed_candle_utc"] = (now - timedelta(minutes=46)).isoformat()
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "WATCHLIST_CANDLE_STALE"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_stale_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report(datetime.now(timezone.utc) - timedelta(hours=4, minutes=1))
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

    def test_rejects_watchlist_with_inverted_stop_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["stop_loss"] = 99.0
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_LEVEL_DIRECTION_INVALID"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_watchlist_with_risk_reward_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["rr"] = 3.0
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_RR_MISMATCH"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_watchlist_with_misordered_tp1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["take_profit_1"] = 97.0
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_LEVEL_DIRECTION_INVALID"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_watchlist_with_placeholder_hypothesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["hypothesis"] = "UNAVAILABLE"
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_HYPOTHESIS_MISSING"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_unverified_lfs_threshold_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["lfs_threshold_method"] = "ROLLING_90D_80TH_PERCENTILE"
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_LFS_THRESHOLD_METHOD_UNVERIFIED"):
                publish_dashboard(report_path, universe_path, root)

    def test_cvd_proxy_does_not_silently_change_the_current_fixed_lfs_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["cvd"] = {"source": "PROXY_OHLCV"}
            report["symbols"][0]["lfs_threshold"] = 0.30
            report_path, universe_path = write_inputs(root, report, symbols)
            result = publish_dashboard(report_path, universe_path, root)
            dashboard = json.loads((root / "lrt15m_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(result["candidate_setups"], 1)
            self.assertEqual(dashboard["signals"][0]["lfs_threshold"], 0.30)
            self.assertEqual(dashboard["signals"][0]["lfs_threshold_method"], "FIXED_BASELINE_0.30_NOT_ROLLING_90D")

    def test_rejects_watchlist_below_effective_lfs_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["lfs_score"] = 0.25
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_LFS_GATE_MISMATCH"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_out_of_range_lfs_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report["symbols"][0]["lfs_score"] = 1.2
            report_path, universe_path = write_inputs(root, report, symbols)
            with self.assertRaisesRegex(ValueError, "REPORT_WATCHLIST_LFS_SCORE_OUT_OF_RANGE"):
                publish_dashboard(report_path, universe_path, root)


    def test_rejects_different_snapshot_with_same_generation_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            report["symbols"][1]["reason"] = "CHANGED_WITHOUT_NEW_TIMESTAMP"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SAME_TIMESTAMP_REPORT_CONFLICT"):
                publish_dashboard(report_path, universe_path, root)

    def test_rejects_conflicting_history_row_for_same_signal_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, symbols = make_report()
            report_path, universe_path = write_inputs(root, report, symbols)
            publish_dashboard(report_path, universe_path, root)
            history_path = root / "lrt15m_history.csv"
            with history_path.open("r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            rows[0]["reason"] = "CORRUPTED_OR_CONFLICTING_HISTORY"
            with history_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=HISTORY_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "HISTORY_KEY_CONFLICT"):
                publish_dashboard(report_path, universe_path, root)

if __name__ == "__main__":
    unittest.main(verbosity=2)
