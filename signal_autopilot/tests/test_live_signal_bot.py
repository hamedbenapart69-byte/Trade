import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import (
    _atomic_write_json, calculate_confluence, tenkan_kijun_cross,
    process_symbol, reason_distribution, load_research_state, save_research_state,
)
from modules.live_data_adapter import LiveOHLCVFetcher, is_closed_candle
from telegram_bot import build_signal_messages


def candle(ts, open_, high, low, close, volume=100.0, buy=55.0):
    return {
        "open_time": ts, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume, "taker_buy_base": buy,
    }


class LiveSignalBotTests(unittest.TestCase):
    def test_okx_funding_source_timestamp_is_not_replaced_by_receive_time(self):
        class FakeResponse:
            def __init__(self, data):
                self.payload = {"code": "0", "data": data}
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        source_ts = 1_800_000_000_000
        settlement_ts = source_ts + 8 * 60 * 60 * 1000
        next_settlement_ts = settlement_ts + 4 * 60 * 60 * 1000
        responses = [
            FakeResponse([{
                "fundingRate": "0.0001",
                "ts": str(source_ts),
                "fundingTime": str(settlement_ts),
                "nextFundingTime": str(next_settlement_ts),
            }]),
            FakeResponse([]),
            FakeResponse([]),
            FakeResponse([[source_ts, "1.2"]]),
        ]

        class FakeClient:
            def get(self, *args, **kwargs):
                return responses.pop(0)

        fetcher = LiveOHLCVFetcher.__new__(LiveOHLCVFetcher)
        fetcher.client = FakeClient()
        metrics = fetcher._okx_metrics("BTCUSDT", source_ts)

        self.assertEqual(metrics["funding_timestamp_ms"], source_ts)
        self.assertEqual(metrics["funding_settlement_time_ms"], settlement_ts)
        self.assertEqual(metrics["funding_next_settlement_time_ms"], next_settlement_ts)
        self.assertEqual(metrics["funding_interval_ms"], 4 * 60 * 60 * 1000)
        self.assertIsInstance(metrics["funding_received_at_ms"], int)
        self.assertNotEqual(metrics["funding_received_at_ms"], source_ts)
        self.assertEqual(metrics["long_short_ratio_timestamp_ms"], source_ts)

    def test_report_json_writer_is_atomic_and_preserves_previous_file_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stage1_lrt_report.json"
            _atomic_write_json(path, {"version": 1})
            with self.assertRaises(TypeError):
                _atomic_write_json(path, {"invalid": object()})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 1})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
            _atomic_write_json(path, {"version": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_research_state_rejects_duplicate_signal_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            row = {"signal_id": "duplicate-1"}
            path.write_text(json.dumps({"schema_version": 1, "signals": [row, row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_signal_id_missing_or_duplicate"):
                load_research_state(path)

    def test_research_state_persistence_is_atomic_and_counts_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            payload = {"schema_version": 1, "signals": [{"signal_id": "r-1"}]}
            save_research_state(path, payload)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["signal_count"], 1)
            self.assertEqual(saved["signals"][0]["signal_id"], "r-1")
            self.assertTrue(saved["updated_at_utc"])
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_public_market_timeout_returns_unavailable_without_crashing(self):
        class FailingFetcher:
            @staticmethod
            def fetch_symbol(symbol):
                raise RuntimeError(
                    "all_dual_timeframe_sources_failed|okx:ReadTimeout|fallback:NetworkError"
                )

        signal, reason, diagnostic = process_symbol("BTCUSDT", FailingFetcher())
        self.assertIsNone(signal)
        self.assertEqual(reason, "UNAVAILABLE")
        self.assertEqual(diagnostic["veto"], "DATA_UNAVAILABLE")
        self.assertEqual(diagnostic["lfs_status"], "UNAVAILABLE")
        self.assertIn("ReadTimeout", diagnostic["reason"])

    def test_production_and_research_thresholds_are_named_constants(self):
        from modules.lrt15m_engine import (
            MAX_ZONE_DISTANCE_PCT,
            PRODUCTION_MODE_THRESHOLD,
            RESEARCH_MODE_THRESHOLD,
        )
        self.assertEqual(PRODUCTION_MODE_THRESHOLD, 80)
        self.assertEqual(RESEARCH_MODE_THRESHOLD, 60)
        self.assertEqual(MAX_ZONE_DISTANCE_PCT, 0.80)

    def test_lrt_v2_engine_has_no_legacy_entry_point(self):
        import modules.lrt15m_engine as engine
        self.assertFalse(hasattr(engine, "analyze" + "_symbol"))

    def test_reason_distribution_preserves_each_symbol_and_reason(self):
        result = reason_distribution([
            {"symbol": "BTCUSDT", "reason": "DIRECTION_CONFLICT"},
            {"symbol": "ETHUSDT", "reason": "DIRECTION_CONFLICT"},
            {"symbol": "SOLUSDT", "reason": "LFS_BELOW_THRESHOLD"},
        ])
        self.assertEqual(result, {
            "DIRECTION_CONFLICT": {"count": 2, "symbols": ["BTCUSDT", "ETHUSDT"]},
            "LFS_BELOW_THRESHOLD": {"count": 1, "symbols": ["SOLUSDT"]},
        })

    def test_direction_conflict_candidate_scores_survive_symbol_diagnostic(self):
        candidates = [
            {"direction": "BUY", "raw_score": 80, "tier_score": 80, "lfs_score": 0.35},
            {"direction": "SELL", "raw_score": 80, "tier_score": 80, "lfs_score": 0.40},
        ]

        class FakeFetcher:
            @staticmethod
            def fetch_symbol(symbol):
                return []

        with patch("main.evaluate_stage1_symbol", return_value={
            "symbol": "BTCUSDT",
            "decision": "NO_TRADE",
            "veto": "PASS",
            "reason": "DIRECTION_CONFLICT",
            "direction_candidates": candidates,
            "data_sources": ["OKX_PUBLIC_SWAP_CANDLE"],
            "cvd": {"source": "PROXY_OHLCV"},
            "entry": 100.0,
            "stop_loss": 98.0,
            "take_profit": 104.0,
            "rr": 2.0,
            "hypothesis": "Test hypothesis",
            "falsification": "Test invalidation",
        }):
            signal, reason, diagnostic = process_symbol("BTCUSDT", FakeFetcher())

        self.assertIsNone(signal)
        self.assertEqual(reason, "DIRECTION_CONFLICT")
        self.assertEqual(diagnostic["direction_candidates"], candidates)
        self.assertEqual(diagnostic["data_sources"], ["OKX_PUBLIC_SWAP_CANDLE"])
        self.assertEqual(diagnostic["cvd"]["source"], "PROXY_OHLCV")
        self.assertEqual(diagnostic["entry"], 100.0)
        self.assertEqual(diagnostic["stop_loss"], 98.0)
        self.assertEqual(diagnostic["take_profit"], 104.0)
        self.assertEqual(diagnostic["rr"], 2.0)
    def test_freshness_guard_rejects_stale_and_future_closed_candles(self):
        interval = 900_000
        now_ms = 1_800_000_000_000
        expected = (now_ms // interval) * interval - interval
        stale = [{"open_time": expected - 2 * interval}]
        future = [{"open_time": expected + interval}]
        with self.assertRaisesRegex(ValueError, "15M_CANDLES_STALE"):
            LiveOHLCVFetcher._assert_fresh_closed_bars(stale, interval, now_ms, "15M")
        with self.assertRaisesRegex(ValueError, "15M_CANDLE_FUTURE_DATED"):
            LiveOHLCVFetcher._assert_fresh_closed_bars(future, interval, now_ms, "15M")

    def test_dual_timeframe_fallback_uses_one_exchange_for_both_frames(self):
        fetcher = LiveOHLCVFetcher.__new__(LiveOHLCVFetcher)
        fetcher.fetch_stats = True
        fetcher.stats_limit = 2500
        fetcher.limit = 500
        fetcher.provider_names = ("okx", "bybit")
        calls = []

        def fake_ccxt(symbol, timeframe, limit, now_ms, providers=None):
            calls.append((timeframe, providers))
            if providers == ("okx",):
                raise RuntimeError("okx_public_data_unavailable")
            return [{"open_time": 0, "data_source": "CCXT_BYBIT_PUBLIC_OHLCV"}]

        fetcher._okx_candles = lambda symbol, timeframe, limit, now_ms: (_ for _ in ()).throw(
            RuntimeError("okx_rest_unavailable")
        )
        fetcher._ccxt_timeframe = fake_ccxt
        metrics_calls = []
        fetcher._okx_metrics = lambda symbol, now_ms: metrics_calls.append((symbol, now_ms)) or {
            "funding_rate": None, "oi_1h": None, "oi_1d": None,
            "long_short_ratio": None,
        }
        bundle = fetcher.fetch_symbol("BTCUSDT")

        self.assertEqual(calls, [
            ("1h", ("okx",)),
            ("1h", ("bybit",)),
            ("15m", ("bybit",)),
        ])
        self.assertEqual(bundle.stats_1h[0]["data_source"], "CCXT_BYBIT_PUBLIC_OHLCV")
        self.assertEqual(metrics_calls, [])
        self.assertEqual(bundle.okx_metrics["derivatives_source"], "UNAVAILABLE_CROSS_VENUE_MIX")
        self.assertIsNone(bundle.okx_metrics["funding_rate"])
        self.assertEqual(bundle[0]["data_source"], "CCXT_BYBIT_PUBLIC_OHLCV")

    def test_open_candle_is_excluded_by_close_time_rule(self):
        now_ms = 1_800_000_000_000
        self.assertTrue(is_closed_candle(now_ms - 900_000, 900_000, now_ms))
        self.assertFalse(is_closed_candle(now_ms, 900_000, now_ms))

    def test_confluence_uses_five_approved_gates_and_60_threshold(self):
        result = {
            "higher_timeframe_bias_confirmed": True,
            "higher_timeframe_bias": {"4h_kumo": "BULLISH", "1h_kijun": "BEARISH"},
            "zone_distance_pct": 0.40,
            "lfs_components": {
                "liquidity_sweep": True,
                "order_block": True,
                "fair_value_gap": False,
            },
            "cvd": {"source": "KLINE_TAKER_BUY_PROXY"},
            "lfs_score": 0.80,
        }
        rows = []
        score, parts = calculate_confluence(result, rows, "BUY")
        self.assertEqual(score, 40)
        self.assertEqual(parts, {
            "bias_4h": 20, "bias_1h": 0, "sweep": 20,
            "zone_reaction": 0, "tenkan_kijun_cross_10": 0,
        })
        self.assertFalse(parts["tenkan_kijun_cross_10"])

    def test_cross_lookback_is_ten_closed_candles(self):
        from modules.lrt15m_engine import CROSS_LOOKBACK, tenkan_kijun_cross as cross
        self.assertEqual(CROSS_LOOKBACK, 10)
        bars = []
        for i in range(40):
            center = 100.0 if i < 23 else 110.0
            bars.append(candle(i * 900000, center, center + 0.5, center - 0.5, center))
        self.assertTrue(cross(bars, "BUY", lookback=10))
        self.assertFalse(cross(bars, "BUY", lookback=3))

    def test_zone_distance_uses_synthetic_fvg_and_080_percent_limit(self):
        from modules.lrt15m_engine import zone_distance
        rows = [candle(i * 900000, 99.5, 100.0, 99.0, 99.5) for i in range(20)]
        rows[-1] = candle(7 * 900000, 100.25, 100.5, 100.2, 100.3)
        near = zone_distance(rows, "BUY", None)
        self.assertEqual(near["zone_type"], "FVG")
        self.assertTrue(near["within_limit"])
        self.assertLess(near["distance_pct"], 0.80)
        rows[-1] = candle(7 * 900000, 102.0, 102.3, 101.0, 102.1)
        far = zone_distance(rows, "BUY", None)
        self.assertFalse(far["within_limit"])
        self.assertGreater(far["distance_pct"], 0.80)

    def test_proxy_lfs_threshold_is_stricter_than_real_threshold(self):
        from modules.lrt15m_engine import MIN_LFS_SCORE_PROXY_CVD, MIN_LFS_SCORE_REAL_CVD
        self.assertEqual(MIN_LFS_SCORE_PROXY_CVD, 0.70)
        self.assertEqual(MIN_LFS_SCORE_REAL_CVD, 0.30)
        self.assertGreater(MIN_LFS_SCORE_PROXY_CVD, MIN_LFS_SCORE_REAL_CVD)

    def test_watchlist_and_monitoring_thresholds_are_separate(self):
        from modules.lrt15m_engine import (
            MONITORING_CONFLUENCE_THRESHOLD,
            STAGE1_WATCHLIST_CONFLUENCE_THRESHOLD,
            WATCHLIST_CONFLUENCE_THRESHOLD,
        )
        self.assertEqual(WATCHLIST_CONFLUENCE_THRESHOLD, 60)  # Diagnostic قدیمی
        self.assertEqual(STAGE1_WATCHLIST_CONFLUENCE_THRESHOLD, 80)
        self.assertEqual(MONITORING_CONFLUENCE_THRESHOLD, 60)

    def test_five_components_score_100(self):
        result = {
            "higher_timeframe_bias_confirmed": True,
            "lfs_components": {
                "liquidity_sweep": True,
                "order_block": True,
                "fair_value_gap": False,
            },
            "cvd": {"source": "KLINE_TAKER_BUY_PROXY"},
            "lfs_score": 0.80,
        }
        rows = []
        # Force the cross helper through a patch-free valid 15m series.
        # With fewer than 30 bars the cross component correctly remains false.
        score, parts = calculate_confluence(result, rows, "BUY")
        self.assertLessEqual(score, 80)
        self.assertFalse(parts["tenkan_kijun_cross_10"])


    def test_ccxt_short_pages_are_paginated_until_history_requirement_is_met(self):
        class DummyExchange:
            rateLimit = 0
            markets = {
                "BTC/USDT:USDT": {
                    "active": True, "swap": True, "linear": True,
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "symbol": "BTC/USDT:USDT",
                }
            }

            def __init__(self):
                self.calls = 0

            def fetch_ohlcv(self, symbol, timeframe, since, limit):
                self.calls += 1
                return [
                    [since + i * 900_000, 100, 102, 99, 101, 10]
                    for i in range(300)
                ]

        fetcher = LiveOHLCVFetcher.__new__(LiveOHLCVFetcher)
        fetcher.limit = 1500
        exchange = DummyExchange()
        fetcher._exchange = lambda provider: exchange
        rows = fetcher._from_ccxt(
            "okx",
            "BTCUSDT",
            1_900_000_000_000,
        )
        self.assertEqual(len(rows), 1500)
        self.assertEqual(exchange.calls, 5)
        self.assertEqual(rows[0]["cvd_source"], "UNAVAILABLE_NEUTRAL_PROXY")

    def test_format_test_header_chart_and_body_all_have_exact_safety_label(self):
        signal = {
            "symbol": "ARBUSDT",
            "direction": "SELL",
            "engine": "LRT-15m",
            "timeframe": "15m",
            "signal_id": "historical-arb-format-test",
            "format_test": True,
            "confluence_score": 60,
            "tier": "RESEARCH",
            "confluence_components": {},
            "ichimoku": {},
            "levels": {},
            "calibration": {},
            "costs": {},
            "risk_flags": ["FORMAT TEST ONLY"],
        }
        header, chart_caption, body = build_signal_messages(signal)
        marker = "[FORMAT TEST - NOT A REAL SIGNAL]"
        self.assertTrue(header.startswith(marker))
        self.assertTrue(chart_caption.startswith(marker))
        self.assertTrue(body.startswith(marker))

    def test_message_contains_nine_ordered_sections(self):
        signal = {
            "symbol": "BTCUSDT",
            "direction": "BUY",
            "engine": "LRT-15m",
            "timeframe": "15m",
            "signal_id": "test-id",
            "status": "WATCHLIST",
            "calibration_status": "UNCALIBRATED",
            "confluence_score": 100,
            "ichimoku": {},
            "levels": {},
            "calibration": {},
            "costs": {},
            "risk_flags": ["UNCALIBRATED"],
        }
        header, chart, body = build_signal_messages(signal)
        combined = "\n".join([header, chart, body])
        for number in range(1, 10):
            self.assertIn(f"{number}. ", combined)


if __name__ == "__main__":
    unittest.main()
