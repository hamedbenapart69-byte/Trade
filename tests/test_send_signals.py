from __future__ import annotations

import math
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import send_signals as bot


def synthetic_market(target: date):
    days = [target - timedelta(days=i) for i in range(69, -1, -1)]
    market = {}
    for index, symbol in enumerate(bot.UNIVERSE):
        rows = []
        for i, day in enumerate(days):
            close = (100.0 + i * 1.0 if symbol == "BTCUSDT" else
                     100.0 + i * (0.03 + index * 0.01) +
                     math.sin(i * (0.3 + index * 0.025)) * (index + 1) * 0.7)
            volume = 1000.0 + (i % 7) * 13.0 + math.sin(i * (0.2 + index * 0.04)) * (index + 1) * 9.0
            rows.append(bot.Candle(day, close * 0.99, close * 1.01, close * 0.98, close, volume))
        market[symbol] = rows
    return market


class SignalBotTests(unittest.TestCase):
    def test_saturday_midnight_uses_friday_close(self):
        now = datetime(2026, 11, 28, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(bot.latest_completed_friday(now), date(2026, 11, 27))

    def test_friday_intraday_uses_previous_completed_friday(self):
        now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(bot.latest_completed_friday(now), date(2026, 11, 20))

    def test_rsi_edge_cases(self):
        self.assertEqual(bot._rsi14([float(i) for i in range(20)]), 100.0)
        self.assertEqual(bot._rsi14([100.0] * 20), 50.0)

    def test_atr14_and_two_percent_risk_sizing(self):
        start = date(2026, 11, 1)
        candles = [
            bot.Candle(start + timedelta(days=i), 100.0, 101.0, 99.0, 100.0, 1000.0)
            for i in range(15)
        ]
        value = bot.atr14(candles)
        self.assertAlmostEqual(value, 2.0)
        plan = bot.atr_risk_plan(100.0, value, equity_quote=1000.0)
        self.assertAlmostEqual(plan["stop_distance"], 4.0)
        self.assertAlmostEqual(plan["max_risk_fraction"], 0.01)
        self.assertAlmostEqual(plan["risk_budget_per_1000_equity"], 10.0)
        self.assertAlmostEqual(plan["notional_per_1000_equity"], 250.0)

    def test_weekly_execution_is_next_monday_open_to_friday_close(self):
        monday, friday = bot.next_week_execution_window(date(2026, 11, 27))
        self.assertEqual(monday, date(2026, 11, 30))
        self.assertEqual(friday, date(2026, 12, 4))

    def test_bull_regime_ranks_eight_alts_and_selects_two(self):
        target = date(2026, 11, 27)
        result = bot.build_signal("OKX", synthetic_market(target), target)
        self.assertEqual(result["state"], "LONG_TOP_2")
        self.assertEqual(len(result["selected"]), 2)
        self.assertEqual(set(result["scores"]), set(bot.ALTCOINS))
        self.assertGreater(result["btc_close"], result["btc_ma50"])
        self.assertEqual(result["weekly_execution"]["entry_rule"], "NEXT_MONDAY_OPEN")
        self.assertEqual(result["weekly_execution"]["exit_rule"], "SAME_WEEK_FRIDAY_CLOSE")
        self.assertEqual(result["weekly_execution"]["entry_date"], "2026-11-30")
        self.assertEqual(result["weekly_execution"]["exit_date"], "2026-12-04")
        self.assertTrue(all(item["max_risk_fraction"] == 0.01 for item in result["selected"]))
        self.assertEqual(result["risk_model"]["max_account_risk_fraction"], 0.02)
        self.assertEqual(result["risk_model"]["max_concurrent_positions"], 2)

    def test_bear_regime_returns_cash(self):
        target = date(2026, 11, 27)
        market = synthetic_market(target)
        market["BTCUSDT"] = [
            bot.Candle(c.day, c.open, c.high, c.low, 200.0 - i, c.base_volume)
            for i, c in enumerate(market["BTCUSDT"])
        ]
        result = bot.build_signal("OKX", market, target)
        self.assertEqual(result["state"], "CASH")
        self.assertEqual(result["selected"], [])

    def test_provider_fallback_restarts_whole_universe(self):
        target = date(2026, 11, 27)
        market = synthetic_market(target)
        calls = []
        def fake_fetch(provider, symbol):
            calls.append((provider, symbol))
            if provider == "OKX" and symbol == "SOLUSDT":
                raise bot.ProviderError("fixture failure")
            return market[symbol]
        with patch.object(bot, "fetch_symbol", side_effect=fake_fetch):
            provider, snapshot, failures = bot.fetch_consistent_universe(target)
        self.assertEqual(provider, "BYBIT")
        self.assertEqual(set(snapshot), set(bot.UNIVERSE))
        self.assertEqual(failures[0]["provider"], "OKX")
        self.assertTrue(all(p == "BYBIT" for p, _ in calls[3:]))


    def test_okx_uses_confirmed_candle_and_base_volume(self):
        payload = {"code": "0", "data": [[
            "1795737600000", "100", "102", "99", "101",
            "50", "5050", "5100", "1"
        ]]}
        with patch.object(bot, "_http_json", return_value=payload):
            rows = bot.fetch_okx("BTCUSDT")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].base_volume, 5050.0)

    def test_bybit_uses_linear_base_volume(self):
        payload = {"retCode": 0, "result": {"list": [[
            "1795737600000", "100", "102", "99", "101", "50", "5100"
        ]]}}
        with patch.object(bot, "_http_json", return_value=payload):
            rows = bot.fetch_bybit("BTCUSDT")
        self.assertEqual(rows[0].base_volume, 50.0)

    def test_binance_uses_usdm_base_volume(self):
        payload = [[
            1795737600000, "100", "102", "99", "101", "50",
            1795823999999, "5100", 100, "20", "2000", "0"
        ]]
        with patch.object(bot, "_http_json", return_value=payload):
            rows = bot.fetch_binance_futures("BTCUSDT")
        self.assertEqual(rows[0].base_volume, 50.0)

    def test_release_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "gate.json"
            self.assertEqual(bot.load_release_gate(path)["status"], "BLOCKED_NO_RELEASE_GATE")
            path.write_text('{"status":"PASS","max_drawdown_below_30_percent":true,"profit_factor_above_1_50":true,"pbo_below_0_40":true}', encoding="utf-8")
            self.assertEqual(bot.load_release_gate(path)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
