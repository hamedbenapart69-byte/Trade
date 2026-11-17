from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.export_l1_contract import build_contract


def _fixture(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    acquired = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    acquired_ms = int(acquired.timestamp() * 1000)
    ohlcv = [
        {"timestamp": acquired_ms - 3_600_000, "open": 100.0, "high": 105.0,
         "low": 99.0, "close": 103.0, "volume": 10.0},
        {"timestamp": acquired_ms, "open": 103.0, "high": 106.0,
         "low": 102.0, "close": 104.0, "volume": 11.0},
    ]
    funding = [
        {"timestamp": acquired_ms - 3_600_000, "symbol": "BTC-USDT-SWAP",
         "funding_rate": None, "mark_price": None}
    ]
    oi = [{"timestamp": acquired_ms - 3_600_000, "symbol": "BTC-USDT-SWAP",
           "open_interest": 1200.0, "open_interest_value_usd": None}]
    for name, rows in (("ohlcv", ohlcv), ("funding", funding), ("oi", oi)):
        pq.write_table(pa.Table.from_pylist(rows), data / f"{name}.parquet")
    report = {
        "history_target_years": 2,
        "primary_provider": "okx",
        "provider": "OKX public market-data API",
        "symbols": {
            "BTC-USDT-SWAP": {
                "instrument": {
                    "instrument_id": "BTC-USDT-SWAP", "unified_symbol": "BTC/USDT:USDT",
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "contract_type": "linear_perpetual", "contract_size": 0.01,
                    "provider_id": "okx",
                },
                "files": {"ohlcv": "ohlcv.parquet", "funding": "funding.parquet",
                          "open_interest": "oi.parquet"},
                "ohlcv": {"coverage_of_requested_window_pct": 99.5},
            }
        },
    }
    return report, data, acquired, acquired_ms


def test_missing_funding_and_oi_remain_null(tmp_path):
    report, data, acquired, _ = _fixture(tmp_path)
    result = build_contract(report, data, now=acquired)
    instrument = result["instruments"][0]
    assert instrument["funding"][0]["funding_rate"] is None
    assert instrument["funding"][0]["mark_price"] is None
    assert instrument["open_interest"][0]["open_interest_value_usd"] is None
    assert instrument["availability"]["funding"] == "PARTIAL"


def test_open_candle_is_excluded(tmp_path):
    report, data, acquired, acquired_ms = _fixture(tmp_path)
    result = build_contract(report, data, now=acquired)
    candles = result["instruments"][0]["candles"]
    assert len(candles) == 1
    assert candles[0]["timestamp_ms"] == acquired_ms - 3_600_000
    assert candles[0]["closed"] is True


def test_duplicate_ohlcv_timestamp_fails_closed(tmp_path):
    report, data, acquired, _ = _fixture(tmp_path)
    rows = pq.read_table(data / "ohlcv.parquet").to_pylist()
    rows.append(dict(rows[0]))
    pq.write_table(pa.Table.from_pylist(rows), data / "ohlcv.parquet")
    with pytest.raises(ValueError, match="duplicate_ohlcv_timestamp"):
        build_contract(report, data, now=acquired)


def test_exact_linear_perpetual_identity_is_required(tmp_path):
    report, data, acquired, _ = _fixture(tmp_path)
    report["symbols"]["BTC-USDT-SWAP"]["instrument"]["contract_type"] = "spot"
    with pytest.raises(ValueError, match="unsupported_contract_type"):
        build_contract(report, data, now=acquired)
