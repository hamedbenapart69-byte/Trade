import unittest
from app.quant.models import score_all


class QuantModelTests(unittest.TestCase):
    def complete_features(self):
        return {
            "return_1h_pct": 1.0, "return_4h_pct": 2.0, "return_1d_pct": 4.0, "rsi_14": 60.0,
            "volume_ratio_20": 1.8, "obv_slope_pct": 4.0, "price_return_7d_pct": 3.0, "range_compression_pct": 20.0,
            "distance_to_resistance_pct": 0.5, "adx_14": 25.0, "close_above_resistance": 1,
            "bollinger_percent_b": -0.1, "zscore_20": -1.5,
            "relative_return_7d_vs_btc_pct": 3.0, "relative_return_30d_vs_btc_pct": 8.0,
            "revenue_growth_yoy_pct": 40.0, "active_users_growth_yoy_pct": 25.0, "developer_growth_yoy_pct": 10.0,
            "token_value_capture_score": 70.0,
            "exchange_netflow_supply_pct": -0.5, "whale_balance_change_30d_pct": 2.0, "active_address_growth_30d_pct": 15.0,
            "verified_catalyst_score": 80.0, "catalyst_days": 20.0, "catalyst_delivery_risk_score": 70.0,
            "liquidity_score": 85.0, "volatility_penalty_score": 20.0, "drawdown_penalty_score": 25.0,
            "unlock_risk_score": 10.0, "contract_risk_score": 5.0,
            "trend_15m_score": 70.0, "trend_1h_score": 75.0, "trend_4h_score": 80.0, "trend_1d_score": 85.0,
        }

    def test_all_ten_models_calculate_with_complete_inputs(self):
        scores = score_all(self.complete_features())
        self.assertEqual(len(scores), 10)
        self.assertTrue(all(s.status == "CALCULATED" for s in scores))
        self.assertTrue(all(0 <= s.score <= 100 for s in scores if s.score is not None))

    def test_missing_input_is_not_fabricated(self):
        scores = score_all({})
        self.assertEqual(len(scores), 10)
        self.assertTrue(all(s.score is None and s.status == "INSUFFICIENT_INPUTS" for s in scores))

    def test_scores_are_deterministic(self):
        features = self.complete_features()
        self.assertEqual(score_all(features), score_all(features))


if __name__ == "__main__":
    unittest.main()
