import unittest

from app.signals import render_output


class AutopilotOutputTests(unittest.TestCase):
    def test_v6_actionable_and_conditional_tables_include_strategy_family(self):
        result = {
            "status": "SCAN_COMPLETED",
            "actionable": [{
                "symbol": "BTCUSDT", "strategy_family":"V3_STRICT_BASELINE", "decision": "BUY_NOW", "direction": "LONG",
                "entry": 100.0, "stop_loss": 98.5, "take_profit": 103.0,
                "stop_pct": 1.5, "confidence_v5": 75, "data_grade": "B",
                "risk": {"required_leverage": 2.0, "planned_loss_usd": 4.0},
            }],
            "conditional": [{
                "symbol": "ETHUSDT", "strategy_family":"TREND_PULLBACK", "decision": "CONDITIONAL_SELL", "direction": "SHORT",
                "confidence_v6": 65, "confidence_v5": 65, "data_grade": "B", "entry":2500.0,"stop_loss":2600.0,"take_profit":2300.0,
                "risk":{"required_leverage":3.0,"planned_loss_usd":4.0},
                "entry_quality": {"confirmation_required": "15m close below trigger", "trigger_level": 2500.0},
            }],
        }
        rendered = render_output(result)
        self.assertIn("| Symbol | Strategy | Decision | Direction | Entry | Stop-Loss | Take-Profit | Stop % | Leverage | Risk $ | Data Grade | V6 Score |", rendered)
        self.assertIn("| BTCUSDT | V3_STRICT_BASELINE | BUY_NOW | LONG | 100 | 98.5 | 103 | 1.5 | 2x | 4 | B | 75 |", rendered)
        self.assertIn("Conditional watchlist", rendered)
        self.assertIn("| ETHUSDT | TREND_PULLBACK | CONDITIONAL_SELL | SHORT | 2500 | 2600 | 2300 | 15m close below trigger | 2500 | 3x | 4 | 65 | B |", rendered)

    def test_no_actionable_setup_returns_exact_no_signal_text(self):
        self.assertEqual(render_output({"status": "SCAN_COMPLETED", "actionable": [], "conditional": []}),
                         "No actionable or conditional setups today.")
        self.assertEqual(render_output({"status": "DATA_UNAVAILABLE", "actionable": []}),
                         "DATA UNAVAILABLE — do not trade today.")

    def test_conditional_only_and_partial_scan_messages_follow_v5_contract(self):
        conditional={"status":"SCAN_COMPLETED","actionable":[],"conditional":[{
            "symbol":"ETHUSDT","decision":"CONDITIONAL_BUY","direction":"LONG","confidence_v5":65,
            "data_grade":"B","entry_quality":{"confirmation_required":"15m close above trigger","trigger_level":2500}
        }]}
        rendered=render_output(conditional)
        self.assertTrue(rendered.startswith("No immediate entries. 1 conditional setup is waiting for its defined trigger."))
        self.assertIn("Conditional watchlist",rendered)
        partial={"status":"SCAN_COMPLETED","actionable":[],"conditional":[],"partial_scan":True,"screened_assets":12}
        self.assertEqual(render_output(partial),"No actionable or conditional setups today.\nPartial scan: 12/30.")
        unavailable={"status":"DATA_UNAVAILABLE","actionable":[],"partial_scan":True,"screened_assets":0}
        self.assertEqual(render_output(unavailable),"DATA UNAVAILABLE — do not trade today.\nPartial scan: 0/30.")


if __name__ == "__main__":
    unittest.main()
