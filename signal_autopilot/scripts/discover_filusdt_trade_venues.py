"""کشف پوشش نماد FIL در آرشیو عمومی چندبازاری؛ بدون دانلود فایل خام."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from signal_autopilot.modules.cryptohftdata_provider import CryptoHFTDataProvider, ALLOWED_EXCHANGES

EXCHANGES = (
    "binance_futures",
    "bybit",
    "kraken_futures",
    "okx_futures",
    "bitget_futures",
    "hyperliquid_futures",
    "aster_futures",
    "lighter",
    "bitmex",
)


def summarize_symbol_coverage(exchange_id: str, symbols: list[str], target: str = "FILUSDT") -> dict[str, Any]:
    normalized = sorted({str(symbol).upper() for symbol in symbols})
    return {
        "exchange_id": exchange_id,
        "symbol_count": len(normalized),
        "exact_target_symbol": target in normalized,
        "fil_related_candidates": [symbol for symbol in normalized if "FIL" in symbol][:30],
        "instrument_equivalence": "NOT_ESTABLISHED",
        "download_test": "NOT_RUN",
    }


def run(provider: Any | None = None) -> dict[str, Any]:
    client = provider or CryptoHFTDataProvider(
        api_key=None,
        timeout_seconds=20,
        max_file_bytes=32 * 1024 * 1024,
        min_request_interval_seconds=1.05,
    )
    results = []
    for exchange_id in EXCHANGES:
        try:
            symbols = client.discover_symbols(exchange_id, "trades")
            results.append({
                "status": "PASS",
                **summarize_symbol_coverage(exchange_id, symbols),
            })
        except Exception as exc:
            results.append({
                "status": "UNAVAILABLE",
                "exchange_id": exchange_id,
                "error_type": type(exc).__name__,
                "reason": str(exc)[:180],
                "instrument_equivalence": "NOT_ESTABLISHED",
                "download_test": "NOT_RUN",
            })
        time.sleep(0.2)

    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "CryptoHFTData",
        "data_type": "trades",
        "target_symbol": "FILUSDT",
        "mode": "PUBLIC_READ_ONLY_SYMBOL_DISCOVERY",
        "api_key_used": False,
        "raw_market_data_downloaded": False,
        "results": results,
        "interpretation": (
            "A symbol-name match is discovery evidence only. It does not prove contract equivalence, "
            "listing status, quantity units, or permission to merge data into the canonical stream."
        ),
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("filusdt-venue-discovery.json"))
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "target_symbol": report["target_symbol"],
        "results": [
            {
                "exchange_id": item["exchange_id"],
                "status": item["status"],
                "exact_target_symbol": item.get("exact_target_symbol"),
                "fil_related_candidates": item.get("fil_related_candidates", []),
            }
            for item in report["results"]
        ],
        "report": str(args.output),
    }, ensure_ascii=False))
    return 0 if any(
        item.get("exact_target_symbol") for item in report["results"]
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
