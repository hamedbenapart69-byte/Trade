import unittest
from app.quant.indicators import MarketDataValidationError
from app.quant.portfolio import correlation_matrix, covariance_matrix, minimum_variance_weights, portfolio_volatility


class PortfolioTests(unittest.TestCase):
    def test_covariance_and_correlation(self):
        returns = {"A": [0.01, -0.01, 0.02, 0.0], "B": [0.02, -0.02, 0.04, 0.0]}
        names, cov = covariance_matrix(returns)
        self.assertEqual(names, ["A", "B"])
        self.assertGreater(cov[0][0], 0)
        names, corr = correlation_matrix(returns)
        self.assertAlmostEqual(corr[0][1], 1.0)

    def test_minimum_variance_weights_are_valid(self):
        returns = {"low_vol": [0.001, -0.001, 0.001, -0.001, 0.001],
                   "high_vol": [0.03, -0.03, 0.02, -0.02, 0.01]}
        weights = minimum_variance_weights(returns, max_weight=0.8)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertTrue(all(0 <= w <= 0.8 for w in weights.values()))
        self.assertGreater(portfolio_volatility(returns, weights), 0)

    def test_misaligned_dates_are_rejected(self):
        with self.assertRaises(MarketDataValidationError):
            minimum_variance_weights({"A": [1, 2, 3], "B": [1, 2, 3, 4]})


if __name__ == "__main__":
    unittest.main()
