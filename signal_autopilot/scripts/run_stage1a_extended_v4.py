"""Stage 1a extended v4: Binance Vision S3 universe with independent fallbacks."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import download_stage1a_extended_history as downloader

S3_BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
S3_MONTHLY_PREFIX = "data/futures/um/monthly/klines/"
S3_DAILY_PREFIX = "data/futures/um/daily/klines/"
COINGECKO_DERIVATIVES = "https://api.coingecko.com/api/v3/derivatives"
BINANCE_TICKER_URLS = [
    "https://fapi.binance.com/fapi/v1/ticker/24hr",
    "https://fapi1.binance.com/fapi/v1/ticker/24hr",
    "https://fapi2.binance.com/fapi/v1/ticker/24hr",
    "https://fapi3.binance.com/fapi/v1/ticker/24hr",
    "https://fapi4.binance.com/fapi/v1/ticker/24hr",
]
MIN_QUOTE_VOLUME_USD = 50_000_000
MIN_LISTING_AGE_DAYS = 730
SNAPSHOT_PATH = Path("../config/binance_perpetuals_snapshot.json")


def http_bytes(url: str, method: str = "GET", retries: int = 2) -> tuple[int, bytes]:
    """404/429/سایر 4xx بدون retry؛ retry فقط برای 5xx و timeout."""
    last = "UNKNOWN"
    for attempt in range(retries):
        req = urllib.request.Request(
            url, method=method,
            headers={"User-Agent": "Trade-Stage1A-Extended/4.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return response.status, response.read() if method == "GET" else b""
        except urllib.error.HTTPError as exc:
            if exc.code not in (500, 502, 503, 504):
                return exc.code, b""
            last = f"HTTP_{exc.code}"
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            if not isinstance(reason, (TimeoutError,)) and not isinstance(exc, TimeoutError):
                raise downloader.FetchFailure(f"NETWORK_ERROR:{reason}") from exc
            last = "TIMEOUT"
        if attempt + 1 < retries:
            time.sleep(2 ** attempt)
    raise downloader.FetchFailure(f"RETRIES_EXHAUSTED:{last}")


def get_json(url: str, label: str) -> Any:
    status, body = http_bytes(url)
    if status != 200:
        raise downloader.FetchFailure(f"{label}_HTTP_{status}")
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise downloader.FetchFailure(f"{label}_INVALID_JSON") from exc


def s3_list(prefix: str, delimiter: str | None = None) -> list[str]:
    """List all S3 keys/common-prefixes with ListObjectsV2 pagination."""
    values: list[str] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        url = S3_BUCKET + "?" + urllib.parse.urlencode(params)
        root = ET.fromstring(get_json_xml(url))
        ns = {"s3": root.tag.split("}")[0].strip("{")} if "}" in root.tag else {}
        def findall(name: str):
            return root.findall(f"s3:{name}", ns) if ns else root.findall(name)
        for node in findall("CommonPrefixes"):
            child = node.find("s3:Prefix", ns) if ns else node.find("Prefix")
            if child is not None and child.text:
                values.append(child.text)
        for node in findall("Contents"):
            child = node.find("s3:Key", ns) if ns else node.find("Key")
            if child is not None and child.text:
                values.append(child.text)
        truncated = (root.find("s3:IsTruncated", ns) if ns else root.find("IsTruncated"))
        is_truncated = truncated is not None and (truncated.text or "").lower() == "true"
        if not is_truncated:
            break
        next_token = root.find("s3:NextContinuationToken", ns) if ns else root.find("NextContinuationToken")
        if next_token is None or not next_token.text:
            raise downloader.FetchFailure("S3_TRUNCATED_WITHOUT_CONTINUATION_TOKEN")
        token = next_token.text
    return values


def get_json_xml(url: str) -> bytes:
    status, body = http_bytes(url)
    if status != 200:
        raise downloader.FetchFailure(f"S3_LIST_HTTP_{status}")
    return body


def discover_s3_symbols() -> list[str]:
    prefixes = s3_list(S3_MONTHLY_PREFIX, delimiter="/")
    symbols = sorted({
        p[len(S3_MONTHLY_PREFIX):].strip("/").upper()
        for p in prefixes
        if p.startswith(S3_MONTHLY_PREFIX)
        and p[len(S3_MONTHLY_PREFIX):].strip("/")
    })
    if not symbols:
        raise downloader.FetchFailure("S3_MONTHLY_KLINES_LISTING_EMPTY")
    return symbols


def parse_coingecko_derivatives(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, list):
        raise downloader.FetchFailure("COINGECKO_DERIVATIVES_INVALID_SCHEMA")
    active: dict[str, dict[str, Any]] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "").lower()
        contract = str(row.get("contract_type") or "").lower()
        if "binance" not in market or "futures" not in market or contract not in ("perpetual", "perpetuals"):
            continue
        if row.get("expired_at") not in (None, "", 0):
            continue
        raw_symbol = str(row.get("symbol") or row.get("index_id") or "").upper()
        symbol = re.sub(r"[^A-Z0-9]", "", raw_symbol)
        if not symbol.endswith("USDT"):
            continue
        try:
            volume = float(row.get("volume"))
        except (TypeError, ValueError):
            continue
        if volume < 0:
            continue
        active[symbol] = {
            "quote_volume_24h_usd": volume,
            "metadata_source": "COINGECKO_DERIVATIVES_BINANCE_FUTURES",
            "volume_source": "COINGECKO_DERIVATIVES_VOLUME_USD",
            "market": row.get("market"),
            "contract_type": row.get("contract_type"),
        }
    if not active:
        raise downloader.FetchFailure("COINGECKO_HAS_NO_ACTIVE_BINANCE_USDT_PERPETUALS")
    return active


def parse_binance_tickers(payload: Any) -> dict[str, float]:
    if not isinstance(payload, list):
        raise downloader.FetchFailure("BINANCE_TICKER_INVALID_SCHEMA")
    out = {}
    for row in payload:
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        try:
            out[str(row["symbol"]).upper()] = float(row["quoteVolume"])
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise downloader.FetchFailure("BINANCE_TICKER_NO_QUOTE_VOLUME")
    return out


def oldest_monthly_listing_date(symbol: str) -> str | None:
    prefix = f"{S3_MONTHLY_PREFIX}{symbol}/1h/"
    keys = s3_list(prefix)
    pattern = re.compile(rf"/{re.escape(symbol)}-1h-(\d{{4}})-(\d{{2}})\.zip$")
    months = []
    for key in keys:
        match = pattern.search(key)
        if match:
            year, month = map(int, match.groups())
            if 1 <= month <= 12:
                months.append(date(year, month, 1))
    return min(months).isoformat() if months else None


async def resolve_listing_dates(symbols: list[str]) -> dict[str, str | None]:
    sem = asyncio.Semaphore(8)
    async def one(symbol: str):
        async with sem:
            try:
                value = await asyncio.to_thread(oldest_monthly_listing_date, symbol)
                return symbol, value
            except Exception as exc:
                print(f"LISTING_LOOKUP {symbol} {type(exc).__name__}:{str(exc)[:100]}", flush=True)
                return symbol, None
    pairs = await asyncio.gather(*(one(s) for s in symbols))
    return dict(pairs)


def load_snapshot() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not SNAPSHOT_PATH.exists():
        raise downloader.FetchFailure("SNAPSHOT_NOT_FOUND")
    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    captured = datetime.fromisoformat(str(data["captured_at_utc"]).replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - captured
    if age < timedelta(minutes=-5) or age > timedelta(days=30):
        raise downloader.FetchFailure(f"SNAPSHOT_STALE:{age}")
    rows = data.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise downloader.FetchFailure("SNAPSHOT_EMPTY")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        try:
            volume = float(row.get("quoteVolume", row.get("quote_volume_24h_usd")))
        except (TypeError, ValueError):
            continue
        listing = row.get("listing_date_utc")
        if not listing and row.get("onboardDate"):
            listing = datetime.fromtimestamp(int(row["onboardDate"]) / 1000, timezone.utc).date().isoformat()
        if symbol and listing:
            result[symbol] = {
                "quote_volume_24h_usd": volume,
                "listing_date": str(listing),
                "metadata_source": "BINANCE_OFFICIAL_SNAPSHOT",
                "volume_source": "BINANCE_OFFICIAL_SNAPSHOT",
            }
    if not result:
        raise downloader.FetchFailure("SNAPSHOT_HAS_NO_USABLE_ROWS")
    return result, {"captured_at_utc": data.get("captured_at_utc"), "source": data.get("source")}


async def run_v4(start: date, end: date, outdir: Path, report_path: Path) -> dict[str, Any]:
    if (end - start).days != MIN_LISTING_AGE_DAYS:
        raise ValueError("Historical window must remain exactly 730 days.")

    s3_symbols: list[str] | None = None
    s3_error = None
    try:
        s3_symbols = await asyncio.to_thread(discover_s3_symbols)
        universe_source = "BINANCE_VISION_S3_MONTHLY_DIRECTORY_LISTING"
    except Exception as exc:
        s3_error = f"{type(exc).__name__}:{exc}"
        universe_source = ""

    cg_active: dict[str, dict[str, Any]] | None = None
    cg_error = None
    snapshot_meta: dict[str, Any] = {}
    snapshot_data: dict[str, dict[str, Any]] | None = None

    print(f"V4_S3_DISCOVERY {'OK' if s3_symbols is not None else 'FAILED'} count={len(s3_symbols) if s3_symbols is not None else 0} detail={s3_error}", flush=True)

    if s3_symbols is not None:
        # Primary path: S3 proves archive presence; current Binance snapshot validates active status, quote volume and onboardDate.
        try:
            snapshot_data, snapshot_meta = await asyncio.to_thread(load_snapshot)
            active_symbols = sorted(set(s3_symbols).intersection(snapshot_data))
            metadata_source = snapshot_data
            universe_source = "BINANCE_VISION_S3_DIRECTORY_LISTING"
            if not active_symbols:
                raise downloader.FetchFailure("S3_AND_BINANCE_SNAPSHOT_INTERSECTION_EMPTY")
        except Exception as snapshot_error:
            # CoinGecko is only a metadata substitute when S3 discovery itself succeeded.
            try:
                cg_payload = await asyncio.to_thread(get_json, COINGECKO_DERIVATIVES, "COINGECKO_DERIVATIVES")
                cg_active = parse_coingecko_derivatives(cg_payload)
                active_symbols = sorted(set(s3_symbols).intersection(cg_active))
                metadata_source = cg_active
                universe_source = "BINANCE_VISION_S3_WITH_COINGECKO_METADATA"
                cg_error = f"SNAPSHOT_METADATA_UNAVAILABLE:{type(snapshot_error).__name__}:{snapshot_error}"
                if not active_symbols:
                    raise downloader.FetchFailure("S3_AND_COINGECKO_INTERSECTION_EMPTY")
            except Exception as cg_exc:
                raise downloader.FetchFailure(
                    f"S3_DISCOVERY_OK_BUT_METADATA_SOURCES_FAILED: snapshot={snapshot_error}; coingecko={cg_exc}"
                ) from cg_exc
    else:
        # Fallback 2: CoinGecko derivatives becomes the universe source if S3 listing fails.
        try:
            cg_payload = await asyncio.to_thread(get_json, COINGECKO_DERIVATIVES, "COINGECKO_DERIVATIVES")
            cg_active = parse_coingecko_derivatives(cg_payload)
            active_symbols = sorted(cg_active)
            metadata_source = cg_active
            universe_source = "COINGECKO_DERIVATIVES_BINANCE_FUTURES_FALLBACK"
        except Exception as cg_exc:
            cg_error = f"{type(cg_exc).__name__}:{cg_exc}"
            # Fallback 3: manually refreshed Binance snapshot, valid for at most 30 days.
            snapshot_data, snapshot_meta = await asyncio.to_thread(load_snapshot)
            active_symbols = sorted(snapshot_data)
            metadata_source = snapshot_data
            universe_source = "BINANCE_OFFICIAL_30D_SNAPSHOT_FALLBACK"

    print(f"V4_METADATA_SOURCE {universe_source}; active_symbols={len(active_symbols)}; snapshot={snapshot_meta.get('captured_at_utc')}", flush=True)

    # Use the volume supplied by the selected source. Binance ticker is a final live refresh when using CoinGecko only.
    volume_source = "BINANCE_OFFICIAL_SNAPSHOT_QUOTEVOLUME" if snapshot_data is not None else "COINGECKO_DERIVATIVES_VOLUME_USD"
    ticker_volumes: dict[str, float] = {}
    if snapshot_data is None and cg_active is not None:
        for ticker_url in BINANCE_TICKER_URLS:
            try:
                ticker_payload = await asyncio.to_thread(get_json, ticker_url, "BINANCE_TICKER_24HR")
                ticker_volumes = parse_binance_tickers(ticker_payload)
                volume_source = "BINANCE_TICKER_24HR_QUOTEVOLUME"
                break
            except Exception:
                continue

    candidates = []
    for symbol in active_symbols:
        meta = metadata_source.get(symbol, {})
        volume = ticker_volumes.get(symbol) if ticker_volumes else meta.get("quote_volume_24h_usd")
        if volume is not None and float(volume) >= MIN_QUOTE_VOLUME_USD:
            candidates.append((symbol, float(volume), meta))
    counts = {
        "binance_vision_s3_symbol_directories": len(s3_symbols) if s3_symbols is not None else None,
        "active_binance_usdt_perpetuals": len(active_symbols),
        "symbols_volume_50m": len(candidates),
        "symbols_listing_730d": 0,
        "listing_metadata_missing": 0,
    }

    # Prefer the official onboardDate snapshot; otherwise infer from the oldest monthly archive.
    if snapshot_data is not None:
        listing_dates = {s: snapshot_data[s].get("listing_date") for s in active_symbols}
        listing_method = "BINANCE_OFFICIAL_SNAPSHOT_ONBOARDDATE"
    else:
        listing_dates = await resolve_listing_dates([s for s, _, _ in candidates])
        listing_method = "OLDEST_BINANCE_VISION_MONTHLY_1H_ARCHIVE_APPROXIMATION"

    listing_map: dict[str, dict[str, Any]] = {}
    qualifying: list[str] = []
    inventory = []
    for symbol, volume, meta in candidates:
        listing_date = listing_dates.get(symbol) or meta.get("listing_date")
        classification = "EXCLUDED_LISTING_DATE_UNAVAILABLE"
        if listing_date:
            try:
                if date.fromisoformat(str(listing_date)) <= start:
                    classification = "QUALIFYING_VOLUME_AND_LISTING_AGE"
                    qualifying.append(symbol)
                    counts["symbols_listing_730d"] += 1
                else:
                    classification = "EXCLUDED_LISTED_WITHIN_730D"
            except ValueError:
                listing_date = None
        if listing_date is None:
            counts["listing_metadata_missing"] += 1
        listing_map[symbol] = {
            "listing_date": str(listing_date) if listing_date else None,
            "status": "TRADING_PROXY" if snapshot_data is None else "SNAPSHOT_STATUS",
            "contract_type": "PERPETUAL",
            "metadata_source": meta.get("metadata_source", listing_method),
            "volume_source": volume_source if ticker_volumes else meta.get("volume_source"),
            "quote_volume_24h_usd": volume,
            "listing_date_method": listing_method,
        }
        inventory.append({
            "symbol": symbol, "quote_volume_24h_usd": volume,
            "listing_date": listing_date, "classification": classification,
            "listing_date_method": listing_method,
        })

    downloader.fetch_exchange_info = lambda: listing_map
    downloader.request_bytes = http_bytes
    report = await downloader.run(qualifying, start, end, outdir, report_path)
    report.update({
        "source": "BINANCE_VISION_S3_WITH_BINANCE_SNAPSHOT_METADATA",
        "universe_source": universe_source,
        "s3_error": s3_error,
        "coingecko_error": cg_error,
        "universe_snapshot_metadata": snapshot_meta,
        "volume_source": volume_source,
        "volume_threshold_usd": MIN_QUOTE_VOLUME_USD,
        "listing_age_threshold_days": MIN_LISTING_AGE_DAYS,
        "listing_date_method": listing_method,
        "listing_date_is_approximate": listing_method.startswith("OLDEST_"),
        "universe_counts": counts,
        "universe_inventory": inventory,
        "symbols_full_history": sum(row.get("continuity") is True for row in report.get("symbols", [])),
        "stage1a_extended_status": "PASS" if sum(row.get("continuity") is True for row in report.get("symbols", [])) >= 27 else "FAIL",
    })
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "universe_source": universe_source,
        "counts": counts,
        "symbols_full_history": report["symbols_full_history"],
        "status": report["stage1a_extended_status"],
        "archive_requests_issued": report.get("archive_requests_issued"),
    }
    print("STAGE1A_V4_SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return report


def _json_endpoint_valid(url: str) -> bool:
    try:
        payload = get_json(url, "BINANCE_TICKER_24HR")
        parse_binance_tickers(payload)
        _json_endpoint_valid.last_payload = payload
        return True
    except Exception:
        return False


_json_endpoint_valid.last_payload = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", default="../market-data/datasets/stage1a_extended_v4/ohlcv_1h")
    parser.add_argument("--report", default="data/stage1a_extended_v4_report.json")
    args = parser.parse_args()
    report = asyncio.run(run_v4(
        date.fromisoformat(args.start_date), date.fromisoformat(args.end_date),
        Path(args.output_dir), Path(args.report),
    ))
    return 0 if report["stage1a_extended_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
