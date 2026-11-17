#!/usr/bin/env python3
"""Export Stage 1 Parquet observations as a versioned, raw-only L1 contract."""
from __future__ import annotations

import argparse
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT.parent / "contracts" / "l1-market-data.v1.schema.json"
HOUR_MS = 3_600_000


def _finite(value: Any, *, nullable: bool = False, positive: bool = False) -> float | None:
    if value is None:
        if nullable:
            return None
        raise ValueError("required_numeric_value_missing")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non_finite_numeric_value")
    if positive and number <= 0:
        raise ValueError("numeric_value_not_positive")
    return number


def _read_rows(data_dir: Path, relative_path: str) -> list[dict[str, Any]]:
    path = Path(relative_path)
    if not path.is_absolute():
        path = data_dir / path
    if not path.is_file():
        raise FileNotFoundError(f"parquet_file_missing:{path}")
    return pq.read_table(path).to_pylist()


def _availability(rows: list[dict[str, Any]], key: str) -> str:
    if not rows:
        return "UNAVAILABLE"
    if any(row.get(key) is None for row in rows):
        return "PARTIAL"
    return "AVAILABLE"


def build_contract(
    report: dict[str, Any],
    data_dir: str | Path,
    *,
    max_symbols: int = 10,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build contract without deriving signals, gates, risk, or release decisions."""
    data_root = Path(data_dir)
    acquired = now or datetime.now(timezone.utc)
    if acquired.tzinfo is None:
        raise ValueError("acquisition_time_must_be_timezone_aware")
    acquired = acquired.astimezone(timezone.utc)
    acquired_ms = int(acquired.timestamp() * 1000)
    acquired_text = acquired.isoformat().replace("+00:00", "Z")
    start_ms = acquired_ms - int(float(report.get("history_target_years", 2)) * 365.25 * 24 * HOUR_MS)
    instrument_rows = []
    symbol_reports = report.get("symbols", {})
    if not isinstance(symbol_reports, dict):
        raise ValueError("report_symbols_must_be_object")

    for instrument_id, item in list(symbol_reports.items())[:max_symbols]:
        if "error" in item:
            continue
        identity = item.get("instrument")
        files = item.get("files")
        if not isinstance(identity, dict) or not isinstance(files, dict):
            raise ValueError(f"instrument_identity_or_files_missing:{instrument_id}")
        if identity.get("contract_type") != "linear_perpetual":
            raise ValueError(f"unsupported_contract_type:{instrument_id}")
        for field in ("unified_symbol", "base", "quote", "settle", "provider_id"):
            if not identity.get(field):
                raise ValueError(f"instrument_identity_missing:{instrument_id}:{field}")
        if str(identity["quote"]).upper() != "USDT" or str(identity["settle"]).upper() != "USDT":
            raise ValueError(f"non_usdt_linear_contract_rejected:{instrument_id}")

        raw_candles = _read_rows(data_root, files["ohlcv"])
        candles = []
        seen = set()
        for row in sorted(raw_candles, key=lambda x: int(x["timestamp"])):
            ts = int(row["timestamp"])
            if ts in seen:
                raise ValueError(f"duplicate_ohlcv_timestamp:{instrument_id}:{ts}")
            seen.add(ts)
            if ts + HOUR_MS > acquired_ms:
                continue
            op = _finite(row["open"], positive=True)
            hi = _finite(row["high"], positive=True)
            lo = _finite(row["low"], positive=True)
            cl = _finite(row["close"], positive=True)
            vol = _finite(row["volume"])
            if hi < max(op, cl, lo) or lo > min(op, cl, hi) or vol < 0:
                raise ValueError(f"invalid_ohlcv_relationship:{instrument_id}:{ts}")
            candles.append({
                "timestamp_ms": ts, "open": op, "high": hi, "low": lo,
                "close": cl, "volume": vol, "closed": True,
                "retrieved_at_utc": acquired_text,
            })

        raw_funding = _read_rows(data_root, files["funding"])
        funding = []
        for row in sorted(raw_funding, key=lambda x: int(x["timestamp"])):
            rate = _finite(row.get("funding_rate"), nullable=True)
            mark = _finite(row.get("mark_price"), nullable=True, positive=True)
            funding.append({
                "timestamp_ms": int(row["timestamp"]),
                "funding_rate": rate,
                "mark_price": mark,
            })

        raw_oi = _read_rows(data_root, files["open_interest"])
        open_interest = []
        for row in sorted(raw_oi, key=lambda x: int(x["timestamp"])):
            amount = _finite(row.get("open_interest"), nullable=True, positive=True)
            value = _finite(row.get("open_interest_value_usd"), nullable=True, positive=True)
            open_interest.append({
                "timestamp_ms": int(row["timestamp"]),
                "open_interest": amount,
                "open_interest_value_usd": value,
            })

        ohlcv_report = item.get("ohlcv", {})
        coverage_pct = ohlcv_report.get("coverage_of_requested_window_pct")
        if coverage_pct is not None:
            coverage_pct = _finite(coverage_pct)
        contract_size = _finite(identity.get("contract_size"), nullable=True, positive=True)
        instrument_rows.append({
            "instrument_id": str(identity["instrument_id"]),
            "unified_symbol": str(identity["unified_symbol"]),
            "base": str(identity["base"]).upper(),
            "quote": str(identity["quote"]).upper(),
            "settle": str(identity["settle"]).upper(),
            "contract_type": identity["contract_type"],
            "contract_size": contract_size,
            "provider_id": str(identity["provider_id"]),
            "timeframe": "1h",
            "candles": candles,
            "funding": funding,
            "open_interest": open_interest,
            "availability": {
                "ohlcv": "AVAILABLE" if candles else "UNAVAILABLE",
                "funding": _availability(funding, "funding_rate"),
                "open_interest": _availability(open_interest, "open_interest"),
            },
            "coverage": {
                "ohlcv_rows": len(candles),
                "funding_rows": len(funding),
                "open_interest_rows": len(open_interest),
                "ohlcv_coverage_pct": coverage_pct,
            },
            "errors": [],
        })

    if not instrument_rows:
        raise ValueError("no_exportable_instruments")
    contract = {
        "schema_version": "1.0.0",
        "run_id": str(uuid.uuid4()),
        "producer": {
            "name": "cfss-python-l1-exporter",
            "version": "1.0.0",
            "source_commit": os.getenv("GITHUB_SHA"),
        },
        "acquired_at_utc": acquired_text,
        "window": {"timeframe": "1h", "start_ms": start_ms, "end_ms": acquired_ms},
        "provider": {
            "primary_provider_id": str(report.get("primary_provider", "unknown")),
            "display_name": str(report.get("provider", "unknown")),
            "fallback_used": False,
        },
        "instruments": instrument_rows,
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(contract),
                    key=lambda err: list(err.path))
    if errors:
        raise ValueError("contract_schema_validation_failed:" + ";".join(
            f"{'/'.join(map(str, err.path))}:{err.message}" for err in errors[:8]
        ))
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Stage 1 Parquet data to the Hybrid L1 JSON contract")
    parser.add_argument("--provider", choices=["okx", "binance"], default="okx")
    parser.add_argument("--symbols", type=int, default=10)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--data-dir", default="signal_autopilot/data/stage1-hybrid")
    parser.add_argument("--output", default="artifacts/l1-market-data.v1.json")
    args = parser.parse_args()
    if args.symbols < 1 or args.symbols > 100:
        parser.error("--symbols must be between 1 and 100")

    from app.data_layer.collector import Stage1Collector

    data_dir = Path(args.data_dir)
    collector = Stage1Collector(data_dir=data_dir, provider=args.provider)
    try:
        report = collector.run(target_count=args.symbols, years=args.years)
    finally:
        collector.close()

    contract = build_contract(report, data_dir, max_symbols=args.symbols)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(contract, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                    encoding="utf-8")
    temp.replace(output)
    print(json.dumps({
        "status": "EXPORTED",
        "schema_version": contract["schema_version"],
        "run_id": contract["run_id"],
        "instrument_count": len(contract["instruments"]),
        "output": str(output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
