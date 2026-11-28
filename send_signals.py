#!/usr/bin/env python3
"""Read-only weekly futures signal generator. Never places orders."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def _load_universe_manifest() -> tuple[str, tuple[str, ...]]:
    manifest_path = Path(__file__).resolve().parent / "config" / "universe.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("UNIVERSE_MANIFEST_UNAVAILABLE") from exc
    symbols = tuple(manifest.get("symbols", []))
    if (len(symbols) != 9 or len(set(symbols)) != 9 or
            symbols[0] != "BTCUSDT" or any(not item.endswith("USDT") for item in symbols)):
        raise RuntimeError("UNIVERSE_MANIFEST_INVALID: expected nine unique USDT perpetual symbols with BTC first")
    version = str(manifest.get("version", "UNVERSIONED"))
    if version == "UNVERSIONED":
        raise RuntimeError("UNIVERSE_MANIFEST_VERSION_MISSING")
    return version, symbols


UNIVERSE_VERSION, UNIVERSE = _load_universe_manifest()
ALTCOINS = UNIVERSE[1:]
PROVIDERS = ("OKX", "BYBIT", "BINANCE_FUTURES")
TIMEOUT_SECONDS = 15
CANDLE_LIMIT = 100
VOLUME_LABEL = "base-asset futures volume"


@dataclass(frozen=True)
class Candle:
    day: date
    open: float
    high: float
    low: float
    close: float
    base_volume: float


class ProviderError(RuntimeError):
    pass


def _http_json(url: str, params: dict[str, str]) -> Any:
    query = urlencode(params)
    request = Request(
        f"{url}?{query}",
        headers={"User-Agent": "Trade-ReadOnly-SignalBot/1.0", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ProviderError(f"HTTP_OR_JSON_ERROR:{type(exc).__name__}") from exc
    return payload


def _utc_day(timestamp_ms: Any) -> date:
    return datetime.fromtimestamp(int(timestamp_ms) / 1000.0, tz=timezone.utc).date()


def _valid_candle(day_value: date, o: Any, h: Any, l: Any, c: Any, volume: Any) -> Candle:
    values = [float(o), float(h), float(l), float(c), float(volume)]
    op, high, low, close, base_volume = values
    if not all(math.isfinite(x) for x in values):
        raise ProviderError("NON_FINITE_CANDLE")
    if min(op, high, low, close) <= 0 or base_volume < 0:
        raise ProviderError("INVALID_OHLC_OR_VOLUME")
    if high < max(op, low, close) or low > min(op, high, close):
        raise ProviderError("INVALID_OHLC_ORDER")
    return Candle(day_value, op, high, low, close, base_volume)


def fetch_okx(symbol: str) -> list[Candle]:
    inst_id = symbol.replace("USDT", "-USDT-SWAP")
    payload = _http_json(
        "https://www.okx.com/api/v5/market/history-candles",
        {"instId": inst_id, "bar": "1Dutc", "limit": str(CANDLE_LIMIT)},
    )
    if payload.get("code") != "0" or not isinstance(payload.get("data"), list):
        raise ProviderError(f"OKX_API_ERROR:{payload.get('code', 'UNKNOWN')}")
    rows = []
    for item in payload["data"]:
        if len(item) < 9 or str(item[8]) != "1":
            continue
        rows.append(_valid_candle(_utc_day(item[0]), item[1], item[2], item[3], item[4], item[6]))
    return sorted(rows, key=lambda x: x.day)


def fetch_bybit(symbol: str) -> list[Candle]:
    payload = _http_json(
        "https://api.bybit.com/v5/market/kline",
        {"category": "linear", "symbol": symbol, "interval": "D", "limit": str(CANDLE_LIMIT)},
    )
    if payload.get("retCode") != 0 or not isinstance(payload.get("result", {}).get("list"), list):
        raise ProviderError(f"BYBIT_API_ERROR:{payload.get('retCode', 'UNKNOWN')}")
    rows = []
    for item in payload["result"]["list"]:
        if len(item) < 7:
            raise ProviderError("BYBIT_KLINE_SCHEMA_INVALID")
        rows.append(_valid_candle(_utc_day(item[0]), item[1], item[2], item[3], item[4], item[5]))
    return sorted(rows, key=lambda x: x.day)


def fetch_binance_futures(symbol: str) -> list[Candle]:
    payload = _http_json(
        "https://fapi.binance.com/fapi/v1/klines",
        {"symbol": symbol, "interval": "1d", "limit": str(CANDLE_LIMIT)},
    )
    if not isinstance(payload, list):
        raise ProviderError("BINANCE_FUTURES_API_ERROR")
    rows = []
    for item in payload:
        if len(item) < 8:
            raise ProviderError("BINANCE_FUTURES_KLINE_SCHEMA_INVALID")
        rows.append(_valid_candle(_utc_day(item[0]), item[1], item[2], item[3], item[4], item[5]))
    return sorted(rows, key=lambda x: x.day)


def fetch_symbol(provider: str, symbol: str) -> list[Candle]:
    if provider == "OKX":
        return fetch_okx(symbol)
    if provider == "BYBIT":
        return fetch_bybit(symbol)
    if provider == "BINANCE_FUTURES":
        return fetch_binance_futures(symbol)
    raise ProviderError(f"UNKNOWN_PROVIDER:{provider}")


def latest_completed_friday(now_utc: datetime) -> date:
    now_utc = now_utc.astimezone(timezone.utc)
    days_since_friday = (now_utc.date().weekday() - 4) % 7
    target = now_utc.date() - timedelta(days=days_since_friday)
    # Friday's UTC daily candle closes at Saturday 00:00 UTC.
    if now_utc.date().weekday() == 4:
        target -= timedelta(days=7)
    return target


def fetch_consistent_universe(target_friday: date) -> tuple[str, dict[str, list[Candle]], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    for provider in PROVIDERS:
        try:
            market: dict[str, list[Candle]] = {}
            for symbol in UNIVERSE:
                candles = fetch_symbol(provider, symbol)
                candles = [c for c in candles if c.day <= target_friday]
                if not candles or candles[-1].day != target_friday:
                    raise ProviderError(f"TARGET_FRIDAY_MISSING:{symbol}:{target_friday.isoformat()}")
                if len(candles) < 50:
                    raise ProviderError(f"INSUFFICIENT_HISTORY:{symbol}:{len(candles)}")
                market[symbol] = candles
            return provider, market, failures
        except Exception as exc:
            failures.append({"provider": provider, "reason": str(exc)[:240]})
    raise ProviderError("ALL_FUTURES_PROVIDERS_FAILED:" + json.dumps(failures, ensure_ascii=False))


def _zscore(values: dict[str, float]) -> dict[str, float]:
    vals = list(values.values())
    mean = sum(vals) / len(vals)
    variance = sum((x - mean) ** 2 for x in vals) / len(vals)
    sd = math.sqrt(variance)
    if not math.isfinite(sd) or sd <= 1e-12:
        raise ProviderError("CROSS_SECTION_STANDARD_DEVIATION_ZERO")
    return {key: (value - mean) / sd for key, value in values.items()}


def _rsi14(closes: list[float]) -> float:
    if len(closes) < 15:
        raise ProviderError("RSI_HISTORY_INSUFFICIENT")
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(x, 0.0) for x in deltas]
    losses = [max(-x, 0.0) for x in deltas]
    avg_gain = sum(gains[:14]) / 14.0
    avg_loss = sum(losses[:14]) / 14.0
    for gain, loss in zip(gains[14:], losses[14:]):
        avg_gain = (avg_gain * 13.0 + gain) / 14.0
        avg_loss = (avg_loss * 13.0 + loss) / 14.0
    if avg_loss <= 1e-15:
        return 100.0 if avg_gain > 1e-15 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def build_signal(provider: str, market: dict[str, list[Candle]], target_friday: date) -> dict[str, Any]:
    btc = market["BTCUSDT"]
    btc_closes = [c.close for c in btc if c.day <= target_friday]
    if len(btc_closes) < 50:
        raise ProviderError("BTC_MA50_HISTORY_INSUFFICIENT")
    btc_close = btc_closes[-1]
    btc_ma50 = sum(btc_closes[-50:]) / 50.0
    base: dict[str, Any] = {
        "as_of_utc": target_friday.isoformat(),
        "provider": provider,
        "market": "USDT_PERPETUAL",
        "benchmark": "BTCUSDT",
        "btc_close": btc_close,
        "btc_ma50": btc_ma50,
        "volume_measure": VOLUME_LABEL,
        "universe_version": UNIVERSE_VERSION,
        "universe": list(UNIVERSE),
        "execution": "MANUAL_ONLY_NO_ORDERS",
    }
    if btc_close <= btc_ma50:
        return {**base, "state": "CASH", "selected": [], "scores": {}}

    volume_z20: dict[str, float] = {}
    rsi14: dict[str, float] = {}
    closes_by_symbol: dict[str, float] = {}
    for symbol in ALTCOINS:
        candles = [c for c in market[symbol] if c.day <= target_friday]
        if len(candles) < 20:
            raise ProviderError(f"ALT_HISTORY_INSUFFICIENT:{symbol}")
        volumes = [c.base_volume for c in candles[-20:]]
        mean = sum(volumes) / 20.0
        variance = sum((v - mean) ** 2 for v in volumes) / 20.0
        sd = math.sqrt(variance)
        if sd <= 1e-12:
            raise ProviderError(f"VOLUME_STD_ZERO:{symbol}")
        volume_z20[symbol] = (volumes[-1] - mean) / sd
        closes = [c.close for c in candles]
        rsi14[symbol] = _rsi14(closes)
        closes_by_symbol[symbol] = closes[-1]

    zv = _zscore(volume_z20)
    zr = _zscore(rsi14)
    scores = {symbol: 0.5 * zv[symbol] + 0.5 * zr[symbol] for symbol in ALTCOINS}
    ranked = sorted(ALTCOINS, key=lambda symbol: (-scores[symbol], symbol))
    selected = [
        {"symbol": symbol, "close": closes_by_symbol[symbol],
         "volume_z20": volume_z20[symbol], "rsi14": rsi14[symbol], "score": scores[symbol]}
        for symbol in ranked[:2]
    ]
    return {**base, "state": "LONG_TOP_2", "selected": selected,
            "scores": scores, "ranked_symbols": ranked}


def format_persian_message(signal: dict[str, Any]) -> str:
    day = signal["as_of_utc"]
    provider = signal["provider"]
    if signal["state"] == "CASH":
        return (
            "گزارش هفتگی بازار آتی\n"
            f"تاریخ مبنا: {day} | منبع داده: {provider}\n"
            "وضعیت بازار: CASH\n"
            f"BTC: {signal['btc_close']:.6g}\n"
            f"MA50 بیت‌کوین: {signal['btc_ma50']:.6g}\n"
            "شرط روند صعودی برقرار نیست؛ در این دوره هیچ موقعیت لانگی انتخاب نمی‌شود.\n"
            "این خروجی صرفاً تحلیل است؛ هیچ سفارشی اجرا نمی‌شود."
        )
    lines = [
        "سیگنال هفتگی بازار آتی",
        f"تاریخ مبنا: {day} | منبع داده: {provider}",
        "وضعیت بازار: BTC بالاتر از MA50 — انتخاب دو موقعیت لانگ",
        f"BTC: {signal['btc_close']:.6g} | MA50: {signal['btc_ma50']:.6g}",
        "",
        "دو دارایی برتر:",
    ]
    for index, item in enumerate(signal["selected"], start=1):
        lines.append(
            f"{index}) {item['symbol']} | قیمت بسته‌شدن: {item['close']:.6g} | "
            f"امتیاز: {item['score']:.4f} | Volume_Z20: {item['volume_z20']:.3f} | "
            f"RSI14: {item['rsi14']:.2f}"
        )
    lines.append("")
    lines.append("Volume_Z20 بر اساس حجم دارایی پایه در قرارداد دائمی محاسبه شده است.")
    lines.append("این خروجی صرفاً تحلیل است؛ هیچ سفارشی اجرا نمی‌شود.")
    return "\n".join(lines)


def send_telegram(message: str, token: str, chat_id: str) -> dict[str, Any]:
    if not token or not chat_id:
        return {"status": "SKIPPED_NOT_CONFIGURED"}
    payload = json.dumps({
        "chat_id": chat_id, "text": message,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"TELEGRAM_SEND_FAILED:{type(exc).__name__}") from exc
    if not result.get("ok") or not isinstance(result.get("result"), dict):
        raise RuntimeError("TELEGRAM_SEND_REJECTED")
    sent = result["result"]
    return {
        "status": "SENT",
        "message_id": sent.get("message_id"),
        "chat_id": str(sent.get("chat", {}).get("id", "")),
        "date": sent.get("date"),
    }


def load_release_gate(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "BLOCKED_NO_RELEASE_GATE"}
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "BLOCKED_INVALID_RELEASE_GATE"}
    if gate.get("status") != "PASS" or gate.get("max_drawdown_below_30_percent") is not True:
        return {"status": "BLOCKED_RESEARCH_NOT_VALIDATED"}
    if gate.get("profit_factor_above_1_50") is not True or gate.get("pbo_below_0_40") is not True:
        return {"status": "BLOCKED_RESEARCH_NOT_VALIDATED"}
    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--market-data-smoke", action="store_true",
                        help="Fetch real public futures data and calculate a signal without Telegram delivery")
    parser.add_argument("--now-utc", help="ISO-8601 timestamp override for deterministic tests")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now_utc.replace("Z", "+00:00")) if args.now_utc else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SystemExit("--now-utc must include a timezone")
    if args.market_data_smoke and not args.dry_run:
        raise SystemExit("--market-data-smoke requires --dry-run")
    target_friday = latest_completed_friday(now)
    gate = load_release_gate(Path("config/signal_release_gate.json"))

    if gate.get("status") != "PASS" and not args.market_data_smoke:
        message = (
            "وضعیت سامانه سیگنال‌دهی\n"
            f"تاریخ: {target_friday.isoformat()}\n"
            "NO TRADE — اعتبارسنجی استراتژی هنوز معیارهای انتشار را پاس نکرده است.\n"
            "هیچ سیگنال معاملاتی صادر نشد و هیچ سفارشی اجرا نمی‌شود."
        )
        result = {"state": "NO_QUALIFIED_SETUP", "release_gate": gate.get("status"),
                  "as_of_utc": target_friday.isoformat(), "telegram": {"status": "DRY_RUN" if args.dry_run else "NOT_ATTEMPTED"}}
    else:
        provider, market, failures = fetch_consistent_universe(target_friday)
        signal = build_signal(provider, market, target_friday)
        message = format_persian_message(signal)
        if args.market_data_smoke:
            message = (
                "آزمون داده — این پیام به تلگرام ارسال نمی‌شود\n"
                + message
                + "\nخروجی صرفاً برای بررسی API عمومی و محاسبات است؛ سیگنال منتشر نشده است."
            )
        result = {**signal, "provider_failures": failures,
                  "mode": "MARKET_DATA_SMOKE_ONLY" if args.market_data_smoke else "PRODUCTION",
                  "release_gate": gate.get("status"),
                  "telegram": {"status": "NOT_ATTEMPTED" if args.market_data_smoke else ("DRY_RUN" if args.dry_run else "PENDING")}}

    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/telegram_message.txt").write_text(message + "\n", encoding="utf-8")
    if not args.dry_run:
        delivery = send_telegram(message, os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))
        result["telegram"] = delivery
    Path("artifacts/signals.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print("----- EXACT_TELEGRAM_MESSAGE_BEGIN -----")
    print(message)
    print("----- EXACT_TELEGRAM_MESSAGE_END -----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
