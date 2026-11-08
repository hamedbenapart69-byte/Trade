#!/usr/bin/env python3
"""Read-only GitHub Actions runner audit for public crypto market-data endpoints.

No credentials, exchange accounts, trading endpoints, or order execution are used.
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from typing import Any

UA = "Trade-Data-Audit/1.0 (+read-only public market data)"
TIMEOUT = 20


def iso_ms(value: Any) -> str | None:
    try:
        raw = str(value).strip()
        if raw.isdigit():
            numeric = int(raw)
            divisor = 1_000_000 if len(raw) >= 16 else (1_000 if len(raw) >= 13 else 1)
            return datetime.fromtimestamp(numeric / divisor, tz=timezone.utc).isoformat()
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def request(url: str, method: str = "GET", max_bytes: int = 8_000_000) -> dict[str, Any]:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "application/json,*/*"})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            body = response.read(max_bytes + 1)
            return {
                "http_status": response.status,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "headers": {k: v for k, v in response.headers.items()
                            if k.lower() in {"x-mbx-used-weight", "x-mbx-used-weight-1m",
                                             "x-bapi-limit", "x-bapi-limit-status",
                                             "x-bapi-limit-reset-timestamp", "content-length",
                                             "last-modified", "date"}},
                "body": body if len(body) <= max_bytes else None,
                "body_truncated": len(body) > max_bytes,
            }
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(500).decode("utf-8", "replace")
        except Exception:
            detail = ""
        return {"http_status": exc.code, "elapsed_ms": round((time.monotonic() - started) * 1000),
                "error": "HTTPError", "detail": detail}
    except Exception as exc:
        return {"http_status": None, "elapsed_ms": round((time.monotonic() - started) * 1000),
                "error": type(exc).__name__, "detail": str(exc)[:300]}


def get_json(name: str, url: str) -> dict[str, Any]:
    result = request(url)
    body = result.pop("body", None)
    if body is not None:
        try:
            obj = json.loads(body.decode("utf-8"))
            result["json_valid"] = True
            if name == "binance_funding_earliest":
                result["count"] = len(obj) if isinstance(obj, list) else None
                if isinstance(obj, list) and obj:
                    result["first_record_utc"] = iso_ms(obj[0].get("fundingTime"))
                    result["last_record_utc"] = iso_ms(obj[-1].get("fundingTime"))
                    result["first_record"] = obj[0]
            elif name == "binance_open_interest_daily":
                result["count"] = len(obj) if isinstance(obj, list) else None
                if isinstance(obj, list) and obj:
                    result["first_record_utc"] = iso_ms(obj[0].get("timestamp"))
                    result["last_record_utc"] = iso_ms(obj[-1].get("timestamp"))
            elif name == "bybit_funding":
                rows = obj.get("result", {}).get("list", [])
                result.update({"retCode": obj.get("retCode"), "count": len(rows),
                               "newest_utc": iso_ms(rows[0].get("fundingRateTimestamp")) if rows else None,
                               "oldest_utc": iso_ms(rows[-1].get("fundingRateTimestamp")) if rows else None})
            elif name == "bybit_open_interest":
                rows = obj.get("result", {}).get("list", [])
                result.update({"retCode": obj.get("retCode"), "count": len(rows),
                               "newest_utc": iso_ms(rows[0].get("timestamp")) if rows else None,
                               "oldest_utc": iso_ms(rows[-1].get("timestamp")) if rows else None})
            elif name == "binance_depth":
                result.update({"lastUpdateId": obj.get("lastUpdateId"),
                               "bid_levels": len(obj.get("bids", [])),
                               "ask_levels": len(obj.get("asks", []))})
            elif name == "okx_orderbook":
                rows = obj.get("data", [])
                book = rows[0] if rows else {}
                result.update({"code": obj.get("code"), "message": obj.get("msg"),
                               "bid_levels": len(book.get("bids", [])),
                               "ask_levels": len(book.get("asks", [])),
                               "ts": book.get("ts")})
            elif name in {"binance_spot_kline", "binance_futures_kline"}:
                result["count"] = len(obj) if isinstance(obj, list) else None
                if isinstance(obj, list) and obj:
                    result["first_open_utc"] = iso_ms(obj[0][0])
                    result["last_open_utc"] = iso_ms(obj[-1][0])
                    result["last_closed_utc"] = iso_ms(obj[-1][6])
                    result["last_close"] = float(obj[-1][4])
            elif name.startswith("kucoin_futures_klines"):
                rows = obj.get("data", []) if isinstance(obj, dict) else []
                result["count"] = len(rows)
                if rows:
                    result["first_open_utc"] = iso_ms(rows[0][0])
                    result["last_open_utc"] = iso_ms(rows[-1][0])
                    result["first_close"] = float(rows[0][4])
                    result["last_close"] = float(rows[-1][4])
            elif name == "kucoin_funding_2y":
                rows = obj.get("data", []) if isinstance(obj, dict) else []
                result["count"] = len(rows)
                if rows:
                    times = [int(row.get("timepoint", 0)) for row in rows if row.get("timepoint") is not None]
                    result["oldest_utc"] = iso_ms(min(times)) if times else None
                    result["newest_utc"] = iso_ms(max(times)) if times else None
            elif name == "kucoin_open_interest_2y_daily":
                rows = obj.get("data", []) if isinstance(obj, dict) else []
                result["count"] = len(rows)
                if rows:
                    times = [int(row.get("ts", 0)) for row in rows if row.get("ts") is not None]
                    result["oldest_utc"] = iso_ms(min(times)) if times else None
                    result["newest_utc"] = iso_ms(max(times)) if times else None
            else:
                result["top_level_type"] = type(obj).__name__
        except Exception as exc:
            result.update({"json_valid": False, "parse_error": str(exc)[:200]})
    return {"name": name, **result}


def archive_kline(name: str, market: str, month: str, symbol: str = "BTCUSDT") -> dict[str, Any]:
    base = "https://data.binance.vision/data"
    if market == "spot":
        path = f"spot/monthly/klines/{symbol}/1h/{symbol}-1h-{month}.zip"
    else:
        path = f"futures/um/monthly/klines/{symbol}/1h/{symbol}-1h-{month}.zip"
    result = request(f"{base}/{path}", max_bytes=5_000_000)
    body = result.pop("body", None)
    out: dict[str, Any] = {"name": name, **result, "archive_path": path}
    if body is None:
        return out
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            csv_name = next(n for n in archive.namelist() if n.endswith(".csv"))
            rows = list(csv.reader(io.TextIOWrapper(archive.open(csv_name), encoding="utf-8")))
        if rows and rows[0] and not rows[0][0].isdigit():
            rows = rows[1:]
        parsed = [row for row in rows if len(row) >= 5]
        if parsed:
            closes = {}
            for row in parsed:
                ts = iso_ms(row[0])
                if ts:
                    closes[ts] = float(row[4])
            out.update({"archive_rows": len(parsed), "first_open_raw": parsed[0][0],
                        "last_open_raw": parsed[-1][0], "first_open_utc": iso_ms(parsed[0][0]),
                        "last_open_utc": iso_ms(parsed[-1][0]), "matched_timestamp_count": len(closes),
                        "last_close": float(parsed[-1][4]), "close_by_open_time": closes})
    except Exception as exc:
        out["archive_parse_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return out


def probe_csv(name: str, path: str) -> dict[str, Any]:
    result = request(f"https://data.binance.vision/data/{path}", max_bytes=2_000_000)
    body = result.pop("body", None)
    out: dict[str, Any] = {"name": name, "archive_path": path, **result}
    if body is not None:
        try:
            rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))
            out["row_count"] = len(rows)
            out["header_or_first_row"] = rows[0] if rows else None
            out["sample_row"] = rows[1] if len(rows) > 1 else None
        except Exception as exc:
            out["parse_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    return out


def main() -> None:
    q = urllib.parse.urlencode({"symbol": "BTCUSDT", "startTime": 0, "limit": 1000})
    results = [
        get_json("binance_funding_earliest", f"https://fapi.binance.com/fapi/v1/fundingRate?{q}"),
        get_json("binance_funding_fapi1", f"https://fapi1.binance.com/fapi/v1/fundingRate?{q}"),
        get_json("binance_open_interest_daily",
                 "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1d&limit=30"),
        get_json("binance_depth", "https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=100"),
        get_json("okx_orderbook", "https://www.okx.com/api/v5/market/books?instId=BTC-USDT-SWAP&sz=50"),
        get_json("bybit_funding",
                 "https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=200"),
        get_json("bybit_open_interest",
                 "https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1d&limit=200"),
        get_json("bybit_long_short_ratio",
                 "https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=1h&limit=2"),
        archive_kline("binance_vision_spot_1h_2026_10", "spot", "2026-10"),
        archive_kline("binance_vision_um_futures_1h_2026_10", "futures_um", "2026-10"),
        archive_kline("binance_vision_spot_1h_2024_11", "spot", "2024-11"),
        archive_kline("binance_vision_um_futures_1h_2024_11", "futures_um", "2024-11"),
        probe_csv("binance_vision_metrics_2026_10_01",
                  "futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-10-01.csv"),
        probe_csv("binance_vision_funding_rate_2026_10_01",
                  "futures/um/daily/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10-01.csv"),
        get_json("kucoin_futures_klines_2y_start",
                 "https://api-futures.kucoin.com/api/v1/kline/query?symbol=XBTUSDTM&granularity=60&from=1731024000000&to=1731196800000"),
        get_json("kucoin_futures_klines_recent",
                 "https://api-futures.kucoin.com/api/v1/kline/query?symbol=XBTUSDTM&granularity=60&from=1794096000000&to=1794268800000"),
        get_json("kucoin_funding_2y",
                 "https://api-futures.kucoin.com/api/v1/contract/funding-rates?symbol=XBTUSDTM&from=1731024000000&to=1794268800000"),
        get_json("kucoin_open_interest_2y_daily",
                 "https://api.kucoin.com/api/ua/v1/market/open-interest?symbol=XBTUSDTM&interval=1day&startAt=1731024000000&endAt=1794268800000&pageSize=1000"),
    ]
    by_name = {x["name"]: x for x in results}
    for symbol in ["ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "PEPEUSDT",
                   "NEARUSDT", "WLDUSDT", "BCHUSDT", "UNIUSDT", "AAVEUSDT"]:
        results.append(archive_kline(f"binance_vision_spot_{symbol}_2026_10", "spot", "2026-10", symbol))
        results.append(archive_kline(f"binance_vision_futures_{symbol}_2026_10", "futures_um", "2026-10", symbol))
    by_name = {x["name"]: x for x in results}
    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        spot = by_name.get("binance_vision_spot_1h_2026_10" if symbol == "BTCUSDT" else f"binance_vision_spot_{symbol}_2026_10", {})
        fut = by_name.get("binance_vision_um_futures_1h_2026_10" if symbol == "BTCUSDT" else f"binance_vision_futures_{symbol}_2026_10", {})
        spot_closes = spot.get("close_by_open_time", {})
        futures_closes = fut.get("close_by_open_time", {})
        common_times = sorted(set(spot_closes) & set(futures_closes))
        if common_times:
            matched_time = common_times[-1]
            spot_close = float(spot_closes[matched_time])
            futures_close = float(futures_closes[matched_time])
            basis = (futures_close - spot_close) / spot_close
            results.append({"name": f"binance_vision_basis_{symbol}", "matched_open_time_utc": matched_time,
                            "spot_close": spot_close, "futures_close": futures_close,
                            "basis_fraction": basis, "basis_percent": basis * 100,
                            "spot_month": "2026-10", "futures_month": "2026-10",
                            "note": "Spot and futures closes matched by identical 1h candle open timestamp."})
    for item in results:
        item.pop("close_by_open_time", None)
    report = {"audit_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "runner": "GitHub Actions ubuntu-latest", "credentials_used": False,
              "scope": "public read-only endpoints and Binance Vision archive HEAD/GET",
              "results": results}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
