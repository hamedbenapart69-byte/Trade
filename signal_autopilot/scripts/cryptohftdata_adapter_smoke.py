"""Smoke test واقعی CryptoHFTData؛ فقط فراداده را نگه می‌دارد، نه دادهٔ خام."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_autopilot.modules.cryptohftdata_provider import (
    CryptoHFTDataProvider,
    latest_complete_hour,
)

TARGET_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "FILUSDT")
DATA_TYPES = ("mark_price", "open_interest")
EXCHANGE_ID = "binance_futures"


def _range(table, column_name: str) -> dict[str, int] | None:
    if column_name not in table.schema.names:
        return None
    values = [
        int(value)
        for value in table.column(column_name).to_pylist()
        if value is not None
    ]
    if not values:
        return None
    return {"min_raw": min(values), "max_raw": max(values)}


def _snapshot_report(snapshot) -> dict[str, Any]:
    table = snapshot.table
    required = {
        "mark_price": (
            "received_time", "symbol", "mark_price", "index_price",
            "funding_rate", "next_funding_time",
        ),
        "open_interest": (
            "received_time", "symbol", "sum_open_interest",
            "sum_open_interest_value", "timestamp",
        ),
    }[snapshot.data_type]
    symbols = sorted({
        str(value).upper()
        for value in table.column("symbol").to_pylist()
        if value is not None
    })
    timestamp_columns = (
        ("event_time", "received_time", "next_funding_time")
        if snapshot.data_type == "mark_price"
        else ("timestamp", "received_time")
    )
    return {
        "provider": snapshot.provider,
        "exchange_id": snapshot.exchange_id,
        "symbol": snapshot.symbol,
        "data_type": snapshot.data_type,
        "hour_start_utc": snapshot.hour_start_utc.isoformat(),
        "retrieved_at_utc": snapshot.retrieved_at_utc.isoformat(),
        "source_path": snapshot.source_path,
        "row_count": snapshot.row_count,
        "columns": snapshot.columns,
        "null_counts": {
            name: table.column(name).null_count for name in required
        },
        "timestamp_ranges_raw": {
            name: _range(table, name) for name in timestamp_columns
        },
        "symbol_values": symbols,
        "symbol_match": symbols == [snapshot.symbol],
        "raw_file_persisted": False,
    }


def run() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    hour_start = latest_complete_hour(started)
    provider = CryptoHFTDataProvider(
        api_key=None,
        timeout_seconds=20,
        max_file_bytes=16 * 1024 * 1024,
        min_request_interval_seconds=1.05,
    )
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at_utc": started.isoformat(),
        "mode": "READ_ONLY_INTERNAL_PROCESSING",
        "exchange_id": EXCHANGE_ID,
        "hour_start_utc": hour_start.isoformat(),
        "target_symbols": list(TARGET_SYMBOLS),
        "data_types": list(DATA_TYPES),
        "raw_data_persisted": False,
        "repository_visibility": "public",
        "snapshots": [],
        "discovery": {},
        "errors": [],
    }

    discovered: dict[str, set[str]] = {}
    for data_type in DATA_TYPES:
        try:
            symbols = set(provider.discover_symbols(EXCHANGE_ID, data_type))
            discovered[data_type] = symbols
            report["discovery"][data_type] = {
                "count": len(symbols),
                "target_symbols_present": [
                    symbol for symbol in TARGET_SYMBOLS if symbol in symbols
                ],
                "missing_target_symbols": [
                    symbol for symbol in TARGET_SYMBOLS if symbol not in symbols
                ],
            }
        except Exception as exc:
            discovered[data_type] = set()
            report["errors"].append({
                "stage": "symbol_discovery",
                "data_type": data_type,
                "error": type(exc).__name__,
                "detail": str(exc)[:200],
            })

    for symbol in TARGET_SYMBOLS:
        for data_type in DATA_TYPES:
            if symbol not in discovered.get(data_type, set()):
                report["snapshots"].append({
                    "symbol": symbol,
                    "data_type": data_type,
                    "status": "SYMBOL_NOT_COVERED",
                    "raw_file_persisted": False,
                })
                continue
            try:
                snapshot = provider.download_hourly_parquet(
                    EXCHANGE_ID, symbol, data_type, hour_start
                )
                row = _snapshot_report(snapshot)
                row["status"] = "PASS"
                report["snapshots"].append(row)
            except Exception as exc:
                report["snapshots"].append({
                    "symbol": symbol,
                    "data_type": data_type,
                    "status": "UNAVAILABLE",
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "raw_file_persisted": False,
                })

    passed = sum(1 for item in report["snapshots"] if item.get("status") == "PASS")
    expected = len(TARGET_SYMBOLS) * len(DATA_TYPES)
    report["passed"] = passed
    report["expected"] = expected
    report["status"] = "PASS" if passed == expected else "DEGRADED"
    report["interpretation"] = (
        "Schema and row metadata only; not proof of full continuity, semantic correctness, "
        "two-year history, signal value, or Stage 1 acceptance."
    )
    return report


def main() -> int:
    report = run()
    output = Path("cryptohftdata-adapter-smoke.json")
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "passed": report["passed"],
        "expected": report["expected"],
        "hour_start_utc": report["hour_start_utc"],
        "report": str(output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
