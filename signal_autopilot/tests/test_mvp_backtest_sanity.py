"""Sanity checks مستقل برای مدل اجرای بک‌تست MVP."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "research" / "mvp_validation.py"
SPEC = importlib.util.spec_from_file_location("mvp_validation_sanity", MODULE_PATH)
bt = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(bt)

HOUR_MS = 3_600_000


def synthetic_rows() -> list[dict]:
    rows = [
        {
            "timestamp": (index - 3) * HOUR_MS,
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100.0, "volume": 1000.0,
        }
        for index in range(80)
    ]
    return rows


def run_with_signal(rows: list[dict]) -> list[dict]:
    # فقط index 50 سیگنال معتبر دارد؛ بعد از آن EMA lookup تهی می‌شود.
    with patch.object(bt, "ema", side_effect=[[110.0] * 32, [100.0] * 2]), \
         patch.object(bt, "atr_series", return_value=[1.0] * len(rows)):
        return bt.backtest_window("BTCUSDT", rows, start_index=50)


class BacktestExecutionSanityTests(unittest.TestCase):
    def test_signal_at_close_enters_at_next_bar_open_and_records_timestamps(self):
        rows = synthetic_rows()
        rows[51]["open"] = 100.0
        rows[51]["low"] = 98.0
        rows[51]["high"] = 103.0

        trades = run_with_signal(rows)

        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["exit_reason"], "STOP_SAME_BAR_AMBIGUITY")
        self.assertEqual(trade["signal_time"], rows[50]["timestamp"] + HOUR_MS)
        self.assertEqual(trade["order_decision_time"], trade["signal_time"])
        self.assertEqual(trade["entry_time"], rows[51]["timestamp"])
        self.assertEqual(trade["entry_fill_price"], rows[51]["open"])
        self.assertEqual(trade["exit_fill_price"], trade["stop"])
        self.assertEqual(trade["target_triggers"], ["TP1"])

    def test_same_bar_stop_and_target_uses_worst_case_stop(self):
        rows = synthetic_rows()
        rows[51]["high"] = 103.0
        rows[51]["low"] = 98.0

        trade = run_with_signal(rows)[0]

        self.assertEqual(trade["exit_reason"], "STOP_SAME_BAR_AMBIGUITY")
        self.assertAlmostEqual(trade["exit_fill_price"], 98.5)
        self.assertAlmostEqual(trade["gross_return_pct"], -1.5, places=8)
        self.assertAlmostEqual(trade["cost_return_pct"], 0.12, places=8)
        self.assertAlmostEqual(trade["net_return_pct"], -1.62, places=8)
        self.assertAlmostEqual(trade["net_r"], -1.08, places=8)

    def test_tp1_and_tp2_partial_fills_are_weighted_fifty_fifty(self):
        rows = synthetic_rows()
        rows[51]["high"] = 105.0
        rows[51]["low"] = 99.0

        trade = run_with_signal(rows)[0]

        self.assertEqual(trade["exit_reason"], "TP2")
        self.assertEqual(trade["target_triggers"], ["TP1", "TP2"])
        self.assertAlmostEqual(trade["gross_return_pct"], 3.0, places=8)
        self.assertAlmostEqual(trade["net_return_pct"], 2.88, places=8)
        self.assertEqual(trade["partial_fill_assumption"], "50% at TP1 and 50% at TP2")

    def test_last_candle_is_checked_for_stop_before_end_of_window_close(self):
        rows = synthetic_rows()
        rows[-1]["low"] = 98.0
        rows[-1]["high"] = 101.0

        trade = run_with_signal(rows)[0]

        self.assertEqual(trade["exit_reason"], "STOP")
        self.assertAlmostEqual(trade["exit_fill_price"], 98.5)

    def test_unavailable_costs_are_not_silently_treated_as_zero(self):
        rows = synthetic_rows()
        rows[51]["low"] = 98.0
        rows[51]["high"] = 101.0

        trade = run_with_signal(rows)[0]

        self.assertEqual(trade["spread_cost_pct"], "UNAVAILABLE")
        self.assertEqual(trade["market_impact_cost_pct"], "UNAVAILABLE")
        self.assertEqual(trade["funding_cost"], "UNAVAILABLE")
        self.assertEqual(trade["slippage_per_side_pct"], 0.02)
        self.assertEqual(trade["round_trip_fee_pct"], 0.08)

    def test_drawdown_proxy_for_one_full_stop_is_not_one_hundred_percent(self):
        rows = synthetic_rows()
        rows[51]["low"] = 98.0
        rows[51]["high"] = 101.0
        trade = run_with_signal(rows)[0]

        summary = bt.metrics([trade])

        self.assertEqual(summary["trades"], 1)
        self.assertAlmostEqual(summary["max_drawdown_pct"], 1.08, places=6)
        self.assertIn("not a concurrency-aware portfolio drawdown", summary["note"])


if __name__ == "__main__":
    unittest.main()
