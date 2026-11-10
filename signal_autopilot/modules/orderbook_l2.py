"""Public L2 order-book sampling adapters; no private/account authentication."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import websockets

SYMBOLS: dict[str, dict[str, str]] = {
    "BTC": {"okx": "BTC-USDT-SWAP", "bybit": "BTCUSDT", "kucoin": "XBTUSDTM"},
    "ETH": {"okx": "ETH-USDT-SWAP", "bybit": "ETHUSDT", "kucoin": "ETHUSDTM"},
    "SOL": {"okx": "SOL-USDT-SWAP", "bybit": "SOLUSDT", "kucoin": "SOLUSDTM"},
    "XRP": {"okx": "XRP-USDT-SWAP", "bybit": "XRPUSDT", "kucoin": "XRPUSDTM"},
    "DOGE": {"okx": "DOGE-USDT-SWAP", "bybit": "DOGEUSDT", "kucoin": "DOGEUSDTM"},
    "ADA": {"okx": "ADA-USDT-SWAP", "bybit": "ADAUSDT", "kucoin": "ADAUSDTM"},
    "LINK": {"okx": "LINK-USDT-SWAP", "bybit": "LINKUSDT", "kucoin": "LINKUSDTM"},
    "LTC": {"okx": "LTC-USDT-SWAP", "bybit": "LTCUSDT", "kucoin": "LTCUSDTM"},
    "BCH": {"okx": "BCH-USDT-SWAP", "bybit": "BCHUSDT", "kucoin": "BCHUSDTM"},
    "AVAX": {"okx": "AVAX-USDT-SWAP", "bybit": "AVAXUSDT", "kucoin": "AVAXUSDTM"},
}


def _levels(items: list[list[Any]], depth: int = 50) -> list[list[str]]:
    output = []
    for item in items[:depth]:
        if len(item) < 2:
            continue
        try:
            price, size = float(item[0]), float(item[1])
        except (TypeError, ValueError):
            continue
        if price > 0 and size > 0:
            output.append([str(item[0]), str(item[1])])
    return output


def apply_bybit_update(book: dict[str, Any], message: dict[str, Any]) -> bool:
    """Snapshot replaces local state; delta inserts, updates, or deletes price levels."""
    kind, data = message.get("type"), message.get("data") or {}
    update_id = data.get("u")
    if kind == "snapshot" or update_id == 1:
        book["bids"], book["asks"], book["has_snapshot"] = {}, {}, True
    elif kind != "delta" or not book.get("has_snapshot"):
        return False
    for side, key in (("b", "bids"), ("a", "asks")):
        levels = book.setdefault(key, {})
        for item in data.get(side, []) or []:
            if len(item) < 2:
                continue
            try:
                price, size = str(item[0]), float(item[1])
            except (TypeError, ValueError):
                continue
            if size == 0:
                levels.pop(price, None)
            elif size > 0:
                levels[price] = str(item[1])
    book["exchange_ts_ms"] = int(message.get("ts") or 0)
    book["sequence"] = str(data.get("seq") or update_id or "")
    return True


def _sorted_book(bids: list[list[str]], asks: list[list[str]], depth: int):
    bid_rows = sorted(_levels(bids, depth), key=lambda row: float(row[0]), reverse=True)[:depth]
    ask_rows = sorted(_levels(asks, depth), key=lambda row: float(row[0]))[:depth]
    return bid_rows, ask_rows


def _metrics(bids: list[list[str]], asks: list[list[str]]) -> dict[str, float | None]:
    if not bids or not asks:
        return {"mid_price": None, "spread_bps": None, "bid_depth_native": None,
                "ask_depth_native": None, "imbalance_native": None}
    bid, ask = float(bids[0][0]), float(asks[0][0])
    if bid <= 0 or ask <= bid:
        return {"mid_price": None, "spread_bps": None, "bid_depth_native": None,
                "ask_depth_native": None, "imbalance_native": None}
    mid = (bid + ask) / 2
    bid_qty = sum(float(row[1]) for row in bids)
    ask_qty = sum(float(row[1]) for row in asks)
    total = bid_qty + ask_qty
    return {"mid_price": mid, "spread_bps": (ask - bid) / mid * 10000,
            "bid_depth_native": bid_qty, "ask_depth_native": ask_qty,
            "imbalance_native": (bid_qty - ask_qty) / total if total else None}


def _record(exchange: str, symbol: str, book: dict[str, Any], sampled_ms: int,
            depth: int, size_unit: str):
    bids, asks = _sorted_book(book.get("bids", []), book.get("asks", []), depth)
    metrics = _metrics(bids, asks)
    if metrics["mid_price"] is None:
        return None
    received = int(book.get("received_at_ms") or sampled_ms)
    return {
        "exchange": exchange, "symbol": symbol, "sampled_at_ms": sampled_ms,
        "exchange_ts_ms": int(book.get("exchange_ts_ms") or 0),
        "book_update_received_at_ms": received, "book_age_ms": max(0, sampled_ms - received),
        "sequence_id": str(book.get("sequence") or ""),
        "depth_levels": min(len(bids), len(asks)), "size_unit": size_unit,
        **metrics,
        "bids_json": json.dumps(bids, separators=(",", ":")),
        "asks_json": json.dumps(asks, separators=(",", ":")),
        "data_class": "REAL_PUBLIC_L2",
    }


def _sample(latest, output, exchange, now_ms, last_ms, depth, size_unit, alive_ms, interval_ms):
    if now_ms - last_ms < interval_ms or now_ms - alive_ms > 45_000:
        return last_ms
    for symbol, book in latest.items():
        row = _record(exchange, symbol, book, now_ms, depth, size_unit)
        if row:
            output.append(row)
    return now_ms


async def _capture_okx(symbols, duration, interval):
    reverse = {SYMBOLS[s]["okx"]: s for s in symbols}
    latest, rows = {}, []
    async with websockets.connect("wss://ws.okx.com:443/ws/v5/public",
            open_timeout=20, close_timeout=5, ping_interval=None, max_size=4_000_000) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [
            {"channel": "books5", "instId": SYMBOLS[s]["okx"]} for s in symbols]}))
        started, last_sample, last_ping = time.monotonic(), 0, time.monotonic()
        alive_ms = int(time.time() * 1000)
        while time.monotonic() - started < duration:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                alive_ms = int(time.time() * 1000)
            except asyncio.TimeoutError:
                if time.monotonic() - last_ping >= 20:
                    await ws.send("ping")
                    last_ping = time.monotonic()
                now = int(time.time() * 1000)
                last_sample = _sample(latest, rows, "okx", now, last_sample, 5,
                                      "CONTRACTS", alive_ms, interval * 1000)
                continue
            if raw == "pong":
                continue
            msg = json.loads(raw)
            if msg.get("event") == "error":
                raise RuntimeError("OKX_SUBSCRIBE_ERROR:" + str(msg.get("msg", ""))[:180])
            symbol = reverse.get((msg.get("arg") or {}).get("instId"))
            if not symbol:
                continue
            for item in msg.get("data", []) or []:
                bids, asks = _sorted_book(item.get("bids", []), item.get("asks", []), 5)
                latest[symbol] = {"bids": bids, "asks": asks,
                    "exchange_ts_ms": int(item.get("ts") or 0),
                    "sequence": str(item.get("seqId") or ""), "received_at_ms": alive_ms}
            now = int(time.time() * 1000)
            last_sample = _sample(latest, rows, "okx", now, last_sample, 5,
                                  "CONTRACTS", alive_ms, interval * 1000)
    return rows


async def _capture_bybit(symbols, duration, interval):
    reverse = {SYMBOLS[s]["bybit"]: s for s in symbols}
    books, latest, rows = {}, {}, []
    async with websockets.connect("wss://stream.bybit.com/v5/public/linear",
            open_timeout=20, close_timeout=5, ping_interval=None, max_size=4_000_000) as ws:
        await ws.send(json.dumps({"op": "subscribe",
            "args": [f"orderbook.50.{SYMBOLS[s]['bybit']}" for s in symbols]}))
        started, last_sample, last_ping = time.monotonic(), 0, time.monotonic()
        alive_ms = int(time.time() * 1000)
        while time.monotonic() - started < duration:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                alive_ms = int(time.time() * 1000)
            except asyncio.TimeoutError:
                if time.monotonic() - last_ping >= 20:
                    await ws.send(json.dumps({"op": "ping"}))
                    last_ping = time.monotonic()
                now = int(time.time() * 1000)
                last_sample = _sample(latest, rows, "bybit", now, last_sample, 50,
                                      "BASE_QTY_LINEAR", alive_ms, interval * 1000)
                continue
            msg = json.loads(raw)
            if msg.get("success") is False:
                raise RuntimeError("BYBIT_SUBSCRIBE_ERROR:" + str(msg.get("ret_msg", ""))[:180])
            market_symbol = str(msg.get("topic", "")).rsplit(".", 1)[-1]
            symbol = reverse.get(market_symbol)
            if not symbol:
                continue
            book = books.setdefault(symbol, {"bids": {}, "asks": {}, "has_snapshot": False})
            if apply_bybit_update(book, msg):
                bids = sorted([[p, q] for p, q in book["bids"].items()],
                              key=lambda row: float(row[0]), reverse=True)[:50]
                asks = sorted([[p, q] for p, q in book["asks"].items()],
                              key=lambda row: float(row[0]))[:50]
                latest[symbol] = {"bids": bids, "asks": asks,
                    "exchange_ts_ms": book.get("exchange_ts_ms", 0),
                    "sequence": book.get("sequence", ""), "received_at_ms": alive_ms}
            now = int(time.time() * 1000)
            last_sample = _sample(latest, rows, "bybit", now, last_sample, 50,
                                  "BASE_QTY_LINEAR", alive_ms, interval * 1000)
    return rows


async def _kucoin_token():
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post("https://api-futures.kucoin.com/api/v1/bullet-public")
        response.raise_for_status()
        body = response.json()
    if body.get("code") != "200000":
        raise RuntimeError("KUCOIN_PUBLIC_TOKEN_ERROR")
    server = body["data"]["instanceServers"][0]
    return server["endpoint"], body["data"]["token"], int(server.get("pingInterval", 18000))


def _parse_kucoin_level5(message: dict[str, Any], reverse: dict[str, str]):
    """تبدیل پیام عمومی Level 5 کوکوین به دفتر سفارش استاندارد داخلی."""
    market_symbol = str(message.get("topic", "")).split(":", 1)[-1]
    symbol = reverse.get(market_symbol)
    data = message.get("data") or {}
    if not symbol or not data.get("bids") or not data.get("asks"):
        return None
    bids, asks = _sorted_book(data["bids"], data["asks"], 5)
    if not bids or not asks:
        return None
    return symbol, {
        "bids": bids, "asks": asks,
        "exchange_ts_ms": int(data.get("timestamp") or data.get("ts") or 0),
        "sequence": str(data.get("sequence") or message.get("sn") or ""),
    }


async def _kucoin_heartbeat_if_due(ws, last_ping: float, interval_seconds: float,
                                now: float | None = None) -> float:
    """ارسال پینگ متنی مستقل از تعداد پیام‌های بازار."""
    current = time.monotonic() if now is None else now
    if current - last_ping < interval_seconds:
        return last_ping
    await ws.send(json.dumps({"id": str(int(time.time() * 1000)), "type": "ping"}))
    return current


async def _capture_kucoin(symbols, duration, interval):
    endpoint, token, ping_ms = await _kucoin_token()
    url = endpoint + "?token=" + token + "&connectId=" + uuid.uuid4().hex
    reverse = {SYMBOLS[s]["kucoin"]: s for s in symbols}
    latest, rows = {}, []
    diagnostics = {"messages": 0, "acks": 0, "book_messages": 0,
                   "symbols_with_book": set(), "normal_close": False}
    async with websockets.connect(url, open_timeout=25, close_timeout=5,
                                  ping_interval=None, max_size=4_000_000) as ws:
        for symbol in symbols:
            await ws.send(json.dumps({"id": str(int(time.time() * 1000)), "type": "subscribe",
                "topic": "/contractMarket/level2Depth5:" + SYMBOLS[symbol]["kucoin"],
                "privateChannel": False, "response": True}))
        started, last_sample, last_ping = time.monotonic(), 0, time.monotonic()
        alive_ms = int(time.time() * 1000)
        # کوکوین پینگ متنی می‌خواهد؛ ارسال پینگ نباید به سکوت بازار وابسته باشد.
        ping_every_seconds = max(3.0, min(8.0, ping_ms / 1000 * 0.4))
        while time.monotonic() - started < duration:
            last_ping = await _kucoin_heartbeat_if_due(
                ws, last_ping, ping_every_seconds
            )
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
                alive_ms = int(time.time() * 1000)
            except asyncio.TimeoutError:
                now = int(time.time() * 1000)
                last_sample = _sample(latest, rows, "kucoin", now, last_sample, 5,
                                      "CONTRACTS", alive_ms, interval * 1000)
                continue
            except websockets.exceptions.ConnectionClosedOK as exc:
                elapsed = time.monotonic() - started
                if elapsed >= duration - 5:
                    diagnostics["normal_close"] = True
                    break
                raise RuntimeError(
                    f"KUCOIN_EARLY_NORMAL_CLOSE elapsed_seconds={elapsed:.1f} "
                    f"code={exc.code} reason={exc.reason!r}"
                ) from exc
            msg = json.loads(raw)
            diagnostics["messages"] += 1
            if msg.get("type") == "error":
                diagnostics["last_error"] = str(msg)[:240]
                raise RuntimeError("KUCOIN_WS_ERROR:" + str(msg)[:240])
            if msg.get("type") == "ack":
                diagnostics["acks"] += 1
                continue
            if msg.get("type") == "pong":
                continue
            parsed = _parse_kucoin_level5(msg, reverse)
            if parsed is None:
                continue
            symbol, book_data = parsed
            diagnostics["book_messages"] += 1
            diagnostics["symbols_with_book"].add(symbol)
            latest[symbol] = {
                **book_data,
                "received_at_ms": alive_ms,
            }
            now = int(time.time() * 1000)
            last_sample = _sample(latest, rows, "kucoin", now, last_sample, 5,
                                  "CONTRACTS", alive_ms, interval * 1000)
    diagnostics["symbols_with_book"] = sorted(diagnostics["symbols_with_book"])
    diagnostics["rows_sampled"] = len(rows)
    diagnostics["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print("KUCOIN_WS_DIAGNOSTICS=" + json.dumps(diagnostics, ensure_ascii=False))
    return rows

async def capture_orderbooks(symbols: list[str], duration: int = 600,
                             sample_interval: int = 10) -> dict[str, Any]:
    adapters = {"okx": _capture_okx, "bybit": _capture_bybit, "kucoin": _capture_kucoin}
    async def run_one(name, adapter):
        try:
            records = await adapter(symbols, duration, sample_interval)
            return name, {"status": "PASS" if records else "NO_BOOK_SNAPSHOTS",
                          "rows": records, "error": None}
        except Exception as exc:
            return name, {"status": "ERROR", "rows": [],
                          "error": type(exc).__name__ + ":" + str(exc)[:240]}

    pairs = await asyncio.gather(
        *(run_one(name, adapter) for name, adapter in adapters.items())
    )
    results = dict(pairs)
    passed = sum(1 for item in results.values() if item["status"] == "PASS")
    records = [row for item in results.values() for row in item["rows"]]
    return {"status": "PASS" if passed == 3 else ("PARTIAL" if passed else "BLOCKED"),
            "providers": {name: {"status": item["status"], "rows": len(item["rows"]),
                                 "error": item["error"]} for name, item in results.items()},
            "total_rows": len(records), "records": records,
            "captured_at_utc": datetime.now(timezone.utc).isoformat()}


def write_parquet_records(records: list[dict[str, Any]], output_dir: str | Path) -> list[str]:
    root = Path(output_dir)
    grouped = {}
    for row in records:
        day = datetime.fromtimestamp(row["sampled_at_ms"] / 1000, timezone.utc).strftime("%Y-%m-%d")
        grouped.setdefault((row["exchange"], day), []).append(row)
    paths = []
    for (exchange, day), rows in grouped.items():
        path = root / day / f"{exchange}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
        paths.append(str(path))
    return paths
