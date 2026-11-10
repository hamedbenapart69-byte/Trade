"""Walk-forward validation of the current EMA20/EMA50 + ATR14 MVP.

This is a research harness, not a profitability claim. It uses next-bar-open
entries, conservative same-bar stop handling, 0.04% fee and 0.02% slippage
per side. Historical funding is explicitly marked unavailable in this first
baseline report because the archived series covers only the latest ~94 days.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


FEE_PER_SIDE = 0.0004
SLIPPAGE_PER_SIDE = 0.0002
TRAIN_HOURS = 6 * 30 * 24
TEST_HOURS = 2 * 30 * 24
STEP_HOURS = 30 * 24
SIGNAL_SCAN_INTERVAL_HOURS = 4


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [sum(values[:period]) / period]
    for value in values[period:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def atr_series(rows: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    tr: list[float] = []
    for i, row in enumerate(rows):
        if i == 0:
            tr.append(float(row["high"]) - float(row["low"]))
        else:
            previous = float(rows[i - 1]["close"])
            high, low = float(row["high"]), float(row["low"])
            tr.append(max(high - low, abs(high - previous), abs(low - previous)))
    result: list[float | None] = [None] * len(rows)
    if len(rows) < period:
        return result
    current = sum(tr[:period]) / period
    result[period - 1] = current
    for i in range(period, len(rows)):
        current = ((current * (period - 1)) + tr[i]) / period
        result[i] = current
    return result


def _trade_result(position: dict[str, Any], exit_time: int, exit_price: float,
                  reason: str, remaining_fraction: float,
                  target_triggers: list[str] | None = None) -> dict[str, Any]:
    side_sign = 1.0 if position["side"] == "LONG" else -1.0
    gross = position["realized_gross_pct"]
    if remaining_fraction > 0:
        gross += remaining_fraction * side_sign * (exit_price / position["entry"] - 1.0)
    round_trip_fee = 2.0 * FEE_PER_SIDE
    round_trip_slippage = 2.0 * SLIPPAGE_PER_SIDE
    round_trip_cost = round_trip_fee + round_trip_slippage
    net_pct = gross - round_trip_cost
    risk_pct = abs(position["entry"] - position["stop"]) / position["entry"]
    net_r = net_pct / risk_pct if risk_pct > 0 else 0.0
    stop_triggered = reason.startswith("STOP")
    return {
        "symbol": position["symbol"],
        "side": position["side"],
        "signal_time": position["signal_time"],
        "order_decision_time": position["order_decision_time"],
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "entry": position["entry"],
        "entry_fill_price": position["entry"],
        "exit": exit_price,
        "exit_fill_price": exit_price,
        "fill_price_model": "NEXT_BAR_OPEN_ENTRY_OHLCV_BAR_EXIT",
        "exit_time_precision": "OHLCV_BAR_TIMESTAMP_ONLY",
        "stop": position["stop"],
        "stop_trigger": position["stop"] if stop_triggered else None,
        "target_triggers": target_triggers or [],
        "tp1": position["tp1"],
        "tp2": position["tp2"],
        "gross_return_pct": gross * 100.0,
        "entry_fee_pct": FEE_PER_SIDE * 100.0,
        "exit_fee_pct": FEE_PER_SIDE * 100.0,
        "round_trip_fee_pct": round_trip_fee * 100.0,
        "slippage_per_side_pct": SLIPPAGE_PER_SIDE * 100.0,
        "round_trip_slippage_pct": round_trip_slippage * 100.0,
        "spread_cost_pct": "UNAVAILABLE",
        "market_impact_cost_pct": "UNAVAILABLE",
        "cost_return_pct": round_trip_cost * 100.0,
        "net_return_pct": net_pct * 100.0,
        "net_r": net_r,
        "exit_reason": reason,
        "position_duration_ms": max(0, int(exit_time) - int(position["entry_time"])),
        "partial_fill_assumption": "50% at TP1 and 50% at TP2",
        "latency_assumption": "NEXT_BAR_OPEN; additional latency unavailable",
        "liquidity_constraints": "UNAVAILABLE",
        "funding_cost": "UNAVAILABLE",
    }


def backtest_window(symbol: str, rows: list[dict[str, Any]], start_index: int = 50) -> list[dict[str, Any]]:
    """تست بدون نگاه به آینده؛ تصمیم در close و ورود در open کندل بعد."""
    if len(rows) < 80:
        return []
    closes = [float(row["close"]) for row in rows]
    fast = ema(closes, 20)
    slow = ema(closes, 50)
    atrs = atr_series(rows, 14)
    # EMA arrays begin at their warm-up offsets.
    fast_by_index = {i + 19: value for i, value in enumerate(fast)}
    slow_by_index = {i + 49: value for i, value in enumerate(slow)}
    trades: list[dict[str, Any]] = []
    position: dict[str, Any] | None = None
    i = max(50, start_index)

    while i < len(rows):
        candle = rows[i]
        if position is None:
            if i >= len(rows) - 1:
                break
            # هم‌تراز با Cron واقعی: هر ۴ ساعت پس از بسته‌شدن کندل 1H.
            completed_hour = int(candle["timestamp"]) // 3_600_000 + 1
            if completed_hour % SIGNAL_SCAN_INTERVAL_HOURS != 0:
                i += 1
                continue
            f = fast_by_index.get(i)
            s = slow_by_index.get(i)
            a = atrs[i]
            if f is None or s is None or a is None or a <= 0:
                i += 1
                continue
            spread = abs(f - s) / max(abs(s), 1e-12)
            if spread <= 0.005:
                i += 1
                continue
            side = "LONG" if f > s else "SHORT"
            entry_bar = rows[i + 1]
            entry = float(entry_bar["open"])
            risk_distance = 1.5 * a
            if side == "LONG":
                stop, tp1, tp2 = entry - risk_distance, entry + 2.0 * a, entry + 4.0 * a
            else:
                stop, tp1, tp2 = entry + risk_distance, entry - 2.0 * a, entry - 4.0 * a
            if stop <= 0 or entry <= 0:
                i += 1
                continue
            position = {
                "symbol": symbol, "side": side,
                "signal_time": int(candle["timestamp"]) + 3_600_000,
                "order_decision_time": int(candle["timestamp"]) + 3_600_000,
                "entry_time": int(entry_bar["timestamp"]),
                "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2,
                "tp1_done": False, "realized_gross_pct": 0.0,
            }
            i += 1
            continue

        high, low = float(candle["high"]), float(candle["low"])
        long_side = position["side"] == "LONG"
        stop_hit = low <= position["stop"] if long_side else high >= position["stop"]
        tp1_hit = high >= position["tp1"] if long_side else low <= position["tp1"]
        tp2_hit = high >= position["tp2"] if long_side else low <= position["tp2"]

        # اگر SL و هر TP در یک کندل دیده شوند، ترتیب نامعلوم است؛ بدترین حالت یعنی SL.
        if stop_hit and (tp1_hit or tp2_hit):
            trades.append(_trade_result(
                position, int(candle["timestamp"]), position["stop"],
                "STOP_SAME_BAR_AMBIGUITY",
                1.0 if not position["tp1_done"] else 0.5,
                [name for name, hit in (("TP1", tp1_hit), ("TP2", tp2_hit)) if hit],
            ))
            position = None
        elif stop_hit:
            trades.append(_trade_result(
                position, int(candle["timestamp"]), position["stop"], "STOP",
                1.0 if not position["tp1_done"] else 0.5,
            ))
            position = None
        else:
            if tp1_hit and not position["tp1_done"]:
                sign = 1.0 if long_side else -1.0
                position["realized_gross_pct"] += 0.5 * sign * (
                    position["tp1"] / position["entry"] - 1.0
                )
                position["tp1_done"] = True
            if tp2_hit:
                sign = 1.0 if long_side else -1.0
                position["realized_gross_pct"] += 0.5 * sign * (
                    position["tp2"] / position["entry"] - 1.0
                )
                trades.append(_trade_result(
                    position, int(candle["timestamp"]), position["tp2"], "TP2", 0.0,
                    [name for name, hit in (("TP1", tp1_hit), ("TP2", tp2_hit)) if hit],
                ))
                position = None
        i += 1

    if position is not None:
        last = rows[-1]
        trades.append(_trade_result(position, int(last["timestamp"]),
                                    float(last["close"]), "END_OF_TEST_WINDOW",
                                    1.0 if not position["tp1_done"] else 0.5))
    return trades


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"trades": 0, "win_rate_pct": None, "profit_factor": None,
                "max_drawdown_pct": None, "expectancy_r": None}
    wins = [float(t["net_r"]) for t in trades if float(t["net_r"]) > 0]
    losses = [float(t["net_r"]) for t in trades if float(t["net_r"]) < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    equity = peak = 1.0
    max_dd = 0.0
    for trade in sorted(trades, key=lambda t: (t["exit_time"], t["symbol"])):
        equity *= max(0.0, 1.0 + 0.01 * float(trade["net_r"]))
        peak = max(peak, equity)
        if peak:
            max_dd = max(max_dd, (peak - equity) / peak)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100.0 * len(wins) / len(trades), 2),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "expectancy_r": round(sum(float(t["net_r"]) for t in trades) / len(trades), 4),
        "note": "Trade-sequence proxy; not a concurrency-aware portfolio drawdown.",
    }


def walk_forward_symbol(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trades_by_entry: dict[int, dict[str, Any]] = {}
    test_start = TRAIN_HOURS
    while test_start + TEST_HOURS < len(rows):
        warm_start = max(0, test_start - 80)
        window = rows[warm_start:test_start + TEST_HOURS]
        for trade in backtest_window(symbol, window, start_index=test_start - warm_start):
            if int(rows[test_start]["timestamp"]) <= trade["entry_time"] < int(rows[test_start + TEST_HOURS]["timestamp"]):
                trades_by_entry.setdefault(int(trade["entry_time"]), trade)
        test_start += STEP_HOURS
    return list(trades_by_entry.values())


def run_validation(data_dir: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    all_trades: list[dict[str, Any]] = []
    symbols_seen = 0
    files = sorted(data_dir.glob("*.parquet"))
    for path in files:
        table = pq.read_table(path)
        rows = table.to_pylist()
        normalized = []
        for row in rows:
            normalized.append({
                "timestamp": int(row.get("timestamp", row.get("ts", 0))),
                "open": float(row["open"]), "high": float(row["high"]),
                "low": float(row["low"]), "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
            })
        normalized.sort(key=lambda r: r["timestamp"])
        if len(normalized) < TRAIN_HOURS + TEST_HOURS + 80:
            continue
        symbol = path.stem.replace("-USDT-SWAP", "")
        symbol_trades = walk_forward_symbol(symbol, normalized)
        all_trades.extend(symbol_trades)
        symbols_seen += 1

    summary = metrics(all_trades)
    return {
        "stage": "MVP_BASELINE_WALK_FORWARD",
        "version": "v1_exact_ema20_ema50_atr14_rule",
        "data_source": "OKX public perpetual OHLCV Parquet",
        "timeframe": "1H",
        "walk_forward": {
            "train_months": 6, "test_months": 2, "step_months": 1,
            "signal_scan_interval_hours": SIGNAL_SCAN_INTERVAL_HOURS,
            "oos_only_metrics": True,
        },
        "costs": {
            "fee_per_side_pct": FEE_PER_SIDE * 100.0,
            "slippage_per_side_pct": SLIPPAGE_PER_SIDE * 100.0,
            "slippage_label": "PROXY",
            "funding": "UNAVAILABLE_FOR_FULL_TWO_YEAR_WINDOW",
        },
        "coverage": {"symbols_with_data": symbols_seen, "parquet_files_found": len(files)},
        "oos_metrics": summary,
        "calibration": "NOT_CALIBRATED",
        "dsr": "UNAVAILABLE",
        "pbo": "UNAVAILABLE",
        "gate_status": "BLOCKED: funding history incomplete; DSR/PBO and baseline comparison not yet implemented",
        "interpretation": "Research evidence only. This report cannot establish profitability or authorize promotion to live signals.",
        "trades": all_trades,
    }
