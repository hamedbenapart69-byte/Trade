"""Stage 1a extended v3: full Binance USDⓈ-M perpetual universe."""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import download_stage1a_extended_history as downloader

EXCHANGE_INFO_URLS = downloader.EXCHANGE_INFO_URLS
TICKER_URLS = [
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
    "https://fapi1.binance.com/fapi/v1/ticker/24hr",
    "https://fapi2.binance.com/fapi/v1/ticker/24hr",
    "https://fapi3.binance.com/fapi/v1/ticker/24hr",
    "https://fapi4.binance.com/fapi/v1/ticker/24hr",
]
MIN_QUOTE_VOLUME_USD = 50_000_000
MIN_LISTING_AGE_DAYS = 730


def strict_request_bytes(url: str, method: str = "GET", retries: int = 3) -> tuple[int, bytes]:
    """Retry only HTTP 5xx and actual timeouts; never retry 404/403/429/other 4xx."""
    last_error = "UNKNOWN"
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            method=method,
            headers={"User-Agent": "Trade-Stage1A-Extended/3.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                payload = response.read() if method == "GET" else b""
                return response.status, payload
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504):
                return exc.code, b""
            last_error = f"HTTP_{exc.code}"
        except (TimeoutError, socket.timeout):
            last_error = "TIMEOUT"
        except urllib.error.URLError as exc:
            if not isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise downloader.FetchFailure(f"NETWORK_ERROR:{exc.reason}") from exc
            last_error = "TIMEOUT"
        if attempt < retries - 1:
            time.sleep(min(2 ** attempt, 8))
    raise downloader.FetchFailure(f"RETRIES_EXHAUSTED_{last_error}")


def fetch_json_fallback(urls: list[str], label: str, validator) -> Any:
    failures: list[str] = []
    for url in urls:
        try:
            status, payload = strict_request_bytes(url, "GET")
            if status != 200:
                failures.append(f"{url}:HTTP_{status}")
                continue
            parsed = json.loads(payload)
            validator(parsed)
            return parsed
        except Exception as exc:
            failures.append(f"{url}:{type(exc).__name__}:{str(exc)[:160]}")
    raise downloader.FetchFailure(f"{label}_ALL_ENDPOINTS_FAILED | " + " | ".join(failures))


def parse_exchange_info(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        payload = payload["data"]
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise downloader.FetchFailure("INVALID_EXCHANGE_INFO_SCHEMA")
    return payload["symbols"]


def parse_tickers(payload: Any) -> dict[str, float]:
    if not isinstance(payload, list):
        raise downloader.FetchFailure("INVALID_TICKER_24HR_SCHEMA")
    volumes: dict[str, float] = {}
    for item in payload:
        if not isinstance(item, dict) or not item.get("symbol"):
            continue
        try:
            volumes[str(item["symbol"])] = float(item["quoteVolume"])
        except (KeyError, TypeError, ValueError):
            continue
    if not volumes:
        raise downloader.FetchFailure("TICKER_24HR_HAS_NO_QUOTE_VOLUME")
    return volumes


def build_universe(
    exchange_symbols: list[dict[str, Any]],
    quote_volumes: dict[str, float],
    listing_cutoff: date,
) -> tuple[dict[str, dict[str, Any]], list[str], list[dict[str, Any]], dict[str, int]]:
    """Return all active USDT-M perpetual metadata and the 50M+ scan universe."""
    all_perpetuals: dict[str, dict[str, Any]] = {}
    inventory: list[dict[str, Any]] = []
    volume_candidates: list[str] = []
    counts = {
        "binance_usdtm_perpetuals_total": 0,
        "symbols_volume_50m": 0,
        "symbols_listing_730d": 0,
        "listing_metadata_missing": 0,
        "volume_data_missing": 0,
    }

    for item in exchange_symbols:
        if not isinstance(item, dict):
            continue
        if (
            item.get("contractType") != "PERPETUAL"
            or item.get("status") != "TRADING"
            or item.get("quoteAsset") != "USDT"
            or item.get("marginAsset") != "USDT"
        ):
            continue

        symbol = str(item.get("symbol") or "")
        if not symbol:
            continue
        counts["binance_usdtm_perpetuals_total"] += 1

        onboard = item.get("onboardDate")
        listing_date: str | None = None
        if onboard is not None:
            try:
                onboard_ms = int(onboard)
                if onboard_ms > 0:
                    listing_date = datetime.fromtimestamp(
                        onboard_ms / 1000, timezone.utc
                    ).date().isoformat()
            except (TypeError, ValueError, OSError, OverflowError):
                listing_date = None

        quote_volume = quote_volumes.get(symbol)
        metadata = {
            "listing_date": listing_date,
            "status": item.get("status"),
            "contract_type": item.get("contractType"),
            "quote_volume_24h_usd": quote_volume,
            "metadata_source": "BINANCE_FAPI_EXCHANGE_INFO",
            "volume_source": "BINANCE_FAPI_TICKER_24HR",
        }
        all_perpetuals[symbol] = metadata

        if quote_volume is None:
            counts["volume_data_missing"] += 1
            inventory.append({
                "symbol": symbol,
                "quote_volume_24h_usd": None,
                "listing_date": listing_date,
                "classification": "EXCLUDED_VOLUME_UNAVAILABLE",
            })
            continue
        if quote_volume < MIN_QUOTE_VOLUME_USD:
            inventory.append({
                "symbol": symbol,
                "quote_volume_24h_usd": quote_volume,
                "listing_date": listing_date,
                "classification": "EXCLUDED_VOLUME_BELOW_50M",
            })
            continue

        counts["symbols_volume_50m"] += 1
        if listing_date is None:
            counts["listing_metadata_missing"] += 1
            classification = "EXCLUDED_LISTING_DATE_UNAVAILABLE"
        else:
            volume_candidates.append(symbol)
        if listing_date is None:
            pass
        elif date.fromisoformat(listing_date) <= listing_cutoff:
            counts["symbols_listing_730d"] += 1
            classification = "QUALIFYING_VOLUME_AND_LISTING_AGE"
        else:
            classification = "EXCLUDED_LISTED_WITHIN_730D"

        inventory.append({
            "symbol": symbol,
            "quote_volume_24h_usd": quote_volume,
            "listing_date": listing_date,
            "classification": classification,
        })

    volume_candidates.sort(key=lambda sym: all_perpetuals[sym]["quote_volume_24h_usd"], reverse=True)
    inventory.sort(key=lambda row: row["symbol"])
    return all_perpetuals, volume_candidates, inventory, counts


def load_recent_snapshot(path: Path) -> tuple[list[dict[str, Any]], dict[str, float], dict[str, Any]]:
    """Use a recent Binance-sourced snapshot only when the runner is region-blocked."""
    if not path.exists():
        raise downloader.FetchFailure("BINANCE_SNAPSHOT_NOT_FOUND")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    captured = datetime.fromisoformat(str(snapshot["captured_at_utc"]).replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - captured
    if age < timedelta(minutes=-5) or age > timedelta(hours=6):
        raise downloader.FetchFailure(f"BINANCE_SNAPSHOT_STALE_OR_CLOCK_INVALID:{age}")
    rows = snapshot.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise downloader.FetchFailure("BINANCE_SNAPSHOT_HAS_NO_SYMBOLS")
    volumes: dict[str, float] = {}
    for row in rows:
        try:
            if row.get("quoteVolume") is not None:
                volumes[str(row["symbol"])] = float(row["quoteVolume"])
        except (TypeError, ValueError):
            continue
    if not volumes:
        raise downloader.FetchFailure("BINANCE_SNAPSHOT_HAS_NO_TICKER_VOLUMES")
    return rows, volumes, {
        "captured_at_utc": snapshot.get("captured_at_utc"),
        "exchange_server_time_utc": snapshot.get("exchange_server_time_utc"),
        "ticker_latest_close_utc": snapshot.get("ticker_latest_close_utc"),
        "source": snapshot.get("source"),
    }


async def run_v3(start: date, end: date, outdir: Path, report_path: Path) -> dict[str, Any]:
    if (end - start).days != MIN_LISTING_AGE_DAYS:
        raise ValueError("The historical window must remain exactly 730 days.")

    source_mode = "LIVE_BINANCE_FAPI"
    snapshot_meta: dict[str, Any] = {}
    try:
        exchange_payload = fetch_json_fallback(
            EXCHANGE_INFO_URLS, "BINANCE_EXCHANGE_INFO", parse_exchange_info
        )
        exchange_symbols = parse_exchange_info(exchange_payload)
        ticker_payload = fetch_json_fallback(
            TICKER_URLS, "BINANCE_TICKER_24HR", parse_tickers
        )
        quote_volumes = parse_tickers(ticker_payload)
    except Exception as live_error:
        snapshot_path = Path("data/binance_usdm_perpetual_snapshot_v3.json")
        try:
            exchange_symbols, quote_volumes, snapshot_meta = load_recent_snapshot(snapshot_path)
            source_mode = "RECENT_BINANCE_OFFICIAL_DATA_SNAPSHOT"
            print(
                f"BINANCE_LIVE_API_UNAVAILABLE; using recent snapshot captured "
                f"{snapshot_meta.get('captured_at_utc')}; cause={type(live_error).__name__}:{live_error}",
                flush=True,
            )
        except Exception as snapshot_error:
            raise downloader.FetchFailure(
                f"LIVE_BINANCE_API_FAILED:{live_error}; SNAPSHOT_FALLBACK_FAILED:{snapshot_error}"
            ) from snapshot_error

    listing_map, symbols, inventory, counts = build_universe(
        exchange_symbols, quote_volumes, start
    )
    # V3 explicitly bypasses the stale 62-symbol snapshot used by the V2 runner.
    downloader.fetch_exchange_info = lambda: listing_map
    downloader.request_bytes = strict_request_bytes

    report = await downloader.run(symbols, start, end, outdir, report_path)

    report["source"] = "BINANCE_USDM_EXCHANGE_INFO_AND_24HR_TICKER"
    report["universe_source"] = "BINANCE_FAPI_EXCHANGE_INFO_FULL_USDTM_PERPETUALS"
    report["universe_source_mode"] = source_mode
    report["universe_snapshot_metadata"] = snapshot_meta
    report["volume_source"] = "BINANCE_FAPI_TICKER_24HR_QUOTE_VOLUME"
    report["volume_unit"] = "USDT quote volume; USD-equivalent threshold proxy"
    report["volume_threshold_usdt"] = MIN_QUOTE_VOLUME_USD
    report["archive_fallback_chain"] = "monthly ZIP -> daily ZIP"
    report["graceful_degradation"] = "per-symbol errors recorded; only complete history emits Parquet"
    report["progress_checkpoint_resume"] = True
    report["listing_age_threshold_days"] = MIN_LISTING_AGE_DAYS
    report["listing_cutoff_utc"] = start.isoformat()
    report["universe_counts"] = counts
    report["universe_inventory"] = inventory
    for row in report.get("symbols", []):
        meta = listing_map.get(row.get("symbol"), {})
        row["quote_volume_24h_usd"] = meta.get("quote_volume_24h_usd")
    report["symbols_full_history"] = sum(
        row.get("continuity") is True for row in report.get("symbols", [])
    )
    report["stage1a_extended_status"] = (
        "PASS" if report["symbols_full_history"] >= 40 else "FAIL"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_counts": counts,
        "volume_threshold_usd": MIN_QUOTE_VOLUME_USD,
        "listing_age_threshold_days": MIN_LISTING_AGE_DAYS,
        "symbols_full_history": report["symbols_full_history"],
        "stage1a_extended_status": report["stage1a_extended_status"],
        "archive_requests_issued": report.get("archive_requests_issued"),
    }
    print("STAGE1A_V3_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output-dir", default="../market-data/datasets/stage1a_extended_v3/ohlcv_1h")
    parser.add_argument("--report", default="data/stage1a_extended_v3_report.json")
    args = parser.parse_args()

    end = date.fromisoformat(args.end_date) if args.end_date else datetime.now(timezone.utc).date()
    start = date.fromisoformat(args.start_date) if args.start_date else end - timedelta(days=730)
    report = asyncio.run(run_v3(start, end, Path(args.output_dir), Path(args.report)))
    return 0 if report["stage1a_extended_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
