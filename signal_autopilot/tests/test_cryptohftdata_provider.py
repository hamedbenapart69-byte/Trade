"""آزمون‌های آداپتر داخلی CryptoHFTData؛ بدون اتصال شبکه در تست واحد."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
import unittest
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_MODULE_PATH = Path(__file__).resolve().parents[1] / "modules" / "cryptohftdata_provider.py"
_SPEC = importlib.util.spec_from_file_location("cryptohftdata_provider", _MODULE_PATH)
_PROVIDER_MODULE = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = _PROVIDER_MODULE
_SPEC.loader.exec_module(_PROVIDER_MODULE)

CryptoHFTDataProvider = _PROVIDER_MODULE.CryptoHFTDataProvider
CryptoHFTDataError = _PROVIDER_MODULE.CryptoHFTDataError
ProviderDataUnavailable = _PROVIDER_MODULE.ProviderDataUnavailable
build_file_path = _PROVIDER_MODULE.build_file_path
latest_complete_hour = _PROVIDER_MODULE.latest_complete_hour


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int = -1) -> bytes:
        return self.body


def parquet_bytes(table: pa.Table) -> bytes:
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


def mark_price_table(symbol: str = "BTCUSDT") -> pa.Table:
    return pa.table({
        "received_time": [1_794_787_200_000_000_000],
        "event_time": [1_794_787_200_000],
        "symbol": [symbol],
        "mark_price": ["90000.0"],
        "index_price": ["89999.0"],
        "estimated_settle_price": ["90001.0"],
        "funding_rate": ["0.0001"],
        "next_funding_time": [1_794_816_000_000],
    })


def open_interest_table(symbol: str = "BTCUSDT") -> pa.Table:
    return pa.table({
        "received_time": [1_794_787_200_000_000_000],
        "symbol": [symbol],
        "sum_open_interest": ["1000.0"],
        "sum_open_interest_value": ["90000000.0"],
        "timestamp": [1_794_787_200_000],
    })


class ProviderPathAndTimeTests(unittest.TestCase):
    def test_latest_complete_hour_respects_publication_delay(self):
        now = datetime(2026, 11, 16, 14, 25, tzinfo=timezone.utc)
        self.assertEqual(
            latest_complete_hour(now),
            datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc),
        )

    def test_latest_complete_hour_does_not_assume_current_hour_is_closed(self):
        now = datetime(2026, 11, 16, 14, 14, tzinfo=timezone.utc)
        self.assertEqual(
            latest_complete_hour(now),
            datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc),
        )

    def test_file_path_is_utc_hourly_and_exact(self):
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        self.assertEqual(
            build_file_path("binance_futures", "BTCUSDT", "mark_price", hour),
            "binance_futures/2026-11-16/13/BTCUSDT_mark_price.parquet",
        )

    def test_rejects_unsupported_exchange_and_invalid_symbol(self):
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            build_file_path("unknown_exchange", "BTCUSDT", "mark_price", hour)
        with self.assertRaises(ValueError):
            build_file_path("binance_futures", "../BTCUSDT", "mark_price", hour)


class ProviderDownloadTests(unittest.TestCase):
    def test_downloads_and_parses_mark_price_in_memory(self):
        body = parquet_bytes(mark_price_table())
        seen = []

        def opener(request, timeout):
            seen.append((request.full_url, timeout))
            return FakeResponse(body)

        provider = CryptoHFTDataProvider(
            min_request_interval_seconds=0,
            opener=opener,
        )
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        snapshot = provider.download_hourly_parquet(
            "binance_futures", "BTCUSDT", "mark_price", hour
        )
        self.assertEqual(snapshot.row_count, 1)
        self.assertIn("funding_rate", snapshot.columns)
        self.assertEqual(snapshot.provider, "CRYPTOHFTDATA")
        self.assertEqual(len(seen), 1)
        self.assertIn("BTCUSDT_mark_price.parquet", seen[0][0])
        self.assertNotIn("api_key=", seen[0][0])

    def test_downloads_and_parses_open_interest_in_memory(self):
        body = parquet_bytes(open_interest_table())
        provider = CryptoHFTDataProvider(
            min_request_interval_seconds=0,
            opener=lambda _request, timeout=None: FakeResponse(body),
        )
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        snapshot = provider.download_hourly_parquet(
            "binance_futures", "BTCUSDT", "open_interest", hour
        )
        self.assertEqual(snapshot.row_count, 1)
        self.assertIn("sum_open_interest_value", snapshot.columns)

    def test_rejects_symbol_mismatch(self):
        body = parquet_bytes(mark_price_table("ETHUSDT"))
        provider = CryptoHFTDataProvider(
            min_request_interval_seconds=0,
            opener=lambda _request, _timeout: FakeResponse(body),
        )
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(CryptoHFTDataError, "symbol_mismatch"):
            provider.download_hourly_parquet(
                "binance_futures", "BTCUSDT", "mark_price", hour
            )

    def test_rejects_missing_required_schema_columns(self):
        table = pa.table({"symbol": ["BTCUSDT"], "mark_price": ["90000"]})
        provider = CryptoHFTDataProvider(
            min_request_interval_seconds=0,
            opener=lambda _request, _timeout: FakeResponse(parquet_bytes(table)),
        )
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(CryptoHFTDataError, "schema_missing_columns"):
            provider.download_hourly_parquet(
                "binance_futures", "BTCUSDT", "mark_price", hour
            )

    def test_discover_symbols_uses_documented_endpoint(self):
        body = json.dumps({
            "exchange": "binance_futures",
            "data_type": "mark_price",
            "count": 2,
            "symbols": ["BTCUSDT", "ETHUSDT"],
        }).encode()
        seen = []

        def opener(request, timeout):
            seen.append(request.full_url)
            return FakeResponse(body)

        provider = CryptoHFTDataProvider(opener=opener)
        self.assertEqual(
            provider.discover_symbols("binance_futures", "mark_price"),
            ["BTCUSDT", "ETHUSDT"],
        )
        self.assertIn("/symbols?", seen[0])
        self.assertIn("exchange=binance_futures", seen[0])

    def test_http_404_is_unavailable_not_fabricated(self):
        def opener(_request, timeout=None):
            raise urllib.error.HTTPError("https://example.invalid", 404, "missing", {}, None)

        provider = CryptoHFTDataProvider(
            min_request_interval_seconds=0,
            opener=opener,
        )
        hour = datetime(2026, 11, 16, 13, 0, tzinfo=timezone.utc)
        with self.assertRaises(ProviderDataUnavailable):
            provider.download_hourly_parquet(
                "binance_futures", "FILUSDT", "mark_price", hour
            )


if __name__ == "__main__":
    unittest.main()
