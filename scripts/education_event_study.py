"""Event-study pre-screen for H1/H2_TIME_PROXY/H5/H6/H7 using the isolated Stage-1 OHLCV archive.

This is not a full strategy backtest: it has no stop/target execution model, no
slippage series and no complete historical funding series. It reports fixed
forward-return observations after round-trip fees only.
"""
from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

# اجرای مستقیم اسکریپت از پوشه scripts باید ریشه مخزن را برای import ببیند.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq

from app.research_education import (
    ResearchEvent,
    detect_breakout_retests,
    detect_breakout_acceptance,
    detect_liquidity_sweeps,
    detect_value_boundary_rejections,
    filter_events_by_higher_timeframe,
)
from app.signals import Candle

HOUR_MS = 3_600_000
FOUR_HOURS_MS = 4 * HOUR_MS
ROUND_TRIP_FEE = 0.0008  # 0.04% each side, per project cost rule
HORIZONS = (1, 4, 8)


def _to_ms(value: Any) -> int:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    number = int(value)
    if abs(number) >= 10**17:
        return number // 1_000_000
    if abs(number) >= 10**14:
        return number // 1_000
    if abs(number) < 10**11:
        return number * 1000
    return number


def _column(names: list[str], candidates: tuple[str, ...]) -> str:
    lower = {name.lower(): name for name in names}
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    raise ValueError(f"Required parquet column missing; candidates={candidates}; columns={names}")


def load_candles(path: Path) -> list[Candle]:
    table = pq.read_table(path)
    names = table.column_names
    ts_name = _column(names, ("timestamp", "open_time", "time", "datetime", "ts"))
    open_name = _column(names, ("open",))
    high_name = _column(names, ("high",))
    low_name = _column(names, ("low",))
    close_name = _column(names, ("close",))
    volume_name = _column(names, ("volume", "base_volume", "vol"))

    columns = {
        "ts": table[ts_name].to_pylist(),
        "open": table[open_name].to_pylist(),
        "high": table[high_name].to_pylist(),
        "low": table[low_name].to_pylist(),
        "close": table[close_name].to_pylist(),
        "volume": table[volume_name].to_pylist(),
    }
    rows = []
    for i in range(len(columns["ts"])):
        open_time = _to_ms(columns["ts"][i])
        rows.append(
            Candle(
                open_time=open_time,
                open=float(columns["open"][i]),
                high=float(columns["high"][i]),
                low=float(columns["low"][i]),
                close=float(columns["close"][i]),
                volume=float(columns["volume"][i]),
                close_time=open_time + HOUR_MS - 1,
                is_final=True,
            )
        )
    rows.sort(key=lambda c: c.open_time)
    if not rows:
        raise ValueError(f"Empty OHLCV file: {path}")
    if len({c.open_time for c in rows}) != len(rows):
        raise ValueError(f"Duplicate timestamps: {path}")
    if any(rows[i + 1].open_time - rows[i].open_time != HOUR_MS for i in range(len(rows) - 1)):
        raise ValueError(f"Hourly gap or irregular timestamp: {path}")
    for c in rows:
        if (
            not all(math.isfinite(x) for x in (c.open, c.high, c.low, c.close, c.volume))
            or min(c.open, c.high, c.low, c.close) <= 0
            or c.volume < 0
            or c.high < max(c.open, c.close, c.low)
            or c.low > min(c.open, c.close, c.high)
        ):
            raise ValueError(f"Invalid OHLCV row: {path} at {c.open_time}")
    return rows


def resample_4h(hourly: list[Candle]) -> list[Candle]:
    buckets: dict[int, list[Candle]] = defaultdict(list)
    for candle in hourly:
        buckets[candle.open_time // FOUR_HOURS_MS].append(candle)
    result = []
    for key in sorted(buckets):
        group = sorted(buckets[key], key=lambda c: c.open_time)
        if len(group) != 4:
            continue
        if any(group[i + 1].open_time - group[i].open_time != HOUR_MS for i in range(3)):
            continue
        result.append(
            Candle(
                open_time=group[0].open_time,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
                close_time=group[-1].close_time,
                is_final=True,
            )
        )
    return result


def _non_overlapping(events: list[ResearchEvent], gap_bars: int = 8) -> list[ResearchEvent]:
    selected = []
    last_index = -gap_bars
    for event in sorted(events, key=lambda e: e.signal_index):
        if event.signal_index - last_index >= gap_bars:
            selected.append(event)
            last_index = event.signal_index
    return selected


def _ema_series(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    value = sum(values[:period]) / period
    output[period - 1] = value
    alpha = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        value = alpha * values[i] + (1.0 - alpha) * value
        output[i] = value
    return output


def build_event_sets(hourly: list[Candle]) -> dict[str, list[ResearchEvent]]:
    h1 = _non_overlapping(detect_liquidity_sweeps(hourly))
    h2 = _non_overlapping(detect_value_boundary_rejections(hourly))
    h5 = _non_overlapping(detect_breakout_acceptance(hourly))
    h6 = _non_overlapping(detect_breakout_retests(hourly))
    four_hour = resample_4h(hourly)
    four_hour_close_times = [c.close_time for c in four_hour]
    closes = [c.close for c in four_hour]
    fast_values = _ema_series(closes, 20)
    slow_values = _ema_series(closes, 50)
    h7 = []
    for event in h6:
        signal_close = hourly[event.signal_index].close_time
        completed_index = bisect_right(four_hour_close_times, signal_close) - 1
        if completed_index < 49:
            continue
        fast = fast_values[completed_index]
        slow = slow_values[completed_index]
        if fast is None or slow is None:
            continue
        close = closes[completed_index]
        bias = "UP" if close > fast and fast > slow else (
            "DOWN" if close < fast and fast < slow else "NEUTRAL"
        )
        if bias == ("UP" if event.side == "LONG" else "DOWN"):
            h7.append(event)
    # H8 keeps LRT and NMT separate: H1 is the LRT location/confirmation trigger;
    # H5 is the NMT location/price-acceptance trigger. The added gate is only
    # the completed 4h direction check (EMA20/EMA50).
    h8_lrt = filter_events_by_higher_timeframe(h1, hourly, four_hour)
    h8_nmt = filter_events_by_higher_timeframe(h5, hourly, four_hour)
    return {
        "H1": h1,
        "H2_TIME_REJECTION_PROXY": h2,
        "H5_PRICE_PROXY": h5,
        "H6": h6,
        "H7": h7,
        "H8_LRT_DLC": h8_lrt,
        "H8_NMT_DLC": h8_nmt,
    }


def month_add(dt: datetime, months: int) -> datetime:
    index = dt.year * 12 + (dt.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    day = min(dt.day, (datetime(year, month % 12 + 1, 1, tzinfo=timezone.utc) - datetime.resolution).day) if month < 12 else min(dt.day, 31)
    return dt.replace(year=year, month=month, day=day)


def walk_forward_windows(start_ms: int, end_ms: int) -> list[dict[str, int]]:
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    windows = []
    test_start = month_add(start, 6)
    fold = 1
    while True:
        test_end = month_add(test_start, 2)
        if test_end > end:
            break
        train_start = month_add(test_start, -6)
        windows.append({
            "fold": fold,
            "train_start_ms": int(train_start.timestamp() * 1000),
            "test_start_ms": int(test_start.timestamp() * 1000),
            "test_end_ms": int(test_end.timestamp() * 1000),
        })
        fold += 1
        test_start = month_add(test_start, 1)
    return windows


def event_observation(
    event: ResearchEvent,
    candles: list[Candle],
    horizon: int,
) -> dict[str, Any] | None:
    entry_index = event.signal_index + 1
    exit_index = event.signal_index + horizon
    if exit_index >= len(candles):
        return None
    entry = candles[entry_index].open
    exit_price = candles[exit_index].close
    if entry <= 0:
        return None
    direction = 1.0 if event.side == "LONG" else -1.0
    gross = direction * (exit_price / entry - 1.0)
    net_after_fee_only = gross - ROUND_TRIP_FEE
    return {
        "signal_time_ms": candles[event.signal_index].open_time,
        "exit_time_ms": candles[exit_index].close_time,
        "gross_return": gross,
        "net_after_fee_only": net_after_fee_only,
        "win_after_fee_only": net_after_fee_only > 0,
    }


def summarize(observations: list[dict[str, Any]]) -> dict[str, Any]:
    if not observations:
        return {
            "events": 0,
            "mean_gross_return": None,
            "mean_net_after_fee_only": None,
            "median_net_after_fee_only": None,
            "win_rate_after_fee_only": None,
            "status": "INSUFFICIENT_SAMPLE",
        }
    net = sorted(x["net_after_fee_only"] for x in observations)
    n = len(net)
    median = net[n // 2] if n % 2 else (net[n // 2 - 1] + net[n // 2]) / 2
    mean_gross = sum(x["gross_return"] for x in observations) / n
    mean_net = sum(net) / n
    win_rate = sum(bool(x["win_after_fee_only"]) for x in observations) / n
    return {
        "events": n,
        "mean_gross_return": mean_gross,
        "mean_net_after_fee_only": mean_net,
        "median_net_after_fee_only": median,
        "win_rate_after_fee_only": win_rate,
        "status": "DESCRIPTIVE_ONLY",
    }


def run(data_root: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = sorted(data_root.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Parquet files found in {data_root}")

    all_results: dict[str, dict[int, list[dict[str, Any]]]] = {
        hypothesis: {horizon: [] for horizon in HORIZONS}
        for hypothesis in ("H1", "H2_TIME_REJECTION_PROXY", "H5_PRICE_PROXY", "H6", "H7", "H8_LRT_DLC", "H8_NMT_DLC")
    }
    fold_results: dict[str, dict[int, dict[int, list[dict[str, Any]]]]] = {
        hypothesis: {
            horizon: defaultdict(list) for horizon in HORIZONS
        }
        for hypothesis in ("H1", "H2_TIME_REJECTION_PROXY", "H5_PRICE_PROXY", "H6", "H7", "H8_LRT_DLC", "H8_NMT_DLC")
    }

    loaded_symbols = 0
    total_rows = 0
    first_timestamp = None
    last_timestamp = None
    event_counts = defaultdict(int)

    for path in files:
        candles = load_candles(path)
        if len(candles) < 500:
            raise ValueError(f"Insufficient history in {path}: {len(candles)}")
        loaded_symbols += 1
        total_rows += len(candles)
        first_timestamp = candles[0].open_time if first_timestamp is None else min(first_timestamp, candles[0].open_time)
        last_timestamp = candles[-1].close_time if last_timestamp is None else max(last_timestamp, candles[-1].close_time)

        windows = walk_forward_windows(candles[0].open_time, candles[-1].close_time)
        event_sets = build_event_sets(candles)
        for hypothesis, events in event_sets.items():
            event_counts[hypothesis] += len(events)
            for event in events:
                for horizon in HORIZONS:
                    observation = event_observation(event, candles, horizon)
                    if observation is None:
                        continue
                    belongs_to_oos = False
                    for window in windows:
                        if (
                            observation["signal_time_ms"] >= window["test_start_ms"]
                            and observation["exit_time_ms"] < window["test_end_ms"]
                        ):
                            fold_results[hypothesis][horizon][window["fold"]].append(observation)
                            belongs_to_oos = True
                    # جمع‌بندی کلی فقط از رویدادهایی است که داخل حداقل یک پنجره آزمون OOS قرار گرفته‌اند.
                    if belongs_to_oos:
                        all_results[hypothesis][horizon].append(observation)

    overall = {}
    per_fold = {}
    for hypothesis in ("H1", "H2_TIME_REJECTION_PROXY", "H5_PRICE_PROXY", "H6", "H7", "H8_LRT_DLC", "H8_NMT_DLC"):
        overall[hypothesis] = {
            str(h): summarize(all_results[hypothesis][h]) for h in HORIZONS
        }
        per_fold[hypothesis] = {}
        for horizon in HORIZONS:
            per_fold[hypothesis][str(horizon)] = {
                str(fold): summarize(rows)
                for fold, rows in sorted(fold_results[hypothesis][horizon].items())
            }

    return {
        "status": "RESEARCH_PRE_SCREEN_ONLY",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "branch": "market-data",
            "provider": manifest.get("provider"),
            "history_target_years": manifest.get("history_target_years"),
            "manifest_generated_at_utc": manifest.get("generated_at_utc"),
            "manifest_active_symbols": manifest.get("active_symbols"),
            "manifest_successful_symbols": manifest.get("successful_symbols"),
            "loaded_symbols": loaded_symbols,
            "rows": total_rows,
            "first_timestamp_ms": first_timestamp,
            "last_timestamp_ms": last_timestamp,
            "ohlcv_timeframe": "1h",
        },
        "walk_forward": {
            "train_months": 6,
            "test_months": 2,
            "step_months": 1,
            "folds": len(walk_forward_windows(first_timestamp, last_timestamp)),
            "overlapping_test_windows": True,
        },
        "event_counts": dict(event_counts),
        "cost_model": {
            "round_trip_fee": ROUND_TRIP_FEE,
            "fee_basis": "0.04% per side",
            "slippage": "UNAVAILABLE_NOT_INCLUDED",
            "funding": "UNAVAILABLE_FOR_FULL_2Y_WINDOW_NOT_INCLUDED",
            "status": "PARTIAL_COST_ONLY",
        },
        "metrics": overall,
        "walk_forward_metrics": per_fold,
        "limitations": [
            "This is a forward-return event study, not a complete trade simulation.",
            "No stop-loss, take-profit, partial-fill, liquidation or portfolio overlap model is applied.",
            "Returns subtract exchange fees only; slippage and funding are unavailable for the full historical window.",
            "No DSR, PBO, Sharpe, profit factor or drawdown PASS is claimed from this event study.",
            "H2_TIME_REJECTION_PROXY uses a rolling 24-hour OHLCV range and two completed closes back inside; it is not a real volume profile or VAH/VAL.",
            "H5_PRICE_PROXY measures consecutive price closes only; it does not use real aggressor flow or delta.",
            "H7 is an H6 breakout-retest subset filtered by completed 4h EMA20/EMA50 direction.",
            "H8_LRT_DLC filters H1 sweep/reclaim events by completed 4h EMA20/EMA50 direction; H8_NMT_DLC separately filters H5 price-acceptance events. No LRT/NMT triggers are blended.",
            "The rolling 2-month test windows overlap by one month; fold results must be inspected separately.",
            "No threshold was tuned on test windows; no strategy is promoted by this pre-screen.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.data_root, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "loaded_symbols": result["dataset"]["loaded_symbols"],
        "rows": result["dataset"]["rows"],
        "event_counts": result["event_counts"],
        "cost_status": result["cost_model"]["status"],
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
