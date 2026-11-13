"""آزمون‌های جداسازی امن Stage 1 Production و Research."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.lrt15m_engine import (
    PRODUCTION_MODE_THRESHOLD,
    RESEARCH_MODE_THRESHOLD,
    score_stage1_confluence,
)
from telegram_bot import build_research_message


class Stage1ResearchModeTests(unittest.TestCase):
    def test_production_mode_requires_tier_80(self):
        result = score_stage1_confluence(
            {"bias_4h": True, "bias_1h": True, "sweep": False,
             "zone_reaction": False, "cross": True},
            "PROXY_OHLCV", False,
        )
        self.assertEqual(result["tier_score"], 60)
        self.assertEqual(result["decision"], "RESEARCH_WATCHLIST")
        self.assertEqual(result["mode"], "RESEARCH")
        self.assertEqual(result["research_decision"], "RESEARCH_WATCHLIST")
        self.assertIsNone(result["tier"])

    def test_tier_80_remains_production_not_research(self):
        result = score_stage1_confluence(
            {"bias_4h": True, "bias_1h": True, "sweep": True,
             "zone_reaction": False, "cross": True},
            "PROXY_OHLCV", False,
        )
        self.assertEqual(result["tier_score"], 80)
        self.assertEqual(result["decision"], "WATCHLIST")
        self.assertEqual(result["mode"], "PRODUCTION")
        self.assertIsNone(result["research_decision"])
        self.assertEqual(result["tier"], "B")

    def test_below_60_has_no_research_signal(self):
        result = score_stage1_confluence(
            {"bias_4h": True, "bias_1h": False, "sweep": False,
             "zone_reaction": False, "cross": True},
            "PROXY_OHLCV", False,
        )
        self.assertEqual(result["tier_score"], 40)
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["mode"], "NONE")
        self.assertIsNone(result["research_decision"])

    def test_proxy_zone_adds_12_and_can_only_reach_research_tier(self):
        result = score_stage1_confluence(
            {"bias_4h": True, "bias_1h": True, "sweep": False,
             "zone_reaction": True, "cross": True},
            "PROXY_OHLCV", False,
        )
        self.assertEqual(result["points"]["zone_reaction"], 12)
        self.assertEqual(result["raw_score"], 72)
        self.assertEqual(result["tier_score"], 60)
        self.assertEqual(result["decision"], "RESEARCH_WATCHLIST")
        self.assertEqual(result["mode"], "RESEARCH")

    def test_real_cvd_aligned_zone_keeps_20_points_and_production_tier(self):
        result = score_stage1_confluence(
            {"bias_4h": True, "bias_1h": True, "sweep": False,
             "zone_reaction": True, "cross": True},
            "AGGTRADES_REAL", True,
        )
        self.assertEqual(result["points"]["zone_reaction"], 20)
        self.assertEqual(result["raw_score"], 80)
        self.assertEqual(result["tier_score"], 80)
        self.assertEqual(result["decision"], "WATCHLIST")
        self.assertEqual(result["mode"], "PRODUCTION")

    def test_threshold_constants_are_separate_and_fixed(self):
        self.assertEqual(PRODUCTION_MODE_THRESHOLD, 80)
        self.assertEqual(RESEARCH_MODE_THRESHOLD, 60)

    def test_research_message_has_unmissable_disclaimer(self):
        message = build_research_message({
            "mode": "RESEARCH",
            "decision": "RESEARCH_WATCHLIST",
            "symbol": "BTCUSDT",
            "direction": "SELL",
            "raw_score": 60,
            "tier_score": 60,
            "points": {
                "bias_4h": 20, "bias_1h": 20, "sweep": 0,
                "zone_reaction": 0, "tenkan_kijun_cross_10": 20,
            },
            "signal_id": "test-123",
            "created_at_utc": "2026-11-13T00:00:00+00:00",
        })
        self.assertIn("NOT A TRADING SIGNAL", message)
        self.assertIn("#RESEARCH_DATA_COLLECTION", message)
        self.assertIn("این سیگنال برای جمع‌آوری داده است، نه معامله", message)
        self.assertIn("BTCUSDT", message)

    def test_research_message_rejects_production_payload(self):
        with self.assertRaises(ValueError):
            build_research_message({"mode": "PRODUCTION", "decision": "WATCHLIST"})


if __name__ == "__main__":
    unittest.main()
