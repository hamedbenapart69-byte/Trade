"""آزمون‌های رهگیر پیامد سایه‌ای سیگنال‌های WATCHLIST تولیدی."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.production_outcome_tracker import (
    _collect_signals,
    update_production_outcomes,
)


def signal(signal_id="prod-1", tracker_status="OPEN", direction="BUY"):
    entry, stop, tp1, tp2 = 100.0, 98.0, 102.0, 104.0
    if direction == "SELL":
        entry, stop, tp1, tp2 = 100.0, 102.0, 98.0, 96.0
    return {
        "signal_id": signal_id,
        "symbol": "BTCUSDT",
        "mode": "PRODUCTION",
        "decision": "WATCHLIST",
        "direction": direction,
        "entry": entry,
        "stop_loss": stop,
        "take_profit_1": tp1,
        "take_profit": tp2,
        "rr": 2.0,
        "created_at_utc": "2026-11-14T14:55:00+00:00",
        "last_closed_candle_utc": "2026-11-14T14:30:00+00:00",
        "hypothesis": "Liquidity sweep and reclaim support a mean-reversion move.",
        "falsification": "A 15m close beyond the stop invalidates the setup.",
        "lfs_score": 0.72,
        "lfs_status": "FULL",
        "lfs_coverage_pct": 100.0,
        "cvd": {"source": "PROXY_OHLCV"},
        "tracker_status": tracker_status,
    }


def write_state(path, open_rows=None, closed_rows=None):
    open_rows = open_rows or {}
    closed_rows = closed_rows or {}
    path.write_text(json.dumps({
        "schema_version": 1,
        "open_signals": open_rows,
        "closed_signals": closed_rows,
    }), encoding="utf-8")


class ProductionOutcomeTrackerTests(unittest.TestCase):
    def test_collects_open_and_closed_production_watchlists(self):
        state = {
            "open_signals": {"prod-1": signal("prod-1", "OPEN")},
            "closed_signals": {"prod-2": signal("prod-2", "CLOSED", "SELL")},
        }
        rows = _collect_signals(state)
        self.assertEqual({row["signal_id"] for row in rows}, {"prod-1", "prod-2"})
        self.assertEqual({row["source_tracker_status"] for row in rows}, {"OPEN", "CLOSED"})
        self.assertTrue(all(row["execution_status"] == "NOT_EXECUTED" for row in rows))

    def test_ignores_research_and_non_watchlist_records(self):
        research = signal("research-1")
        research["mode"] = "RESEARCH"
        no_setup = signal("prod-2")
        no_setup["decision"] = "NO_QUALIFIED_SETUP"
        rows = _collect_signals({
            "open_signals": {"research-1": research, "prod-2": no_setup},
            "closed_signals": {},
        })
        self.assertEqual(rows, [])

    def test_rejects_duplicate_ids_across_open_and_closed(self):
        row = signal("duplicate")
        with self.assertRaisesRegex(ValueError, "PRODUCTION_SIGNAL_ID_DUPLICATE"):
            _collect_signals({
                "open_signals": {"duplicate": row},
                "closed_signals": {"duplicate": row},
            })

    def test_rejects_invalid_level_order_and_unaligned_candle(self):
        row = signal()
        row["stop_loss"] = 101.0
        with self.assertRaisesRegex(ValueError, "PRODUCTION_SIGNAL_LEVEL_ORDER_INVALID"):
            _collect_signals({"open_signals": {"prod-1": row}, "closed_signals": {}})
        row = signal()
        row["last_closed_candle_utc"] = "2026-11-14T14:31:00+00:00"
        with self.assertRaisesRegex(ValueError, "LAST_CLOSED_CANDLE_NOT_15M_ALIGNED"):
            _collect_signals({"open_signals": {"prod-1": row}, "closed_signals": {}})

    def test_writes_separate_shadow_outcomes_without_claiming_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "open_signals.json"
            outcomes_path = root / "production_outcomes.json"
            write_state(state_path, {"prod-1": signal()})
            entry_open_ms = int(datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)

            def fake_fetcher(symbol, since_ms, now_ms, limit):
                self.assertEqual(symbol, "BTCUSDT")
                self.assertEqual(since_ms, entry_open_ms)
                self.assertEqual(limit, 200)
                return ([{
                    "open_time": entry_open_ms,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                }], "TEST_PUBLIC_FIXTURE")

            result = update_production_outcomes(
                state_path,
                outcomes_path,
                now=datetime(2026, 11, 14, 15, 15, tzinfo=timezone.utc),
                fetcher=fake_fetcher,
            )
            payload = json.loads(outcomes_path.read_text(encoding="utf-8"))
            outcome = payload["outcomes"][0]
            self.assertEqual(result["source_signals_count"], 1)
            self.assertEqual(result["outcomes_count"], 1)
            self.assertEqual(outcome["status"], "ACTIVE")
            self.assertEqual(outcome["execution_status"], "NOT_EXECUTED")
            self.assertEqual(outcome["evaluation_kind"], "PRODUCTION_WATCHLIST_SHADOW")
            self.assertEqual(outcome["statistics_status"], "NOT_CALCULATED")
            self.assertEqual(outcome["cost_status"], "UNAVAILABLE")
            self.assertEqual(outcome["fee_pct"], "UNAVAILABLE")
            self.assertEqual(outcome["net_pnl_pct"], "UNAVAILABLE")
            self.assertEqual(outcome["data_source"], "TEST_PUBLIC_FIXTURE")
            self.assertEqual(outcome["tp1_reference"], 102.0)

    def test_empty_source_cannot_erase_existing_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "open_signals.json"
            outcomes_path = root / "production_outcomes.json"
            write_state(state_path)
            outcomes_path.write_text(json.dumps({"outcomes": [{"signal_id": "removed"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PRODUCTION_SIGNAL_HISTORY_REGRESSION"):
                update_production_outcomes(
                    state_path,
                    outcomes_path,
                    now=datetime(2026, 11, 14, 15, 15, tzinfo=timezone.utc),
                    fetcher=lambda *args: ([], "UNUSED"),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
