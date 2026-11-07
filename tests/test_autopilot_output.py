import unittest

from app.signals import render_output


class AutopilotOutputTests(unittest.TestCase):
    def test_exact_signal_table_is_rendered_without_conditional_watchlist(self):
        result = {
            "status": "SCAN_COMPLETED",
            "actionable": [{
                "symbol": "HANAUSDT", "direction": "SHORT", "entry": 0.01374,
                "stop_loss": 0.014, "take_profit": 0.01322,
                "take_profit_2": 0.01296, "take_profit_3": None,
                "primary_timeframe": "1h", "data_grade": "B",
                "risk": {
                    "required_leverage": 1.0, "notional_usd": 153.85, "planned_loss_usd": 4.0,
                    "contract_spec": {
                        "venue_symbol": "HANA-SWAP-USDT",
                        "source": "Toobit public exchangeInfo",
                    },
                },
            }],
            "conditional": [{"symbol": "BTCUSDT", "decision": "CONDITIONAL_BUY"}],
        }
        rendered = render_output(result)
        self.assertIn("| Rank | Symbol | Side | Entry | Stop Loss | TP1 | TP2 | TP3 |", rendered)
        self.assertIn("HANA-SWAP-USDT", rendered)
        self.assertIn("[Toobit API](https://api-docs.toobit.com/api/usdt-m-market-data)", rendered)
        self.assertIn("| — |", rendered)
        self.assertNotIn("CONDITIONAL_BUY", rendered)
        self.assertNotIn("Conditional watchlist", rendered)

    def test_no_actionable_setup_returns_exact_no_signal_text(self):
        self.assertEqual(render_output({"status": "SCAN_COMPLETED", "actionable": [], "conditional": []}),
                         "No qualifying signals today.")
        self.assertEqual(render_output({"status": "DATA_UNAVAILABLE", "actionable": []}),
                         "No qualifying signals today.")


if __name__ == "__main__":
    unittest.main()
