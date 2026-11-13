"""ردیاب نتایج Stage 1؛ OHLCV عمومی، ورود در Open کندل بعد و بدون سفارش."""
from __future__ import annotations
import argparse, json, logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
import ccxt

LOG = logging.getLogger("research_tracker")
INTERVAL_MS = 900_000
MAX_HOLD = timedelta(hours=48)
PROVIDERS = ("okx", "bybit", "kucoinfutures", "mexc", "bitget")
TERMINAL = {"TP_HIT", "SL_HIT", "EXPIRED", "AMBIGUOUS_BOTH_TOUCHED", "ENTRY_INVALIDATED_GAP"}


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp_must_be_timezone_aware")
    return dt.astimezone(timezone.utc)


def _market_symbol(exchange: Any, symbol: str) -> str:
    base = symbol[:-4] if symbol.upper().endswith("USDT") else symbol.upper()
    for market in exchange.markets.values():
        if (market.get("active", True) and market.get("swap") and market.get("linear")
            and str(market.get("base", "")).upper() == base
            and str(market.get("quote", "")).upper() == "USDT"
            and str(market.get("settle", "")).upper() == "USDT"):
            return str(market["symbol"])
    raise ValueError(f"linear_usdt_swap_not_found:{symbol}")


def fetch_public_ohlcv(symbol: str, since_ms: int, now_ms: int, limit: int = 200):
    """دریافت کندل بسته‌شده از زنجیرهٔ عمومی OKX سپس fallback."""
    errors = []
    for provider in PROVIDERS:
        exchange = None
        try:
            exchange = getattr(ccxt, provider)({
                "enableRateLimit": True, "timeout": 20000,
                "options": {"defaultType": "swap"},
            })
            exchange.load_markets()
            market = _market_symbol(exchange, symbol)
            raw = exchange.fetch_ohlcv(market, timeframe="15m", since=int(since_ms), limit=int(limit))
            rows = []
            for c in raw or []:
                if len(c) >= 6 and int(c[0]) >= since_ms and int(c[0]) + INTERVAL_MS <= now_ms:
                    rows.append({
                        "open_time": int(c[0]), "open": float(c[1]), "high": float(c[2]),
                        "low": float(c[3]), "close": float(c[4]), "volume": float(c[5]),
                    })
            rows.sort(key=lambda x: x["open_time"])
            if rows and rows[0]["open_time"] == int(since_ms):
                if any(rows[i]["open_time"] - rows[i - 1]["open_time"] != INTERVAL_MS for i in range(1, len(rows))):
                    errors.append(f"{provider}:CANDLE_GAP_DETECTED")
                    continue
                return rows, f"{provider.upper()}_PUBLIC_OHLCV"
            if rows:
                errors.append(f"{provider}:FIRST_REQUIRED_CANDLE_MISSING")
            errors.append(f"{provider}:NO_CLOSED_CANDLES")
        except Exception as exc:
            errors.append(f"{provider}:{type(exc).__name__}:{str(exc)[:100]}")
        finally:
            if exchange is not None:
                try: exchange.close()
                except Exception: pass
    raise RuntimeError("PUBLIC_OHLCV_UNAVAILABLE|" + "|".join(errors))


def _pnl_pct(direction: str, entry: float, exit_price: float) -> float:
    if entry <= 0: raise ValueError("entry_must_be_positive")
    return ((entry - exit_price) if direction == "SELL" else (exit_price - entry)) / entry * 100.0


def _touch_result(direction: str, candle: dict[str, Any], stop: float, target: float):
    op, hi, lo = float(candle["open"]), float(candle["high"]), float(candle["low"])
    if direction == "SELL":
        if op >= stop: return "SL_HIT", op
        if op <= target: return "TP_HIT", op
        sl, tp = hi >= stop, lo <= target
    else:
        if op <= stop: return "SL_HIT", op
        if op >= target: return "TP_HIT", op
        sl, tp = lo <= stop, hi >= target
    if sl and tp: return "AMBIGUOUS_BOTH_TOUCHED", None
    if sl: return "SL_HIT", stop
    if tp: return "TP_HIT", target
    return None, None


def _entry_invalidation_reason(direction: str, entry: float, stop: float, target: float) -> str | None:
    """اگر بازار قبل از ورود از یکی از سطوح عبور کرده باشد، معامله‌ای فعال نشده است."""
    if direction == "SELL":
        if entry <= target:
            return "TARGET_ALREADY_PASSED_BEFORE_ENTRY"
        if entry >= stop:
            return "STOP_ALREADY_BREACHED_BEFORE_ENTRY"
    else:
        if entry >= target:
            return "TARGET_ALREADY_PASSED_BEFORE_ENTRY"
        if entry <= stop:
            return "STOP_ALREADY_BREACHED_BEFORE_ENTRY"
    return None


def _new_outcome(signal: dict[str, Any], now: datetime) -> dict[str, Any]:
    return {
        "signal_id": signal["signal_id"], "symbol": signal["symbol"],
        "direction": signal["direction"], "status": "ENTRY_PENDING_DATA",
        "entry_contract": "FIRST_15M_OPEN_STRICTLY_AFTER_SIGNAL_TIMESTAMP",
        "entry_reference": float(signal["entry_reference"]), "entry_actual": None,
        "entry_time_utc": None, "entry_candle_ohlc": None,
        "entry_fill_status": "PENDING", "entry_invalidation_reason": None,
        "stop_reference": float(signal["stop_reference"]),
        "target_reference": float(signal["target_reference"]), "rr_actual": None,
        "exit_price": None, "exit_time_utc": None, "exit_candle_ohlc": None, "pnl_pct_raw": None,
        "fee_pct": "UNAVAILABLE", "slippage_pct": "UNAVAILABLE",
        "net_pnl_pct": "UNAVAILABLE", "data_source": "UNAVAILABLE",
        "last_checked_open_time": None, "last_checked_at_utc": now.isoformat(),
        "last_error": None,
        "history": [{"status": "ENTRY_PENDING_DATA", "at_utc": now.isoformat(),
                     "reason": "WAITING_FOR_NEXT_CLOSED_15M_CANDLE"}],
    }


def _event(outcome: dict[str, Any], status: str, now: datetime, reason: str):
    if outcome.get("status") != status:
        outcome.setdefault("history", []).append({
            "status": status, "at_utc": now.isoformat(), "reason": reason
        })
    outcome["status"] = status


def update_one(signal: dict[str, Any], outcome: dict[str, Any] | None,
               fetcher: Callable, now: datetime) -> dict[str, Any]:
    if signal.get("collection_status") != "PENDING_OUTCOME_LABEL":
        return outcome or _new_outcome(signal, now)
    if signal.get("direction") not in {"BUY", "SELL"}: raise ValueError("invalid_direction")
    if outcome is None: outcome = _new_outcome(signal, now)
    if outcome.get("signal_id") != signal.get("signal_id"): raise ValueError("signal_id_mismatch")
    created = _parse_time(signal["created_at_utc"])
    # Entry candle must open strictly after the signal became available, not merely
    # after the candle used to calculate the signal. This prevents look-ahead fills.
    created_ms = int(created.timestamp() * 1000)
    first_open_after_signal = (created_ms // INTERVAL_MS + 1) * INTERVAL_MS
    next_open = max(first_open_after_signal, int(signal["candle_open_time"]) + INTERVAL_MS)

    # Invalidate any prior outcome whose simulated entry predates signal creation.
    prior_entry_time = outcome.get("entry_time_utc")
    invalid_reason = None
    if outcome.get("entry_actual") is not None:
        invalid_reason = _entry_invalidation_reason(
            str(signal["direction"]), float(outcome["entry_actual"]),
            float(signal["stop_reference"]), float(signal["target_reference"])
        )
    entry_candle = outcome.get("entry_candle_ohlc") or {}
    exit_candle = outcome.get("exit_candle_ohlc") or {}
    prior_gap_at_entry = (
        invalid_reason is not None
        and entry_candle.get("open_time") is not None
        and entry_candle.get("open_time") == exit_candle.get("open_time")
        and outcome.get("exit_price") is not None
        and float(outcome["exit_price"]) == float(outcome["entry_actual"])
    )
    if prior_entry_time and _parse_time(prior_entry_time) <= created:
        outcome["invalidated_prior_entry"] = {
            "status": outcome.get("status"), "entry_actual": outcome.get("entry_actual"),
            "entry_time_utc": prior_entry_time, "exit_price": outcome.get("exit_price"),
            "exit_time_utc": outcome.get("exit_time_utc"), "pnl_pct_raw": outcome.get("pnl_pct_raw"),
            "reason": "ENTRY_PRECEDES_SIGNAL_TIMESTAMP",
        }
        _event(outcome, "ENTRY_PENDING_DATA", now, "INVALIDATED_LOOKAHEAD_ENTRY")
    elif prior_gap_at_entry:
        outcome["invalidated_prior_outcome"] = {
            "status": outcome.get("status"), "entry_actual": outcome.get("entry_actual"),
            "entry_time_utc": prior_entry_time, "exit_price": outcome.get("exit_price"),
            "pnl_pct_raw": outcome.get("pnl_pct_raw"), "reason": invalid_reason,
        }
        _event(outcome, "ENTRY_PENDING_DATA", now, "RECLASSIFIED_GAP_AT_ENTRY_NOT_A_FILLED_TRADE")
    if (prior_entry_time and _parse_time(prior_entry_time) <= created) or prior_gap_at_entry:
        for key in (
            "entry_actual", "entry_time_utc", "entry_candle_ohlc", "entry_fill_status",
            "entry_invalidation_reason", "rr_actual", "exit_price", "exit_time_utc",
            "exit_candle_ohlc", "pnl_pct_raw", "last_checked_open_time",
        ):
            outcome[key] = None

    if outcome.get("status") in TERMINAL: return outcome
    expiry = created + MAX_HOLD
    now_ms = int(now.timestamp() * 1000)
    outcome["last_checked_at_utc"] = now.isoformat()
    try:
        candles, source = fetcher(str(signal["symbol"]), next_open, now_ms, 200)
        outcome["data_source"], outcome["last_error"] = source, None
    except Exception as exc:
        outcome["last_error"] = f"{type(exc).__name__}:{str(exc)[:240]}"
        _event(outcome, "DATA_UNAVAILABLE", now, "ALL_PUBLIC_PROVIDERS_FAILED")
        return outcome

    candles = sorted([c for c in candles if int(c["open_time"]) >= next_open],
                     key=lambda x: int(x["open_time"]))
    next_candle = next((c for c in candles if int(c["open_time"]) == next_open), None)
    if outcome.get("entry_actual") is None:
        if next_candle is None:
            status = "ENTRY_PENDING_DATA" if now_ms < next_open + INTERVAL_MS else "DATA_UNAVAILABLE"
            reason = "NEXT_CANDLE_NOT_CLOSED" if status == "ENTRY_PENDING_DATA" else "NEXT_CANDLE_MISSING_FROM_PUBLIC_DATA"
            _event(outcome, status, now, reason)
            return outcome
        entry = float(next_candle["open"])
        if entry <= 0:
            _event(outcome, "DATA_UNAVAILABLE", now, "INVALID_NEXT_CANDLE_OPEN")
            return outcome
        stop, target = float(signal["stop_reference"]), float(signal["target_reference"])
        risk = abs(entry - stop)
        if risk <= 0:
            _event(outcome, "DATA_UNAVAILABLE", now, "INVALID_RISK_FROM_ACTUAL_ENTRY")
            return outcome
        outcome.update({
            "entry_actual": entry,
            "entry_time_utc": datetime.fromtimestamp(next_open / 1000, timezone.utc).isoformat(),
            "entry_candle_ohlc": {k: next_candle[k] for k in ("open_time", "open", "high", "low", "close", "volume")},
        })
        invalid_reason = _entry_invalidation_reason(str(signal["direction"]), entry, stop, target)
        if invalid_reason:
            outcome["entry_fill_status"] = "NOT_FILLED"
            outcome["entry_invalidation_reason"] = invalid_reason
            _event(outcome, "ENTRY_INVALIDATED_GAP", now, invalid_reason)
            return outcome
        outcome["entry_fill_status"] = "SIMULATED_FILLED"
        outcome["rr_actual"] = abs(target - entry) / risk
        _event(outcome, "ACTIVE", now, "ENTRY_FILLED_AT_NEXT_15M_OPEN")

    entry, stop, target = (float(outcome["entry_actual"]),
                           float(signal["stop_reference"]), float(signal["target_reference"]))
    last_processed = outcome.get("last_checked_open_time")
    for candle in candles:
        opened = int(candle["open_time"])
        if opened < next_open or (last_processed is not None and opened <= int(last_processed)):
            continue
        status, exit_price = _touch_result(str(signal["direction"]), candle, stop, target)
        outcome["last_checked_open_time"] = opened
        if status:
            _event(outcome, status, now, "PRICE_LEVEL_TOUCHED")
            outcome["exit_price"] = exit_price
            outcome["exit_candle_ohlc"] = {k: candle[k] for k in ("open_time", "open", "high", "low", "close", "volume")}
            outcome["exit_time_utc"] = datetime.fromtimestamp((opened + INTERVAL_MS) / 1000, timezone.utc).isoformat()
            if status in {"TP_HIT", "SL_HIT"} and exit_price is not None:
                outcome["pnl_pct_raw"] = round(_pnl_pct(str(signal["direction"]), entry, float(exit_price)), 8)
            return outcome
        if datetime.fromtimestamp((opened + INTERVAL_MS) / 1000, timezone.utc) >= expiry:
            exit_price = float(candle["close"])
            _event(outcome, "EXPIRED", now, "48H_HOLD_LIMIT_REACHED")
            outcome["exit_price"] = exit_price
            outcome["exit_candle_ohlc"] = {k: candle[k] for k in ("open_time", "open", "high", "low", "close", "volume")}
            outcome["exit_time_utc"] = datetime.fromtimestamp((opened + INTERVAL_MS) / 1000, timezone.utc).isoformat()
            outcome["pnl_pct_raw"] = round(_pnl_pct(str(signal["direction"]), entry, exit_price), 8)
            return outcome
    if candles:
        outcome["last_checked_open_time"] = max(int(c["open_time"]) for c in candles)
    if outcome.get("status") == "DATA_UNAVAILABLE" and outcome.get("entry_actual") is not None:
        _event(outcome, "ACTIVE", now, "PUBLIC_DATA_RECOVERED")
    return outcome


def update_outcomes(signals_path: Path, outcomes_path: Path, now: datetime | None = None,
                    fetcher: Callable = fetch_public_ohlcv) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source = json.loads(signals_path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or not isinstance(source.get("signals"), list):
        raise ValueError("INVALID_RESEARCH_SIGNALS_SCHEMA")
    previous = json.loads(outcomes_path.read_text(encoding="utf-8")) if outcomes_path.exists() else {"outcomes": []}
    existing = {x["signal_id"]: x for x in previous.get("outcomes", [])
                if isinstance(x, dict) and x.get("signal_id")}
    rows = [update_one(s, existing.get(s.get("signal_id")), fetcher, now)
            for s in source["signals"] if s.get("signal_id")]
    payload = {
        "schema_version": 1, "updated_at_utc": now.isoformat(),
        "entry_contract": "FIRST_15M_OPEN_STRICTLY_AFTER_SIGNAL_TIMESTAMP",
        "source_signals_count": len(source["signals"]), "outcomes_count": len(rows),
        "outcomes": rows,
    }
    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    outcomes_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {}
    for row in rows: counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"counts": counts, "outcomes": rows, "path": str(outcomes_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = update_outcomes(args.signals, args.outcomes)
    print("RESEARCH_OUTCOME_SUMMARY " + json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
