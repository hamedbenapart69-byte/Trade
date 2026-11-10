import unittest
from unittest.mock import patch

from research import mvp_validation


class ChronologicalOOSTimelineTests(unittest.TestCase):
    def test_symbol_uses_one_continuous_oos_simulation(self):
        rows = [{} for _ in range(mvp_validation.TRAIN_HOURS + 100)]
        expected = [{"entry_time": 123, "exit_time": 456}]
        with patch.object(
            mvp_validation, "backtest_window", return_value=expected
        ) as backtest:
            result = mvp_validation.walk_forward_symbol("BTC", rows)

        self.assertEqual(result, expected)
        backtest.assert_called_once_with(
            "BTC", rows, start_index=mvp_validation.TRAIN_HOURS
        )

    def test_insufficient_history_does_not_run_oos_backtest(self):
        rows = [{} for _ in range(mvp_validation.TRAIN_HOURS + 1)]
        with patch.object(mvp_validation, "backtest_window") as backtest:
            result = mvp_validation.walk_forward_symbol("BTC", rows)

        self.assertEqual(result, [])
        backtest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
