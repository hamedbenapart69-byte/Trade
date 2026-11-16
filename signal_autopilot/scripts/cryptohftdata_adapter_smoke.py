"""Smoke test واقعی CryptoHFTData؛ فقط فراداده را نگه می‌دارد، نه دادهٔ خام."""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# اجرای مستقیم اسکریپت از پوشهٔ scripts، ریشهٔ مخزن را به مسیر import اضافه می‌کند.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from signal_autopilot.modules.cryptohftdata_provider import (
    CryptoHFTDataProvider,
    latest_complete_hour,
)

EXCHANGE_ID = "binance_futures"
TARGETS_BY_TYPE = {
    "mark_price": ("BTCUSDT", "ETHUSDT", "SOLUSDT", "FILUSDT"),
    "open_interest": ("BTCUSDT", "ETHUSDT", "SOLUSDT", "FILUSDT"),
    "trades": ("FILUSDT", "SOLUSDT"),
    "liquidations": ("FILUSDT",),
}
CORE_TYPES = frozenset({"mark_price", "open_interest"})


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


def _positive_count(values: list[Any]) -> int:
    count = 0
    for value in values:
        try:
            if value is not None and float(value) > 0:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


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
        "trades": (
            "received_time", "event_time", "symbol", "trade_id",
            "price", "quantity", "trade_time", "is_buyer_maker", "order_type",
        ),
        "liquidations": (
            "received_time", "event_time", "symbol", "side", "order_type",
            "time_in_force", "quantity", "price", "average_price",
            "order_status", "filled_quantity", "trade_time",
        ),
    }[snapshot.data_type]
    symbols = sorted({
        str(value).upper()
        for value in table.column("symbol").to_pylist()
        if value is not None
    })
    timestamp_columns = {
        "mark_price": ("event_time", "received_time", "next_funding_time"),
        "open_interest": ("timestamp", "received_time"),
        "trades": ("event_time", "trade_time", "received_time"),
        "liquidations": ("event_time", "trade_time", "received_time"),
    }[snapshot.data_type]
    report = {
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
    if snapshot.data_type == "trades":
        order_types = table.column("order_type").to_pylist()
        trade_ids = [
            int(value) for value in table.column("trade_id").to_pylist()
            if value is not None
        ]
        unique_ids = sorted(set(trade_ids))
        report["trade_quality"] = {
            "order_type_counts": dict(Counter(str(x) for x in order_types)),
            "na_order_type_rows": sum(1 for x in order_types if str(x) == "NA"),
            "positive_price_rows": _positive_count(table.column("price").to_pylist()),
            "positive_quantity_rows": _positive_count(table.column("quantity").to_pylist()),
            "trade_id_rows": len(trade_ids),
            "unique_trade_ids": len(unique_ids),
            "duplicate_trade_ids": len(trade_ids) - len(unique_ids),
            "trade_id_gaps_inside_file": sum(
                1 for left, right in zip(unique_ids, unique_ids[1:])
                if right - left > 1
            ),
            "is_buyer_maker_counts": {
                str(k): v for k, v in Counter(
                    str(x) for x in table.column("is_buyer_maker").to_pylist()
                ).items()
            },
        }
    elif snapshot.data_type == "liquidations":
        report["liquidation_quality"] = {
            "side_counts": {
                str(k): v for k, v in Counter(
                    str(x) for x in table.column("side").to_pylist()
                ).items()
            },
            "coverage_label": "SAMPLED_LOWER_BOUND",
            "note": "Provider documents Binance force-order liquidation events as sampled, not a complete liquidation tape.",
        }
    return report


def run() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    hour_start = latest_complete_hour(started)
    provider = CryptoHFTDataProvider(
        api_key=None,
        timeout_seconds=25,
        max_file_bytes=32 * 1024 * 1024,
        min_request_interval_seconds=1.05,
    )
    report: dict[str, Any] = {
        "schema_version": "1.1",
        "generated_at_utc": started.isoformat(),
        "mode": "READ_ONLY_INTERNAL_PROCESSING",
        "exchange_id": EXCHANGE_ID,
        "hour_start_utc": hour_start.isoformat(),
        "targets_by_type": {
            key: list(value) for key, value in TARGETS_BY_TYPE.items()
        },
        "raw_data_persisted": False,
        "repository_visibility": "public",
        "snapshots": [],
        "discovery": {},
        "errors": [],
    }

    discovered: dict[str, set[str]] = {}
    for data_type, targets in TARGETS_BY_TYPE.items():
        try:
            symbols = set(provider.discover_symbols(EXCHANGE_ID, data_type))
            discovered[data_type] = symbols
            report["discovery"][data_type] = {
                "count": len(symbols),
                "target_symbols_present": [
                    symbol for symbol in targets if symbol in symbols
                ],
                "missing_target_symbols": [
                    symbol for symbol in targets if symbol not in symbols
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

    for data_type, targets in TARGETS_BY_TYPE.items():
        for symbol in targets:
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

    core_rows = [
        item for item in report["snapshots"]
        if item.get("data_type") in CORE_TYPES
    ]
    optional_rows = [
        item for item in report["snapshots"]
        if item.get("data_type") not in CORE_TYPES
    ]
    core_passed = sum(1 for item in core_rows if item.get("status") == "PASS")
    optional_passed = sum(1 for item in optional_rows if item.get("status") == "PASS")
    core_expected = sum(len(TARGETS_BY_TYPE[k]) for k in CORE_TYPES)
    report["core_passed"] = core_passed
    report["core_expected"] = core_expected
    report["optional_passed"] = optional_passed
    report["optional_expected"] = len(optional_rows)
    report["optional_status"] = (
        "PASS" if optional_rows and optional_passed == len(optional_rows)
        else "PARTIAL" if optional_rows else "NOT_TESTED"
    )
    report["status"] = "PASS" if core_passed == core_expected else "DEGRADED"
    report["interpretation"] = (
        "Schema and bounded metadata only; not proof of full continuity, semantic correctness, "
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
        "core_passed": report["core_passed"],
        "core_expected": report["core_expected"],
        "optional_status": report["optional_status"],
        "optional_passed": report["optional_passed"],
        "optional_expected": report["optional_expected"],
        "hour_start_utc": report["hour_start_utc"],
        "report": str(output),
    }, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
