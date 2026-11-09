"""دریافت تاریخچهٔ ۱۵ دقیقه‌ای Binance Vision برای ۲۷ نماد ثابت."""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = "https://data.binance.vision"
INTERVAL = "15m"
INTERVAL_MS = 900_000
RETRYABLE = {500, 502, 503, 504}


class ArchiveError(RuntimeError):
    pass


def request_bytes(url: str, method: str = "GET", attempts: int = 3) -> tuple[int, bytes]:
    last_error = "UNKNOWN"
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": "Trade-LRT15m/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.status, response.read() if method == "GET" else b""
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE:
                return exc.code, b""
            last_error = f"HTTP_{exc.code}"
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError,)) or isinstance(exc, TimeoutError):
                last_error = "TIMEOUT"
            else:
                raise ArchiveError(f"NETWORK_ERROR:{reason}") from exc
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    raise ArchiveError(f"RETRIES_EXHAUSTED:{last_error}")


def head_get(url: str) -> tuple[bytes | None, str]:
    status, _ = request_bytes(url, "HEAD")
    if status == 404:
        return None, "404"
    if status in (405, 501):
        pass
    elif status != 200:
        return None, f"HEAD_{status}"
    status, payload = request_bytes(url, "GET")
    if status == 404:
        return None, "404"
    if status != 200:
        return None, f"GET_{status}"
    return payload, "200"


def parse_zip(payload: bytes, start_ms: int, end_ms: int) -> dict[int, dict[str, float]]:
    output: dict[int, dict[str, float]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = next((n for n in archive.namelist() if n.lower().endswith(".csv")), None)
        if not csv_name:
            raise ArchiveError("ZIP_WITHOUT_CSV")
        with archive.open(csv_name) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                if len(row) < 11 or not row[0].isdigit():
                    continue
                ts = int(row[0])
                if start_ms <= ts < end_ms:
                    output[ts] = {
                        "open": float(row[1]), "high": float(row[2]),
                        "low": float(row[3]), "close": float(row[4]),
                        "volume": float(row[5]), "quote_volume": float(row[7]),
                        "trades": float(row[8]), "taker_buy_base": float(row[9]),
                        "taker_buy_quote": float(row[10]),
                    }
    return output


def aggregate_1m_to_15m(one: dict[int, dict[str, float]],
                           existing: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """فقط 15 کندل 1m پیوسته را به یک کندل 15m تبدیل می‌کند."""
    grouped: dict[int, list[tuple[int, dict[str, float]]]] = {}
    for ts, row in one.items():
        bucket = (ts // INTERVAL_MS) * INTERVAL_MS
        grouped.setdefault(bucket, []).append((ts, row))
    output: dict[int, dict[str, Any]] = {}
    for bucket, rows in grouped.items():
        rows.sort(key=lambda item: item[0])
        expected = list(range(bucket, bucket + INTERVAL_MS, 60_000))
        if [item[0] for item in rows] != expected or bucket in existing:
            continue
        values = [item[1] for item in rows]
        output[bucket] = {
            "open": values[0]["open"],
            "high": max(x["high"] for x in values),
            "low": min(x["low"] for x in values),
            "close": values[-1]["close"],
            "volume": sum(x["volume"] for x in values),
            "quote_volume": sum(x["quote_volume"] for x in values),
            "trades": sum(x["trades"] for x in values),
            "taker_buy_base": sum(x["taker_buy_base"] for x in values),
            "taker_buy_quote": sum(x["taker_buy_quote"] for x in values),
            "data_source": "BINANCE_VISION_1M_AGGREGATED",
            "cvd_source": "BINANCE_1M_TAKER_BUY_AGGREGATED",
        }
    return output


def parse_aggtrades_zip(payload: bytes, start_ms: int, end_ms: int) -> dict[int, dict[str, float]]:
    """بازسازی کندل 15m از معاملات تجمیعی واقعی Binance Vision."""
    grouped: dict[int, dict[str, float]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = next((n for n in archive.namelist() if n.lower().endswith(".csv")), None)
        if not csv_name:
            raise ArchiveError("AGGTRADES_ZIP_WITHOUT_CSV")
        with archive.open(csv_name) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                if len(row) < 7 or not row[5].isdigit():
                    continue
                ts = int(row[5])
                if not start_ms <= ts < end_ms:
                    continue
                price, qty = float(row[1]), float(row[2])
                bucket = (ts // INTERVAL_MS) * INTERVAL_MS
                quote_qty = price * qty
                buyer_is_maker = row[6].strip().lower() == "true"
                if bucket not in grouped:
                    grouped[bucket] = {
                        "open": price, "high": price, "low": price, "close": price,
                        "volume": 0.0, "quote_volume": 0.0, "trades": 0.0,
                        "taker_buy_base": 0.0, "taker_buy_quote": 0.0,
                        "_first_ts": float(ts),
                    }
                bar = grouped[bucket]
                if ts < bar["_first_ts"]:
                    bar["open"] = price
                    bar["_first_ts"] = float(ts)
                bar["high"] = max(bar["high"], price)
                bar["low"] = min(bar["low"], price)
                if ts >= bar.get("_last_ts", -1):
                    bar["close"] = price
                    bar["_last_ts"] = float(ts)
                bar["volume"] += qty
                bar["quote_volume"] += quote_qty
                bar["trades"] += 1.0
                if not buyer_is_maker:
                    bar["taker_buy_base"] += qty
                    bar["taker_buy_quote"] += quote_qty
    for bar in grouped.values():
        bar.pop("_first_ts", None)
        bar.pop("_last_ts", None)
    return grouped


def parse_okx_pepe_spot_as_1000pepe(payload: bytes, start_ms: int,
                                           end_ms: int) -> dict[int, dict[str, Any]]:
    """تبدیل PEPE-USDT Spot به مقیاس قرارداد 1000PEPE؛ صریحاً Proxy است."""
    raw = json.loads(payload.decode("utf-8"))
    if not isinstance(raw, dict) or raw.get("code") != "0":
        raise ArchiveError(f"OKX_SPOT_PEPE_ERROR:{str(raw)[:200]}")
    output: dict[int, dict[str, Any]] = {}
    for row in raw.get("data", []):
        if len(row) < 9:
            continue
        ts = int(row[0])
        if not start_ms <= ts < end_ms or row[8] != "1":
            continue
        base_volume = float(row[5])
        quote_volume = float(row[7])
        scaled_volume = base_volume / 1000.0
        output[ts] = {
            "open": float(row[1]) * 1000.0,
            "high": float(row[2]) * 1000.0,
            "low": float(row[3]) * 1000.0,
            "close": float(row[4]) * 1000.0,
            "volume": scaled_volume, "quote_volume": quote_volume,
            "trades": 0.0, "taker_buy_base": scaled_volume * 0.5,
            "taker_buy_quote": quote_volume * 0.5,
            "data_source": "OKX_SPOT_PEPE_SCALED_1000PEPE_PROXY",
            "cvd_source": "OKX_SPOT_CVD_UNAVAILABLE_NEUTRAL_PROXY",
        }
    return output


def fetch_okx_pepe_spot_as_1000pepe(symbol: str, start_ms: int,
                                    end_ms: int) -> tuple[dict[int, dict[str, Any]], str]:
    if symbol != "1000PEPEUSDT":
        return {}, "NOT_APPLICABLE"
    query = urllib.parse.urlencode({
        "instId": "PEPE-USDT", "bar": "15m", "after": end_ms, "limit": 100,
    })
    url = f"https://www.okx.com/api/v5/market/history-candles?{query}"
    status, payload = request_bytes(url, "GET")
    if status != 200:
        return {}, f"HTTP_{status}"
    rows = parse_okx_pepe_spot_as_1000pepe(payload, start_ms, end_ms)
    return rows, "200" if rows else "NO_MATCHING_CANDLES"


def parse_mexc_futures_klines(payload: bytes, detail_payload: bytes,
                                start_ms: int, end_ms: int,
                                contract_symbol: str) -> dict[int, dict[str, Any]]:
    """تبدیل کندل Futures عمومی MEXC با ضریب قرارداد واقعی."""
    detail = json.loads(detail_payload.decode("utf-8"))
    if not detail.get("success") or detail.get("code") != 0:
        raise ArchiveError(f"MEXC_DETAIL_ERROR:{str(detail)[:200]}")
    contract = next((x for x in detail.get("data", [])
                     if x.get("symbol") == contract_symbol), None)
    if contract is None:
        raise ArchiveError(f"MEXC_CONTRACT_NOT_LISTED:{contract_symbol}")
    contract_size = float(contract.get("contractSize", 0))
    if contract_size <= 0:
        raise ArchiveError(f"MEXC_INVALID_CONTRACT_SIZE:{contract_symbol}")
    raw = json.loads(payload.decode("utf-8"))
    if not raw.get("success") or raw.get("code") != 0:
        raise ArchiveError(f"MEXC_KLINE_ERROR:{str(raw)[:200]}")
    data = raw.get("data") or {}
    output: dict[int, dict[str, Any]] = {}
    keys = ("time", "open", "close", "high", "low", "vol", "amount")
    if any(key not in data for key in keys):
        raise ArchiveError("MEXC_KLINE_FIELDS_MISSING")
    for values in zip(*(data[key] for key in keys)):
        ts = int(values[0]) * 1000
        if not start_ms <= ts < end_ms:
            continue
        base_volume = float(values[5]) * contract_size
        quote_volume = float(values[6])
        output[ts] = {
            "open": float(values[1]), "high": float(values[3]),
            "low": float(values[4]), "close": float(values[2]),
            "volume": base_volume, "quote_volume": quote_volume,
            "trades": 0.0, "taker_buy_base": base_volume * 0.5,
            "taker_buy_quote": quote_volume * 0.5,
            "data_source": "MEXC_FUTURES_15M",
            "cvd_source": "MEXC_CVD_UNAVAILABLE_NEUTRAL_PROXY",
        }
    return output


def fetch_mexc_futures_15m(symbol: str, start_ms: int, end_ms: int) -> tuple[dict[int, dict[str, Any]], str]:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    contract_symbol = f"{base}_USDT"
    detail_url = "https://contract.mexc.com/api/v1/contract/detail"
    detail_status, detail_payload = request_bytes(detail_url, "GET")
    if detail_status != 200:
        return {}, f"DETAIL_HTTP_{detail_status}"
    query = urllib.parse.urlencode({
        "interval": "Min15", "start": start_ms // 1000, "end": end_ms // 1000,
    })
    url = f"https://contract.mexc.com/api/v1/contract/kline/{contract_symbol}?{query}"
    status, payload = request_bytes(url, "GET")
    if status != 200:
        return {}, f"KLINE_HTTP_{status}"
    rows = parse_mexc_futures_klines(payload, detail_payload, start_ms, end_ms, contract_symbol)
    return rows, "200" if rows else "NO_MATCHING_CANDLES"


def parse_bybit_klines(payload: bytes, start_ms: int, end_ms: int,
                       category: str) -> dict[int, dict[str, Any]]:
    """تبدیل کندل عمومی Bybit؛ نبود دادهٔ taker-buy با Proxy خنثی ثبت می‌شود."""
    raw = json.loads(payload.decode("utf-8"))
    if not isinstance(raw, dict) or raw.get("retCode") != 0:
        raise ArchiveError(f"BYBIT_API_ERROR:{str(raw)[:200]}")
    output: dict[int, dict[str, Any]] = {}
    for row in raw.get("result", {}).get("list", []):
        if len(row) < 7:
            continue
        ts = int(row[0])
        if not start_ms <= ts < end_ms:
            continue
        volume, turnover = float(row[5]), float(row[6])
        output[ts] = {
            "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]),
            "volume": volume, "quote_volume": turnover,
            "trades": 0.0, "taker_buy_base": volume * 0.5,
            "taker_buy_quote": turnover * 0.5,
            "data_source": f"BYBIT_{category.upper()}_15M",
            "cvd_source": "BYBIT_CVD_UNAVAILABLE_NEUTRAL_PROXY",
        }
    return output


def fetch_bybit_15m(symbol: str, start_ms: int, end_ms: int,
                    category: str) -> tuple[dict[int, dict[str, Any]], str]:
    query = urllib.parse.urlencode({
        "category": category, "symbol": symbol, "interval": "15",
        "start": start_ms, "end": end_ms - 1, "limit": 200,
    })
    url = f"https://api.bybit.com/v5/market/kline?{query}"
    status, payload = request_bytes(url, "GET")
    if status != 200:
        return {}, f"HTTP_{status}"
    rows = parse_bybit_klines(payload, start_ms, end_ms, category)
    return rows, "200" if rows else "NO_MATCHING_CANDLES"


def parse_okx_history_candles(payload: bytes, start_ms: int, end_ms: int) -> dict[int, dict[str, Any]]:
    """تبدیل کندل‌های عمومی قرارداد دائمی OKX؛ CVD به‌صراحت خنثی و Proxy است."""
    raw = json.loads(payload.decode("utf-8"))
    if not isinstance(raw, dict) or raw.get("code") != "0":
        raise ArchiveError(f"OKX_API_ERROR:{str(raw)[:200]}")
    output: dict[int, dict[str, Any]] = {}
    for row in raw.get("data", []):
        if len(row) < 9:
            continue
        ts = int(row[0])
        if not start_ms <= ts < end_ms or row[8] != "1":
            continue
        base_volume = float(row[6])
        quote_volume = float(row[7])
        output[ts] = {
            "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]),
            "volume": base_volume, "quote_volume": quote_volume,
            "trades": 0.0,
            # OKX candles do not expose taker-buy volume: neutral proxy only.
            "taker_buy_base": base_volume * 0.5,
            "taker_buy_quote": quote_volume * 0.5,
            "data_source": "OKX_PUBLIC_SWAP_CANDLE",
            "cvd_source": "OKX_CVD_UNAVAILABLE_NEUTRAL_PROXY",
        }
    return output


def fetch_okx_history_15m(symbol: str, start_ms: int, end_ms: int) -> tuple[dict[int, dict[str, Any]], str]:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    # Avoid silently mapping leveraged-denomination symbols to a differently scaled contract.
    if base.startswith("1000"):
        return {}, "UNSUPPORTED_CONTRACT_MULTIPLIER"
    inst_id = f"{base}-USDT-SWAP"
    query = urllib.parse.urlencode({
        "instId": inst_id, "bar": "15m", "after": end_ms, "limit": 100,
    })
    url = f"https://www.okx.com/api/v5/market/history-candles?{query}"
    status, payload = request_bytes(url, "GET")
    if status != 200:
        return {}, f"HTTP_{status}"
    rows = parse_okx_history_candles(payload, start_ms, end_ms)
    return rows, "200" if rows else "NO_MATCHING_CANDLES"


def parse_binance_rest_klines(payload: bytes, start_ms: int, end_ms: int) -> dict[int, dict[str, float]]:
    """تبدیل کندل‌های عمومی Futures REST به ساختار یکسان Parquet."""
    raw = json.loads(payload.decode("utf-8"))
    if not isinstance(raw, list):
        raise ArchiveError(f"BINANCE_REST_UNEXPECTED_RESPONSE:{str(raw)[:200]}")
    output: dict[int, dict[str, float]] = {}
    for row in raw:
        if not isinstance(row, list) or len(row) < 11:
            continue
        ts = int(row[0])
        if start_ms <= ts < end_ms:
            output[ts] = {
                "open": float(row[1]), "high": float(row[2]),
                "low": float(row[3]), "close": float(row[4]),
                "volume": float(row[5]), "quote_volume": float(row[7]),
                "trades": float(row[8]), "taker_buy_base": float(row[9]),
                "taker_buy_quote": float(row[10]),
            }
    return output


def fetch_binance_rest_15m(symbol: str, start_ms: int, end_ms: int) -> tuple[dict[int, dict[str, float]], str]:
    query = urllib.parse.urlencode({
        "symbol": symbol, "interval": "15m",
        "startTime": start_ms, "endTime": end_ms - 1, "limit": 1000,
    })
    url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
    status, payload = request_bytes(url, "GET")
    if status != 200:
        return {}, f"HTTP_{status}"
    return parse_binance_rest_klines(payload, start_ms, end_ms), "200"


def months_between(start: date, end: date):
    current = date(start.year, start.month, 1)
    stop = date(end.year, end.month, 1)
    while current < stop:
        yield current
        current = date(current.year + (current.month == 12),
                       1 if current.month == 12 else current.month + 1, 1)


def days_between(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def month_end(month: date) -> date:
    return date(month.year + (month.month == 12),
                1 if month.month == 12 else month.month + 1, 1)


def build_parquet_records(bars: dict[int, dict[str, Any]],
                           timestamps: list[int]) -> list[dict[str, Any]]:
    """متادیتای منبع را برای تمام ردیف‌ها نگه می‌دارد تا schema حذفش نکند."""
    records = []
    for ts in timestamps:
        bar = bars[ts]
        records.append({
            "open_time": ts,
            "data_source": bar.get("data_source", "BINANCE_VISION_KLINES"),
            "cvd_source": bar.get("cvd_source", "BINANCE_KLINE_TAKER_BUY_PROXY"),
            **bar,
        })
    return records


async def download_symbol(symbol: str, start: date, end: date,
                          outdir: Path, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    start_ms = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end, datetime.min.time(), timezone.utc).timestamp() * 1000)
    bars: dict[int, dict[str, float]] = {}
    events: list[dict[str, str]] = []
    async with semaphore:
        for month in months_between(start, end):
            stop = min(month_end(month), end)
            first = max(month, start)
            is_complete_month = first == month and stop == month_end(month)
            if is_complete_month:
                name = f"{symbol}-{INTERVAL}-{month:%Y-%m}.zip"
                url = f"{BASE}/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{name}"
                try:
                    payload, status = await asyncio.to_thread(head_get, url)
                    if payload is not None:
                        bars.update(parse_zip(payload, start_ms, end_ms))
                        events.append({"archive": name, "status": "MONTHLY_OK"})
                        continue
                    events.append({"archive": name, "status": f"MONTHLY_{status}"})
                except Exception as exc:
                    events.append({"archive": name, "status": f"MONTHLY_ERROR:{type(exc).__name__}:{exc}"})
            # Fallback daily: missing monthly archive or partial current month.
            for day in days_between(first, stop):
                name = f"{symbol}-{INTERVAL}-{day:%Y-%m-%d}.zip"
                url = f"{BASE}/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{name}"
                try:
                    payload, status = await asyncio.to_thread(head_get, url)
                    if payload is None:
                        events.append({"archive": name, "status": f"DAILY_{status}"})
                        continue
                    bars.update(parse_zip(payload, start_ms, end_ms))
                    events.append({"archive": name, "status": "DAILY_OK"})
                except Exception as exc:
                    events.append({"archive": name, "status": f"DAILY_ERROR:{type(exc).__name__}:{exc}"})

    # ماه انتهایی در months_between عمداً وارد نمی‌شود؛ daily آرشیو آن را جداگانه می‌گیریم.
    if end.day > 1:
        partial_month_start = max(date(end.year, end.month, 1), start)
        for day in days_between(partial_month_start, end):
            name = f"{symbol}-{INTERVAL}-{day:%Y-%m-%d}.zip"
            url = f"{BASE}/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{name}"
            try:
                payload, status = await asyncio.to_thread(head_get, url)
                if payload is None:
                    events.append({"archive": name, "status": f"DAILY_{status}"})
                    continue
                bars.update(parse_zip(payload, start_ms, end_ms))
                events.append({"archive": name, "status": "DAILY_OK"})
            except Exception as exc:
                events.append({"archive": name, "status": f"DAILY_ERROR:{type(exc).__name__}:{exc}"})

    # ترمیم روزهای ناقص حتی اگر آرشیو ماهانه با HTTP 200 دریافت شده باشد.
    expected_timestamps = range(start_ms, end_ms, INTERVAL_MS)
    missing_before_repair = [ts for ts in expected_timestamps if ts not in bars]
    missing_days = sorted({datetime.fromtimestamp(ts / 1000, timezone.utc).date()
                           for ts in missing_before_repair})
    for day in missing_days:
        day_start = max(start_ms, int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp() * 1000))
        day_end = min(end_ms, day_start + 86_400_000)
        name = f"{symbol}-{INTERVAL}-{day:%Y-%m-%d}.zip"
        url = f"{BASE}/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{name}"
        try:
            payload, status = await asyncio.to_thread(head_get, url)
            if payload is not None:
                repaired = parse_zip(payload, day_start, day_end)
                added = sum(1 for ts, row in repaired.items() if ts not in bars)
                bars.update(repaired)
                events.append({"archive": name, "status": "GAP_REPAIR_15M_OK",
                               "rows_in_archive": str(len(repaired)), "rows_added": str(added)})
            else:
                events.append({"archive": name, "status": f"GAP_REPAIR_15M_{status}",
                               "rows_in_archive": "0", "rows_added": "0"})
        except Exception as exc:
            events.append({"archive": name, "status": f"GAP_REPAIR_15M_ERROR:{type(exc).__name__}:{exc}",
                           "rows_in_archive": "0", "rows_added": "0"})

        # اگر آرشیو Vision ناقص بود، از API عمومی Futures REST با دادهٔ کامل OHLCV و taker-buy استفاده کن.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            try:
                rest_bars, rest_status = await asyncio.to_thread(
                    fetch_binance_rest_15m, symbol, day_start, day_end
                )
                added_rest = sum(1 for ts in rest_bars if ts not in bars)
                bars.update(rest_bars)
                events.append({"archive": f"BINANCE_FAPI_REST_{day:%Y-%m-%d}",
                               "status": "GAP_REPAIR_BINANCE_REST_OK" if rest_bars else f"GAP_REPAIR_BINANCE_REST_{rest_status}",
                               "rows_in_archive": str(len(rest_bars)), "rows_added": str(added_rest)})
            except Exception as exc:
                events.append({"archive": f"BINANCE_FAPI_REST_{day:%Y-%m-%d}",
                               "status": f"GAP_REPAIR_BINANCE_REST_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # مسیر دوم: بازسازی کندل از آرشیو معاملات تجمیعی واقعی، بدون حدس‌زدن OHLCV.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            agg_name = f"{symbol}-aggTrades-{day:%Y-%m-%d}.zip"
            agg_url = f"{BASE}/data/futures/um/daily/aggTrades/{symbol}/{agg_name}"
            try:
                agg_payload, agg_status = await asyncio.to_thread(head_get, agg_url)
                if agg_payload is not None:
                    rebuilt = parse_aggtrades_zip(agg_payload, day_start, day_end)
                    added_agg = sum(1 for ts in rebuilt if ts not in bars)
                    bars.update(rebuilt)
                    events.append({"archive": agg_name, "status": "GAP_REPAIR_AGGTRADES_OK",
                                   "rows_in_archive": str(len(rebuilt)), "rows_added": str(added_agg)})
                else:
                    events.append({"archive": agg_name, "status": f"GAP_REPAIR_AGGTRADES_{agg_status}",
                                   "rows_in_archive": "0", "rows_added": "0"})
            except Exception as exc:
                events.append({"archive": agg_name, "status": f"GAP_REPAIR_AGGTRADES_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # مسیر سوم: کندل عمومی قرارداد دائمی OKX؛ منبع و محدودیت CVD جداگانه ثبت می‌شود.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            try:
                okx_bars, okx_status = await asyncio.to_thread(
                    fetch_okx_history_15m, symbol, day_start, day_end
                )
                added_okx = sum(1 for ts in okx_bars if ts not in bars)
                bars.update(okx_bars)
                events.append({"archive": f"OKX_SWAP_15M_{day:%Y-%m-%d}",
                               "status": "GAP_REPAIR_OKX_REST_OK" if okx_bars else f"GAP_REPAIR_OKX_REST_{okx_status}",
                               "rows_in_archive": str(len(okx_bars)), "rows_added": str(added_okx)})
            except Exception as exc:
                events.append({"archive": f"OKX_SWAP_15M_{day:%Y-%m-%d}",
                               "status": f"GAP_REPAIR_OKX_REST_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # اگر منابع دیگر کافی نبودند، سه کندل 5m را به یک کندل 15m تبدیل کن.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            name5 = f"{symbol}-5m-{day:%Y-%m-%d}.zip"
            url5 = f"{BASE}/data/futures/um/daily/klines/{symbol}/5m/{name5}"
            try:
                payload5, status5 = await asyncio.to_thread(head_get, url5)
                if payload5 is None:
                    events.append({"archive": name5, "status": f"GAP_REPAIR_5M_{status5}",
                                   "rows_in_archive": "0", "rows_added": "0"})
                else:
                    five = parse_zip(payload5, day_start, day_end)
                    grouped: dict[int, list[tuple[int, dict[str, float]]]] = {}
                    for ts5, row5 in five.items():
                        bucket = (ts5 // INTERVAL_MS) * INTERVAL_MS
                        grouped.setdefault(bucket, []).append((ts5, row5))
                    added5 = 0
                    for bucket, rows in grouped.items():
                        rows.sort(key=lambda item: item[0])
                        expected_5m = [bucket, bucket + 300_000, bucket + 600_000]
                        if [item[0] for item in rows] != expected_5m or bucket in bars:
                            continue
                        values = [item[1] for item in rows]
                        bars[bucket] = {
                            "open": values[0]["open"],
                            "high": max(x["high"] for x in values),
                            "low": min(x["low"] for x in values),
                            "close": values[-1]["close"],
                            "volume": sum(x["volume"] for x in values),
                            "quote_volume": sum(x["quote_volume"] for x in values),
                            "trades": sum(x["trades"] for x in values),
                            "taker_buy_base": sum(x["taker_buy_base"] for x in values),
                            "taker_buy_quote": sum(x["taker_buy_quote"] for x in values),
                        }
                        added5 += 1
                    events.append({"archive": name5, "status": "GAP_REPAIR_5M_AGGREGATED",
                                   "rows_in_archive": str(len(five)), "rows_added": str(added5)})
            except Exception as exc:
                events.append({"archive": name5, "status": f"GAP_REPAIR_5M_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # مسیر نهایی در همان منبع: تجمیع 15 کندل 1m معتبر به یک کندل 15m.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            name1 = f"{symbol}-1m-{day:%Y-%m-%d}.zip"
            url1 = f"{BASE}/data/futures/um/daily/klines/{symbol}/1m/{name1}"
            try:
                payload1, status1 = await asyncio.to_thread(head_get, url1)
                if payload1 is None:
                    events.append({"archive": name1, "status": f"GAP_REPAIR_1M_{status1}",
                                   "rows_in_archive": "0", "rows_added": "0"})
                else:
                    one = parse_zip(payload1, day_start, day_end)
                    rebuilt_1m = aggregate_1m_to_15m(one, bars)
                    added1 = len(rebuilt_1m)
                    bars.update(rebuilt_1m)
                    events.append({"archive": name1, "status": "GAP_REPAIR_1M_AGGREGATED",
                                   "rows_in_archive": str(len(one)), "rows_added": str(added1)})
            except Exception as exc:
                events.append({"archive": name1, "status": f"GAP_REPAIR_1M_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # مسیر چندصرافی آخر: Bybit Linear؛ در صورت نبود قرارداد، Spot با برچسب Proxy.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            categories = ["linear", "spot"] if not symbol.startswith("1000") else ["linear"]
            for category in categories:
                try:
                    bybit_bars, bybit_status = await asyncio.to_thread(
                        fetch_bybit_15m, symbol, day_start, day_end, category
                    )
                    added_bybit = sum(1 for ts in bybit_bars if ts not in bars)
                    bars.update(bybit_bars)
                    events.append({"archive": f"BYBIT_{category.upper()}_15M_{day:%Y-%m-%d}",
                                   "status": f"GAP_REPAIR_BYBIT_{category.upper()}_OK" if bybit_bars else f"GAP_REPAIR_BYBIT_{category.upper()}_{bybit_status}",
                                   "rows_in_archive": str(len(bybit_bars)), "rows_added": str(added_bybit)})
                    if not [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]:
                        break
                except Exception as exc:
                    events.append({"archive": f"BYBIT_{category.upper()}_15M_{day:%Y-%m-%d}",
                                   "status": f"GAP_REPAIR_BYBIT_{category.upper()}_ERROR:{type(exc).__name__}:{exc}",
                                   "rows_in_archive": "0", "rows_added": "0"})

        # آخرین منبع مستقل: MEXC Futures عمومی، فقط با ضریب قرارداد تأییدشده.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing:
            try:
                mexc_bars, mexc_status = await asyncio.to_thread(
                    fetch_mexc_futures_15m, symbol, day_start, day_end
                )
                added_mexc = sum(1 for ts in mexc_bars if ts not in bars)
                bars.update(mexc_bars)
                events.append({"archive": f"MEXC_FUTURES_15M_{day:%Y-%m-%d}",
                               "status": "GAP_REPAIR_MEXC_FUTURES_OK" if mexc_bars else f"GAP_REPAIR_MEXC_FUTURES_{mexc_status}",
                               "rows_in_archive": str(len(mexc_bars)), "rows_added": str(added_mexc)})
            except Exception as exc:
                events.append({"archive": f"MEXC_FUTURES_15M_{day:%Y-%m-%d}",
                               "status": f"GAP_REPAIR_MEXC_FUTURES_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

        # Proxy محدود برای 1000PEPE: PEPE Spot با تبدیل مقیاس ×1000 و ثبت منبع.
        day_missing = [ts for ts in range(day_start, day_end, INTERVAL_MS) if ts not in bars]
        if day_missing and symbol == "1000PEPEUSDT":
            try:
                scaled_bars, scaled_status = await asyncio.to_thread(
                    fetch_okx_pepe_spot_as_1000pepe, symbol, day_start, day_end
                )
                added_scaled = sum(1 for ts in scaled_bars if ts not in bars)
                bars.update(scaled_bars)
                events.append({"archive": f"OKX_SPOT_PEPE_SCALED_1000PEPE_{day:%Y-%m-%d}",
                               "status": "GAP_REPAIR_OKX_SPOT_1000PEPE_PROXY_OK" if scaled_bars else f"GAP_REPAIR_OKX_SPOT_1000PEPE_PROXY_{scaled_status}",
                               "rows_in_archive": str(len(scaled_bars)), "rows_added": str(added_scaled)})
            except Exception as exc:
                events.append({"archive": f"OKX_SPOT_PEPE_SCALED_1000PEPE_{day:%Y-%m-%d}",
                               "status": f"GAP_REPAIR_OKX_SPOT_1000PEPE_PROXY_ERROR:{type(exc).__name__}:{exc}",
                               "rows_in_archive": "0", "rows_added": "0"})

    timestamps = sorted(bars)
    expected = (end_ms - start_ms) // INTERVAL_MS
    missing_after_repair = [ts for ts in range(start_ms, end_ms, INTERVAL_MS) if ts not in bars]
    missing_ranges: list[dict[str, Any]] = []
    if missing_after_repair:
        range_start = previous = missing_after_repair[0]
        count = 1
        for ts in missing_after_repair[1:]:
            if ts == previous + INTERVAL_MS:
                count += 1
            else:
                missing_ranges.append({
                    "start_utc": datetime.fromtimestamp(range_start / 1000, timezone.utc).isoformat(),
                    "end_exclusive_utc": datetime.fromtimestamp((previous + INTERVAL_MS) / 1000, timezone.utc).isoformat(),
                    "missing_bars": count,
                })
                range_start, count = ts, 1
            previous = ts
        missing_ranges.append({
            "start_utc": datetime.fromtimestamp(range_start / 1000, timezone.utc).isoformat(),
            "end_exclusive_utc": datetime.fromtimestamp((previous + INTERVAL_MS) / 1000, timezone.utc).isoformat(),
            "missing_bars": count,
        })
    gaps = sum(1 for a, b in zip(timestamps, timestamps[1:]) if b - a != INTERVAL_MS)
    complete = len(timestamps) == expected and gaps == 0
    output_file = None
    if timestamps:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            records = build_parquet_records(bars, timestamps)
            table = pa.Table.from_pylist(records)
            outdir.mkdir(parents=True, exist_ok=True)
            target = outdir / f"{symbol}_15m_{start}_{end}.parquet"
            pq.write_table(table, target, compression="zstd", version="2.6")
            output_file = str(target)
        except Exception as exc:
            raise ArchiveError(f"PARQUET_WRITE_FAILED:{symbol}:{exc}") from exc
    return {
        "symbol": symbol, "rows": len(timestamps), "expected_rows": expected,
        "gap_count": gaps, "continuity": complete,
        "missing_ranges": missing_ranges,
        "first_open_ms": timestamps[0] if timestamps else None,
        "last_open_ms": timestamps[-1] if timestamps else None,
        "file": output_file, "archive_events": events,
    }


async def run(start: date, end: date, outdir: Path, report_path: Path,
              universe_path: Path) -> dict[str, Any]:
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; got {len(symbols)}")
    if (end - start).days != 730:
        raise ValueError("Stage 1b history window must be exactly 730 days")
    semaphore = asyncio.Semaphore(5)
    tasks = [asyncio.create_task(download_symbol(s, start, end, outdir, semaphore)) for s in symbols]
    results = []
    for index, task in enumerate(asyncio.as_completed(tasks), 1):
        try:
            result = await task
        except Exception as exc:
            result = {"symbol": "TASK_ERROR", "continuity": False,
                      "rows": 0, "reason": f"{type(exc).__name__}:{exc}"}
        results.append(result)
        print(f"15M_PROGRESS {index}/27 complete={sum(x.get('continuity') is True for x in results)}", flush=True)
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "universe_as_of_utc": universe.get("as_of_utc"),
            "start_date_utc": start.isoformat(), "end_date_exclusive_utc": end.isoformat(),
            "interval": INTERVAL, "universe_count": 27,
            "symbols_complete": sum(x.get("continuity") is True for x in results),
            "symbols_processed": len(results), "symbols": results,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    complete_count = sum(x.get("continuity") is True for x in results)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_as_of_utc": universe.get("as_of_utc"),
        "start_date_utc": start.isoformat(), "end_date_exclusive_utc": end.isoformat(),
        "interval": INTERVAL, "universe_count": 27,
        "symbols_complete": complete_count, "symbols_processed": len(results),
        "status": "PASS" if complete_count == 27 else "FAIL",
        "symbols": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STAGE1B_15M_DATA " + json.dumps({
        "complete": complete_count, "universe": 27, "status": report["status"]
    }), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--universe", default="signal_autopilot/data/stage1b_universe_27.json")
    args = parser.parse_args()
    report = asyncio.run(run(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date),
                             Path(args.output_dir), Path(args.report), Path(args.universe)))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
