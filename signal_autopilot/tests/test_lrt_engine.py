import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.lrt15m_engine import analyze_symbol, evaluate_stage1_decision


def components(count: int) -> dict[str, bool]:
    names = ["bias_4h", "bias_1h", "sweep", "zone_reaction", "cross"]
    return {name: index < count for index, name in enumerate(names)}


class LRTStage1DecisionTests(unittest.TestCase):
    def evaluate(self, count: int, *, inside_kumo: bool = False,
                 lfs_score: float = 0.80, cvd_source: str = "AGGTRADES_REAL"):
        return evaluate_stage1_decision(
            data_valid=True,
            inside_kumo=inside_kumo,
            lfs_score=lfs_score,
            cvd_source=cvd_source,
            components=components(count),
            cvd_aligned=True,
        )

    def test_legacy_analyze_symbol_is_deprecated(self):
        with self.assertWarnsRegex(
            DeprecationWarning,
            "LEGACY - NOT USED IN PRODUCTION, ONLY FOR COMPARISON",
        ):
            result = analyze_symbol("BTCUSDT", [])
        self.assertEqual(result["decision"], "NO_QUALIFIED_SETUP")

    def test_5_of_5_components_produce_100_and_watchlist_tier_a(self):
        result = self.evaluate(5)
        self.assertEqual(result["raw_score"], 100)
        self.assertEqual(result["decision"], "WATCHLIST")
        self.assertEqual(result["tier"], "A")

    def test_4_of_5_components_produce_80_and_watchlist_tier_b(self):
        result = self.evaluate(4)
        self.assertEqual(result["raw_score"], 80)
        self.assertEqual(result["decision"], "WATCHLIST")
        self.assertEqual(result["tier"], "B")

    def test_3_of_5_components_produce_60_and_monitoring(self):
        result = self.evaluate(3)
        self.assertEqual(result["raw_score"], 60)
        self.assertEqual(result["decision"], "MONITORING")

    def test_2_of_5_components_produce_40_and_no_trade(self):
        result = self.evaluate(2)
        self.assertEqual(result["raw_score"], 40)
        self.assertEqual(result["decision"], "NO_TRADE")

    def test_kumo_veto_overrides_five_of_five_confluence(self):
        result = self.evaluate(5, inside_kumo=True)
        self.assertEqual(result["veto"], "INSIDE_KUMO_4H")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertIsNone(result["score"])

    def test_lfs_v2_uses_fixed_threshold_for_proxy_and_real_sources(self):
        proxy = evaluate_stage1_decision(
            True, False, 0.35, "PROXY_OHLCV", components(3), False
        )
        real = evaluate_stage1_decision(
            True, False, 0.65, "AGGTRADES_REAL", components(3), True
        )
        below = evaluate_stage1_decision(
            True, False, 0.25, "AGGTRADES_REAL", components(3), True
        )
        self.assertEqual(proxy["veto"], "PASS")
        self.assertEqual(real["veto"], "PASS")
        self.assertEqual(proxy["lfs_threshold"], 0.30)
        self.assertEqual(real["lfs_threshold"], 0.30)
        self.assertEqual(below["veto"], "LFS_BELOW_THRESHOLD")
        self.assertEqual(below["lfs_threshold"], 0.30)


if __name__ == "__main__":
    unittest.main()
