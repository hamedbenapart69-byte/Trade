"""Regression tests for explicit, conservative outcome cost accounting."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.outcome_cost_model import (
    FEE_MODEL,
    annotate_outcome_costs,
    annotate_payload,
)


def closed_outcome(**overrides):
    row = {
        "signal_id": "s-1",
        "status": "TP_HIT",
        "entry_fill_status": "SIMULATED_FILLED",
        "entry_actual": 100.0,
        "exit_price": 102.0,
        "pnl_pct_raw": 2.0,
        "fee_pct": "UNAVAILABLE",
        "slippage_pct": "UNAVAILABLE",
        "net_pnl_pct": "UNAVAILABLE",
    }
    row.update(overrides)
    return row


class OutcomeCostModelTests(unittest.TestCase):
    def test_ambiguous_both_touched_is_terminal_not_pending(self):
        row = annotate_outcome_costs(closed_outcome(
            status="AMBIGUOUS_BOTH_TOUCHED",
            exit_price=None,
            pnl_pct_raw=None,
        ))
        costs = row["cost_accounting"]
        self.assertEqual(costs["status"], "TERMINAL_AMBIGUOUS_EXIT")
        self.assertEqual(costs["gross_return_pct"], "UNAVAILABLE")
        self.assertEqual(costs["fee"]["status"], "UNAVAILABLE")
        self.assertEqual(costs["net_return_pct"], "UNAVAILABLE")
        self.assertEqual(row["net_pnl_pct"], "UNAVAILABLE")

    def test_closed_trade_exposes_fee_basis_scenarios_but_never_full_net_label(self):
        row = annotate_outcome_costs(closed_outcome())
        costs = row["cost_accounting"]
        self.assertEqual(costs["status"], "PROXY_BASIS_UNRESOLVED")
        self.assertEqual(costs["fee"]["status"], "PROXY_SCENARIOS_ONLY")
        self.assertEqual(costs["fee"]["model"], FEE_MODEL)
        self.assertEqual(costs["fee"]["basis"], "UNRESOLVED_PER_FILL_VS_ROUND_TRIP")
        self.assertAlmostEqual(costs["fee"]["round_trip_total_interpretation"]["fee_pct"], 0.04)
        self.assertAlmostEqual(costs["fee"]["round_trip_total_interpretation"]["after_fee_only_pct"], 1.96)
        self.assertAlmostEqual(costs["fee"]["per_fill_interpretation"]["fee_pct"], 0.08)
        self.assertAlmostEqual(costs["fee"]["per_fill_interpretation"]["after_fee_only_pct"], 1.92)
        self.assertEqual(costs["net_return_pct"], "UNAVAILABLE")
        self.assertEqual(row["net_pnl_pct"], "UNAVAILABLE")
        self.assertEqual(row["fee_pct"], "UNAVAILABLE")
        self.assertEqual(row["slippage_pct"], "UNAVAILABLE")

    def test_short_loss_preserves_negative_gross_and_fee_only_return(self):
        row = annotate_outcome_costs(closed_outcome(
            status="SL_HIT", exit_price=102.0, pnl_pct_raw=-2.0
        ))
        self.assertAlmostEqual(row["cost_accounting"]["fee"]["round_trip_total_interpretation"]["after_fee_only_pct"], -2.04)
        self.assertAlmostEqual(row["cost_accounting"]["fee"]["per_fill_interpretation"]["after_fee_only_pct"], -2.08)

    def test_non_filled_gap_is_not_counted_as_a_trade(self):
        row = annotate_outcome_costs(closed_outcome(
            status="ENTRY_INVALIDATED_GAP",
            entry_fill_status="NOT_FILLED",
            pnl_pct_raw=None,
            exit_price=None,
        ))
        self.assertEqual(row["cost_accounting"]["status"], "NOT_TRADED")
        self.assertEqual(row["cost_accounting"]["fee"]["status"], "NOT_APPLICABLE")

    def test_active_trade_remains_pending_cost_resolution(self):
        row = annotate_outcome_costs(closed_outcome(status="ACTIVE", pnl_pct_raw=None))
        self.assertEqual(row["cost_accounting"]["status"], "PENDING")
        self.assertEqual(row["cost_accounting"]["net_return_pct"], "UNAVAILABLE")

    def test_invalid_nan_is_not_written_as_a_number(self):
        row = annotate_outcome_costs(closed_outcome(pnl_pct_raw=float("nan")))
        self.assertEqual(row["cost_accounting"]["status"], "INVALID_INPUT")
        self.assertEqual(row["cost_accounting"]["net_return_pct"], "UNAVAILABLE")

    def test_repeated_application_is_idempotent(self):
        first = annotate_outcome_costs(closed_outcome())
        second = annotate_outcome_costs(first)
        self.assertEqual(first["cost_accounting"], second["cost_accounting"])

    def test_payload_rejects_non_object_rows(self):
        with self.assertRaisesRegex(ValueError, "INVALID_OUTCOME_ROW"):
            annotate_payload({"outcomes": [None]})

    def test_payload_marks_schema_version(self):
        payload = annotate_payload({"outcomes": [closed_outcome()]})
        self.assertEqual(payload["cost_accounting_schema_version"], 1)
        self.assertEqual(payload["cost_accounting_model"], FEE_MODEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
