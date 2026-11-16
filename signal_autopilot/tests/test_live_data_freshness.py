"""Regression tests for live market-data freshness and venue integrity."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.live_data_adapter import LiveOHLCVFetcher


class FakeResponse:
    def __init__(self, data):
        self.payload = {"code": "0", "data": data}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHTTPClient:
    def close(self):
        return None


class LiveDataFreshnessTests(unittest.TestCase):
    def test_freshness_guard_accepts_latest_closed_bar(self):
        interval = 900_000
        now_ms = 1_800_000_000_000
        expected = (now_ms // interval) * interval - interval
        LiveOHLCVFetcher._assert_fresh_closed_bars(
            [{"open_time": expected}], interval, now_ms, "15M"
        )

    def test_freshness_guard_rejects_stale_and_future_bars(self):
        interval = 900_000
        now_ms = 1_800_000_000_000
        expected = (now_ms // interval) * interval - interval
        with self.assertRaisesRegex(ValueError, "15M_CANDLES_STALE"):
            LiveOHLCVFetcher._assert_fresh_closed_bars(
                [{"open_time": expected - 2 * interval}], interval, now_ms, "15M"
            )
        with self.assertRaisesRegex(ValueError, "15M_CANDLE_FUTURE_DATED"):
            LiveOHLCVFetcher._assert_fresh_closed_bars(
                [{"open_time": expected + interval}], interval, now_ms, "15M"
            )

    def test_public_provider_chain_includes_binance_usdm_fallback(self):
        with patch("modules.live_data_adapter.httpx.Client", return_value=FakeHTTPClient()):
            fetcher = LiveOHLCVFetcher()
        self.assertEqual(
            fetcher.provider_names,
            ("okx", "bybit", "binanceusdm", "kucoinfutures", "mexc", "bitget"),
        )

    def test_dual_timeframe_fallback_uses_one_venue_and_disables_cross_venue_derivatives(self):
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
            return [{
                "open_time": 0,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1.0,
                "data_source": "CCXT_BYBIT_PUBLIC_OHLCV",
            }]

        fetcher._okx_candles = lambda *args: (_ for _ in ()).throw(
            RuntimeError("okx_rest_unavailable")
        )
        fetcher._ccxt_timeframe = fake_ccxt
        metrics_calls = []
        fetcher._okx_metrics = lambda symbol, now_ms: metrics_calls.append((symbol, now_ms) or {}) or {
            "funding_rate": 0.0001
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

    def test_funding_source_and_settlement_timestamps_are_distinct(self):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
