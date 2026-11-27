"""Futures-data validation of the fixed-universe Momentum + Cash weekly strategy.

Research-only USD-M perpetual test. Uses Binance Vision daily futures klines and
historical funding-rate archives; verifies every archive SHA-256 checksum.
BTC is a regime benchmark, never tradable.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import math
import re
import time

import numpy as np
import pandas as pd
import requests

from momentum_cash_backtest import (
    ASSETS, BTC, MIN_ELIGIBLE_ASSETS, TOP_N, WARMUP_OBSERVATIONS,
    ROUND_TRIP_COST, WEEKS_PER_YEAR, add_features, zscore, metrics, month_range, month_of,
)

BASE = "https://data.binance.vision/data/futures/um"
SCAN_START = "2019-01"
TIMEOUT = (12, 45)
MAX_WORKERS = 24
GAP_TOLERANCE_HOURS = 0.35


def archive_url(kind: str, symbol: str, month: str) -> str:
    if kind == "klines":
        return f"{BASE}/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"
    if kind == "funding_rate":
        return f"{BASE}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    raise ValueError(f"unknown archive kind: {kind}")


def head_exists(url: str) -> bool:
    for attempt in range(3):
        try:
            response = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code == 404:
                return False
            return response.status_code == 200
        except requests.RequestException:
            if attempt == 2:
                return False
            time.sleep(0.5 * (attempt + 1))
    return False


def first_archive_month(symbol: str, kind: str, months: list[str]) -> str:
    for month in months:
        if head_exists(archive_url(kind, symbol, month)):
            return month
    raise RuntimeError(f"D1_ARCHIVE_NOT_FOUND: {kind}:{symbol}")


def fetch_verified_archive(symbol: str, kind: str, month: str) -> tuple[bytes, str]:
    url = archive_url(kind, symbol, month)
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=TIMEOUT)
            if response.status_code == 404:
                raise RuntimeError(f"D1_DATA_GAP: missing {kind} archive {symbol} {month}")
            response.raise_for_status()
            checksum_response = requests.get(url + ".CHECKSUM", timeout=TIMEOUT)
            checksum_response.raise_for_status()
            match = re.search(r"\b([a-fA-F0-9]{64})\b", checksum_response.text)
            if not match:
                raise RuntimeError(f"D1_CHECKSUM_MISSING: {kind}:{symbol}:{month}")
            expected = match.group(1).lower()
            actual = sha256(response.content).hexdigest()
            if actual != expected:
                raise RuntimeError(f"D1_CHECKSUM_MISMATCH: {kind}:{symbol}:{month}")
            return response.content, actual
        except RuntimeError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"D1_DOWNLOAD_FAILED: {kind}:{symbol}:{month}:{type(last_error).__name__}")


def csv_from_zip(payload: bytes, label: str) -> pd.DataFrame:
    with ZipFile(BytesIO(payload)) as archive:
        csvs = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise RuntimeError(f"D1_ARCHIVE_LAYOUT_INVALID: {label}:{csvs}")
        with archive.open(csvs[0]) as stream:
            frame = pd.read_csv(stream)
    if frame.empty:
        raise RuntimeError(f"D1_EMPTY_ARCHIVE: {label}")
    return frame


def raw_csv_from_zip(payload: bytes, label: str) -> bytes:
    with ZipFile(BytesIO(payload)) as archive:
        csvs = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csvs) != 1:
            raise RuntimeError(f"D1_ARCHIVE_LAYOUT_INVALID: {label}:{csvs}")
        return archive.read(csvs[0])


def parse_kline_archive(payload: bytes, label: str) -> pd.DataFrame:
    raw = raw_csv_from_zip(payload, label)
    headered = pd.read_csv(BytesIO(raw))
    required = {"open_time", "open", "high", "low", "close", "volume"}
    if required.issubset(headered.columns):
        frame = headered.rename(columns={"quote_volume": "quote_asset_volume", "count": "number_of_trades"})
        layout = "HEADERED_STANDARD"
    else:
        raw_frame = pd.read_csv(BytesIO(raw), header=None)
        if raw_frame.shape[1] != 12:
            raise RuntimeError(f"D1_KLINE_COLUMN_COUNT_INVALID: {label}:{raw_frame.shape[1]}")
        numeric = raw_frame.apply(pd.to_numeric, errors="coerce")
        # Some early USD-M monthly archives are headerless and use a legacy
        # field order: ignore, trades, open_time, close_time, taker-buy quote,
        # taker-buy base, quote volume, base volume, low, open, close, high.
        legacy_open_time = numeric.iloc[:, 2]
        legacy_close_time = numeric.iloc[:, 3]
        legacy_delta = legacy_close_time - legacy_open_time
        legacy_timestamp = (
            legacy_open_time.notna().mean() > 0.999 and
            legacy_open_time.median() > 1e11 and
            legacy_close_time.median() > 1e11 and
            (legacy_delta.between(86_399_000, 86_401_000)).mean() > 0.999
        )
        standard_open_time = numeric.iloc[:, 0]
        standard_close_time = numeric.iloc[:, 6]
        standard_delta = standard_close_time - standard_open_time
        standard_timestamp = (
            standard_open_time.notna().mean() > 0.999 and
            standard_open_time.median() > 1e11 and
            standard_close_time.median() > 1e11 and
            (standard_delta.between(86_399_000, 86_401_000)).mean() > 0.999
        )
        if legacy_timestamp:
            frame = pd.DataFrame({
                "open_time": numeric.iloc[:, 2],
                "close_time": numeric.iloc[:, 3],
                "quote_asset_volume": numeric.iloc[:, 6],
                "volume": numeric.iloc[:, 7],
                "number_of_trades": numeric.iloc[:, 1],
                "taker_buy_quote_asset_volume": numeric.iloc[:, 4],
                "taker_buy_base_asset_volume": numeric.iloc[:, 5],
                "low": numeric.iloc[:, 8],
                "open": numeric.iloc[:, 9],
                "close": numeric.iloc[:, 10],
                "high": numeric.iloc[:, 11],
            })
            layout = "HEADERLESS_LEGACY_UM_2020"
        elif standard_timestamp:
            frame = pd.DataFrame({
                "open_time": numeric.iloc[:, 0],
                "open": numeric.iloc[:, 1],
                "high": numeric.iloc[:, 2],
                "low": numeric.iloc[:, 3],
                "close": numeric.iloc[:, 4],
                "volume": numeric.iloc[:, 5],
                "close_time": numeric.iloc[:, 6],
                "quote_asset_volume": numeric.iloc[:, 7],
                "number_of_trades": numeric.iloc[:, 8],
                "taker_buy_base_asset_volume": numeric.iloc[:, 9],
                "taker_buy_quote_asset_volume": numeric.iloc[:, 10],
            })
            layout = "HEADERLESS_STANDARD"
        else:
            raise RuntimeError(f"D1_KLINE_TIMESTAMP_LAYOUT_INVALID: {label}")

    timestamp = pd.to_numeric(frame["open_time"], errors="coerce")
    valid = timestamp[np.isfinite(timestamp)]
    if valid.empty:
        raise RuntimeError(f"D1_KLINE_TIMESTAMP_MISSING: {label}")
    median = float(valid.median())
    unit = "us" if median >= 1e14 else "ms" if median >= 1e11 else "s" if median >= 1e8 else None
    if unit is None:
        raise RuntimeError(f"D1_KLINE_TIMESTAMP_UNIT_UNKNOWN: {label}")
    frame["date"] = pd.to_datetime(timestamp, unit=unit, utc=True).dt.floor("D")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    result = frame[["date", "open", "high", "low", "close", "volume"]].dropna()
    result = result.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    valid_ohlc = (
        (result["low"] > 0) &
        (result["high"] >= result["low"]) &
        (result["open"] >= result["low"]) & (result["open"] <= result["high"]) &
        (result["close"] >= result["low"]) & (result["close"] <= result["high"]) &
        (result["volume"] >= 0)
    )
    if result.empty or not bool(valid_ohlc.all()):
        raise RuntimeError(f"D1_KLINE_OHLC_OR_VOLUME_INVALID: {label}:{layout}")
    result.attrs["schema_layout"] = layout
    return result


def parse_funding_archive(payload: bytes, label: str) -> pd.DataFrame:
    frame = csv_from_zip(payload, label)
    required = {"calc_time", "funding_interval_hours", "last_funding_rate"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"D1_FUNDING_SCHEMA_INVALID: {label}:{sorted(frame.columns)}")
    timestamp = pd.to_numeric(frame["calc_time"], errors="coerce")
    valid = timestamp[np.isfinite(timestamp)]
    if valid.empty:
        raise RuntimeError(f"D1_FUNDING_TIMESTAMP_MISSING: {label}")
    median = float(valid.median())
    unit = "us" if median >= 1e14 else "ms" if median >= 1e11 else "s" if median >= 1e8 else None
    if unit is None:
        raise RuntimeError(f"D1_FUNDING_TIMESTAMP_UNIT_UNKNOWN: {label}")
    frame["time"] = pd.to_datetime(timestamp, unit=unit, utc=True)
    frame["funding_interval_hours"] = pd.to_numeric(frame["funding_interval_hours"], errors="coerce")
    frame["last_funding_rate"] = pd.to_numeric(frame["last_funding_rate"], errors="coerce")
    result = frame[["time", "funding_interval_hours", "last_funding_rate"]].dropna()
    result = result.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    if result.empty or (result["funding_interval_hours"] <= 0).any():
        raise RuntimeError(f"D1_FUNDING_VALUES_INVALID: {label}")
    return result


def download_dataset(symbols: list[str], kind: str, months: list[str]) -> tuple[dict, dict]:
    first_months: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(symbols))) as pool:
        futures = {pool.submit(first_archive_month, symbol, kind, months): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            first_months[symbol] = future.result()

    tasks = [
        (symbol, month)
        for symbol in symbols
        for month in months
        if month >= first_months[symbol]
    ]
    parts: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in symbols}
    archive_manifest: dict[str, list[dict]] = {symbol: [] for symbol in symbols}

    def fetch_one(item: tuple[str, str]):
        symbol, month = item
        payload, checksum = fetch_verified_archive(symbol, kind, month)
        label = f"{symbol}:{month}:{kind}"
        parsed = parse_kline_archive(payload, label) if kind == "klines" else parse_funding_archive(payload, label)
        schema_layout = parsed.attrs.get("schema_layout", "FUNDING_RATE_HEADERED")
        return symbol, month, checksum, parsed, schema_layout

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(fetch_one, item) for item in tasks]
        for future in as_completed(futures):
            symbol, month, checksum, parsed, schema_layout = future.result()
            parts[symbol].append(parsed)
            archive_manifest[symbol].append({
                "month": month, "sha256": checksum, "checksum_verified": True,
                "schema_layout": schema_layout,
            })

    datasets: dict[str, pd.DataFrame] = {}
    coverage: dict[str, dict] = {}
    for symbol in symbols:
        frame = pd.concat(parts[symbol], ignore_index=True)
        time_column = "date" if kind == "klines" else "time"
        frame = frame.drop_duplicates(time_column).sort_values(time_column).reset_index(drop=True)
        datasets[symbol] = frame
        coverage[symbol] = {
            "first_archive_month": first_months[symbol],
            "last_archive_month": months[-1],
            "archive_count": len(archive_manifest[symbol]),
            "row_count": int(len(frame)),
            "first_observation_utc": frame[time_column].iloc[0].isoformat(),
            "last_observation_utc": frame[time_column].iloc[-1].isoformat(),
            "all_archive_checksums_verified": all(x["checksum_verified"] for x in archive_manifest[symbol]),
            "archives": sorted(archive_manifest[symbol], key=lambda x: x["month"]),
        }
    return datasets, {"first_archive_month_by_symbol": first_months, "coverage": coverage}


def funding_window(frame: pd.DataFrame, monday: pd.Timestamp, friday: pd.Timestamp) -> tuple[float, bool, int, str]:
    if frame is None or frame.empty:
        return 0.0, False, 0, "NO_FUNDING_HISTORY"
    close_time = friday + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    times = frame["time"].astype("int64").to_numpy()
    start_ns = monday.value
    end_ns = close_time.value
    left = int(np.searchsorted(times, start_ns, side="right"))
    right = int(np.searchsorted(times, end_ns, side="right"))
    prior_index = left - 1
    if prior_index < 0 or right <= left:
        return 0.0, False, 0, "FUNDING_WINDOW_NOT_COVERED"
    window = frame.iloc[left:right].reset_index(drop=True)
    previous = frame.iloc[prior_index]
    first_gap = (window.iloc[0]["time"] - monday).total_seconds() / 3600.0
    previous_interval = float(previous["funding_interval_hours"])
    if not np.isfinite(previous_interval) or previous_interval <= 0:
        return 0.0, False, int(len(window)), "FUNDING_INTERVAL_INVALID"
    complete = first_gap <= previous_interval * 1.5
    previous_time = previous["time"]
    previous_interval_hours = previous_interval
    for _, event in window.iterrows():
        gap_hours = (event["time"] - previous_time).total_seconds() / 3600.0
        tolerance = max(GAP_TOLERANCE_HOURS, previous_interval_hours * 0.05)
        if not np.isfinite(previous_interval_hours) or abs(gap_hours - previous_interval_hours) > tolerance:
            complete = False
            break
        previous_time = event["time"]
        previous_interval_hours = float(event["funding_interval_hours"])
    trailing_gap = (close_time - window.iloc[-1]["time"]).total_seconds() / 3600.0
    if trailing_gap > float(window.iloc[-1]["funding_interval_hours"]) * 1.5:
        complete = False
    rate_sum = float(window["last_funding_rate"].sum())
    return rate_sum, bool(complete), int(len(window)), "OK" if complete else "FUNDING_SCHEDULE_GAP"


def weekly_panel(frames: dict[str, pd.DataFrame], btc: pd.DataFrame,
                 funding: dict[str, pd.DataFrame], cutoff: date) -> list[dict]:
    indexed = {symbol: frame.set_index("date") for symbol, frame in frames.items()}
    btc_i = btc.set_index("date").copy()
    btc_i["sma50"] = btc_i["close"].rolling(50, min_periods=50).mean()
    earliest = min(frame["date"].min() for frame in frames.values())
    first_monday = earliest + pd.Timedelta(days=(7 - earliest.weekday()) % 7)
    last = pd.Timestamp(cutoff, tz="UTC")
    mondays = pd.date_range(first_monday, last - pd.Timedelta(days=4), freq="W-MON", tz="UTC")
    rows: list[dict] = []
    for monday in mondays:
        prior = monday - pd.Timedelta(days=1)
        friday = monday + pd.Timedelta(days=4)
        eligible: list[str] = []
        features: dict[str, tuple[float, float]] = {}
        returns: dict[str, float] = {}
        for symbol in ASSETS:
            f = indexed[symbol]
            if prior not in f.index or monday not in f.index or friday not in f.index:
                continue
            prior_row, monday_row, friday_row = f.loc[prior], f.loc[monday], f.loc[friday]
            if isinstance(prior_row, pd.DataFrame): prior_row = prior_row.iloc[-1]
            if isinstance(monday_row, pd.DataFrame): monday_row = monday_row.iloc[-1]
            if isinstance(friday_row, pd.DataFrame): friday_row = friday_row.iloc[-1]
            if int(prior_row["observations_since_inception"]) < WARMUP_OBSERVATIONS:
                continue
            volume_z, rsi = float(prior_row["volume_z20"]), float(prior_row["rsi14"])
            if not np.isfinite(volume_z) or not np.isfinite(rsi):
                continue
            eligible.append(symbol)
            features[symbol] = (volume_z, rsi)
            returns[symbol] = float(friday_row["close"] / monday_row["open"] - 1.0)

        regime = None
        if prior in btc_i.index:
            benchmark = btc_i.loc[prior]
            if isinstance(benchmark, pd.DataFrame): benchmark = benchmark.iloc[-1]
            if pd.notna(benchmark["sma50"]):
                regime = bool(float(benchmark["close"]) > float(benchmark["sma50"]))

        scores: dict[str, float] = {}
        if regime is True and len(eligible) >= MIN_ELIGIBLE_ASSETS:
            volume = pd.Series({symbol: features[symbol][0] for symbol in eligible})
            rsi = pd.Series({symbol: features[symbol][1] for symbol in eligible})
            zv, zr = zscore(volume), zscore(rsi)
            if zv.notna().all() and zr.notna().all():
                composite = 0.5 * zv + 0.5 * zr
                scores = {symbol: float(composite[symbol]) for symbol in eligible}
        ranked = sorted(scores, key=lambda symbol: (-scores[symbol], symbol))
        top2 = ranked[:TOP_N] if len(ranked) >= MIN_ELIGIBLE_ASSETS else []
        funding_sums: dict[str, float] = {}
        funding_complete: dict[str, bool] = {}
        funding_counts: dict[str, int] = {}
        funding_reasons: dict[str, str] = {}
        for symbol in top2:
            total, complete, count, reason = funding_window(funding.get(symbol), monday, friday)
            funding_sums[symbol] = total
            funding_complete[symbol] = complete
            funding_counts[symbol] = count
            funding_reasons[symbol] = reason
        rows.append({
            "monday": monday, "friday": friday, "year": int(monday.year),
            "eligible_assets": eligible, "scores": scores, "top2": top2,
            "asset_returns": returns, "btc_bull_regime": regime,
            "funding_sums": funding_sums, "funding_complete": funding_complete,
            "funding_event_counts": funding_counts, "funding_reasons": funding_reasons,
        })
    return rows


def extended_metrics(returns: list[float], invested_mask: list[bool] | None = None) -> dict:
    result = metrics(returns)
    values = np.asarray(returns, dtype=float)
    active = values if invested_mask is None else values[np.asarray(invested_mask, dtype=bool)]
    result["win_rate"] = round(float(np.mean(active > 0.0)), 8) if len(active) else None
    result["invested_sample_count"] = int(len(active))
    result["average_weekly_return"] = round(float(np.mean(values)), 10) if len(values) else None
    result["average_invested_week_return"] = round(float(np.mean(active)), 10) if len(active) else None
    return result


def evaluate(panel: list[dict]) -> dict:
    by_year: dict[int, list[dict]] = {}
    all_rows: list[dict] = []
    cash_reasons = {
        "BTC_AT_OR_BELOW_SMA50": 0, "BTC_SMA50_UNAVAILABLE": 0,
        "INSUFFICIENT_ELIGIBLE_ASSETS": 0, "FEATURE_CROSS_SECTION_INVALID": 0,
        "FUNDING_DATA_UNAVAILABLE": 0,
    }
    for row in panel:
        chosen = list(row["top2"])
        if row["btc_bull_regime"] is False:
            reason = "BTC_AT_OR_BELOW_SMA50"
        elif row["btc_bull_regime"] is None:
            reason = "BTC_SMA50_UNAVAILABLE"
        elif len(row["eligible_assets"]) < MIN_ELIGIBLE_ASSETS:
            reason = "INSUFFICIENT_ELIGIBLE_ASSETS"
        elif not row["scores"] or len(chosen) != TOP_N:
            reason = "FEATURE_CROSS_SECTION_INVALID"
        elif not all(row["funding_complete"].get(symbol, False) for symbol in chosen):
            reason = "FUNDING_DATA_UNAVAILABLE"
        else:
            reason = "INVESTED_LONG_TOP2"

        if reason == "INVESTED_LONG_TOP2":
            gross = float(np.mean([row["asset_returns"][symbol] for symbol in chosen]))
            funding_cost = float(np.mean([row["funding_sums"][symbol] for symbol in chosen]))
            trading_cost = ROUND_TRIP_COST
            net = gross - trading_cost - funding_cost
        else:
            gross = funding_cost = trading_cost = net = 0.0
            chosen = []
            cash_reasons[reason] += 1

        item = {
            "monday": row["monday"], "friday": row["friday"], "year": row["year"],
            "state": reason, "selected_assets": chosen,
            "gross_return": gross, "trading_cost": trading_cost,
            "funding_cost": funding_cost, "net_return": net,
            "funding_event_counts": row["funding_event_counts"],
            "funding_reasons": row["funding_reasons"],
        }
        all_rows.append(item)
        by_year.setdefault(row["year"], []).append(item)

    yearly = {}
    for year, rows in sorted(by_year.items()):
        returns = [item["net_return"] for item in rows]
        invested = sum(item["state"] == "INVESTED_LONG_TOP2" for item in rows)
        yearly[str(year)] = {
            "metrics": extended_metrics(returns, [item["state"] == "INVESTED_LONG_TOP2" for item in rows]),
            "invested_weeks": invested, "cash_weeks": len(rows) - invested,
            "cash_pct": round(100.0 * (len(rows) - invested) / len(rows), 6) if rows else None,
            "funding_cost_sum": round(float(sum(item["funding_cost"] for item in rows)), 10),
            "trading_cost_sum": round(float(sum(item["trading_cost"] for item in rows)), 10),
        }

    returns = [item["net_return"] for item in all_rows]
    invested = sum(item["state"] == "INVESTED_LONG_TOP2" for item in all_rows)
    total = len(all_rows)
    return {
        "strategy": "MOMENTUM_CASH_LONG_TOP2_WITH_REAL_FUNDING",
        "year_by_year": yearly,
        "entire_period": {
            "start_monday": str(all_rows[0]["monday"].date()) if all_rows else None,
            "end_friday": str(all_rows[-1]["friday"].date()) if all_rows else None,
            "metrics": extended_metrics(returns, [item["state"] == "INVESTED_LONG_TOP2" for item in all_rows]),
            "invested_weeks": invested, "cash_weeks": total - invested,
            "cash_pct": round(100.0 * (total - invested) / total, 6) if total else None,
            "cash_reason_counts": cash_reasons,
            "funding_cost_sum": round(float(sum(item["funding_cost"] for item in all_rows)), 10),
            "trading_cost_sum": round(float(sum(item["trading_cost"] for item in all_rows)), 10),
            "cash_time_definition": "Share of non-overlapping Monday-open-to-Friday-close weekly windows with zero exposure; includes regime, feature, eligibility and funding-data cash.",
        },
        "weekly_results": all_rows,
    }


def dsr_z_single_trial(returns: list[float]) -> float | None:
    values = np.asarray(returns, dtype=float)
    if len(values) < 30:
        return None
    sigma = float(np.std(values, ddof=1))
    if sigma <= 1e-15:
        return None
    mean = float(np.mean(values))
    centered = values - mean
    sharpe_period = mean / sigma
    skew = float(np.mean(centered ** 3) / sigma ** 3)
    kurtosis = float(np.mean(centered ** 4) / sigma ** 4)
    variance = (1.0 / (len(values) - 1)) * (
        1.0 + 0.5 * sharpe_period ** 2 - skew * sharpe_period
        + ((kurtosis - 3.0) / 4.0) * sharpe_period ** 2
    )
    if variance <= 0 or not np.isfinite(variance):
        return None
    return float(sharpe_period / math.sqrt(variance))


def walk_forward(results: list[dict]) -> dict:
    if not results:
        return {"status": "UNAVAILABLE", "reason": "NO_WEEKLY_RESULTS"}
    first = pd.Timestamp(results[0]["monday"])
    last = pd.Timestamp(results[-1]["friday"]) + pd.Timedelta(days=1)
    cursor = first + pd.DateOffset(months=6)
    cursor += pd.Timedelta(days=(7 - cursor.weekday()) % 7)
    assigned: dict[str, dict] = {}
    folds = []
    while cursor + pd.DateOffset(months=2) <= last:
        test_end = cursor + pd.DateOffset(months=2)
        fold_rows = [row for row in results if cursor <= pd.Timestamp(row["monday"]) < test_end]
        if fold_rows:
            fold_returns = [row["net_return"] for row in fold_rows]
            fold_invested = [row["state"] == "INVESTED_LONG_TOP2" for row in fold_rows]
            folds.append({
                "train_start": (cursor - pd.DateOffset(months=6)).date().isoformat(),
                "train_end": (cursor - pd.Timedelta(days=1)).date().isoformat(),
                "test_start": cursor.date().isoformat(),
                "test_end_exclusive": test_end.date().isoformat(),
                "metrics": extended_metrics(fold_returns, fold_invested),
            })
            for row in fold_rows:
                assigned.setdefault(pd.Timestamp(row["monday"]).isoformat(), row)
        cursor += pd.DateOffset(months=1)
        cursor += pd.Timedelta(days=(7 - cursor.weekday()) % 7)
    oos_rows = sorted(assigned.values(), key=lambda row: row["monday"])
    oos_returns = [row["net_return"] for row in oos_rows]
    oos_invested = [row["state"] == "INVESTED_LONG_TOP2" for row in oos_rows]
    oos_metrics = extended_metrics(oos_returns, oos_invested)
    dsr = dsr_z_single_trial(oos_returns)
    pbo = {"status": "UNAVAILABLE", "value": None,
           "reason": "A single pre-registered strategy is not a CSCV strategy family; PBO is not fabricated."}
    brier = {"status": "NOT_APPLICABLE", "value": None,
             "reason": "The strategy emits no probability forecast."}
    return {
        "status": "COMPUTED" if oos_rows else "UNAVAILABLE",
        "method": "Rolling 6-month history / 2-month test / 1-month step; fixed rules, no parameter fitting. Overlapping test windows are deduplicated by first test-fold assignment.",
        "train_months": 6, "test_months": 2, "step_months": 1,
        "fold_count": len(folds),
        "oos_start": str(oos_rows[0]["monday"].date()) if oos_rows else None,
        "oos_end": str(oos_rows[-1]["friday"].date()) if oos_rows else None,
        "oos_week_count": len(oos_rows),
        "oos_metrics": oos_metrics,
        "dsr_z": {"status": "COMPUTED_SINGLE_TRIAL", "value": dsr, "trial_count": 1,
                  "method": "Single-trial Sharpe significance Z; no cross-variant selection/deflation because no variant family was searched."},
        "pbo": pbo, "brier_score": brier, "folds": folds,
    }


def gate_result(wf: dict) -> dict:
    metrics_oos = wf.get("oos_metrics", {})
    dd = metrics_oos.get("max_drawdown")
    pf = metrics_oos.get("profit_factor")
    sharpe = metrics_oos.get("sharpe_ratio")
    win = metrics_oos.get("win_rate")
    dsr = wf.get("dsr_z", {}).get("value")
    pbo = wf.get("pbo", {}).get("value")
    checks = {
        "OOS_WIN_RATE_GT_50_PERCENT": win is not None and win > 0.50,
        "OOS_PROFIT_FACTOR_GT_1_40": pf is not None and pf > 1.40,
        "OOS_SHARPE_GE_1_20": sharpe is not None and sharpe >= 1.20,
        "OOS_MAX_DD_LE_20_PERCENT": dd is not None and dd >= -0.20,
        "PBO_LT_0_40": pbo is not None and pbo < 0.40,
        "DSR_Z_GT_1_00": dsr is not None and dsr > 1.00,
    }
    return {"gate": "CROSS_SECTIONAL_ALPHA_RESEARCH_GATE", "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "failed_checks": [key for key, passed in checks.items() if not passed]}


def main() -> None:
    now = datetime.now(timezone.utc).date()
    last_complete_month_end = date(now.year, now.month, 1) - timedelta(days=1)
    months = month_range(SCAN_START, month_of(last_complete_month_end))
    kline_symbols = [BTC, *ASSETS]
    funding_symbols = list(ASSETS)

    klines, kline_manifest = download_dataset(kline_symbols, "klines", months)
    funding, funding_manifest = download_dataset(funding_symbols, "funding_rate", months)

    cutoff = min(frame["date"].max().date() for frame in klines.values())
    raw_assets = {symbol: frame[frame["date"].dt.date <= cutoff].copy() for symbol, frame in klines.items()}
    frames = {symbol: add_features(raw_assets[symbol]) for symbol in ASSETS}
    btc = add_features(raw_assets[BTC])
    panel = weekly_panel(frames, btc, funding, cutoff)
    result = evaluate(panel)
    wf = walk_forward(result["weekly_results"])
    gate = gate_result(wf)

    funding_coverage = {
        symbol: {
            **funding_manifest["coverage"][symbol],
            "funding_interval_hours_seen": sorted(
                float(x) for x in funding[symbol]["funding_interval_hours"].dropna().unique()
            ),
        }
        for symbol in funding_symbols
    }
    output = {
        "schema_version": "1.0.0",
        "research_status": "EXPLORATORY_NOT_APPROVED_FOR_TRADING",
        "production_status": "NOT_ELIGIBLE",
        "data": {
            "provider": "Binance Vision",
            "market": "USD_M_PERPETUAL",
            "interval": "1d",
            "data_cutoff_utc": str(cutoff),
            "benchmark_only": BTC,
            "fixed_tradable_assets": list(ASSETS),
            "kline_first_archive_month_by_symbol": kline_manifest["first_archive_month_by_symbol"],
            "funding_first_archive_month_by_symbol": funding_manifest["first_archive_month_by_symbol"],
            "kline_coverage": kline_manifest["coverage"],
            "funding_coverage": funding_coverage,
            "archive_integrity": "SHA256_CHECKSUM_VERIFIED_FOR_EVERY_DOWNLOADED_MONTHLY_ARCHIVE",
            "data_limitations": [
                "Single-exchange historical dataset; not a multi-venue execution model.",
                "Fixed current eight-asset universe retains survivorship and selection bias.",
                "Order-book impact, liquidation, basis and exchange outages are not modeled.",
                "Funding is included from verified historical fundingRate archives; weeks with incomplete funding schedule are forced to cash.",
            ],
        },
        "methodology": {
            "regime": "BTC prior-Sunday close > BTC SMA50: bullish; otherwise 100% cash. Missing BTC SMA: cash.",
            "ranking": "0.5 * cross_section_z(Volume_Z20) + 0.5 * cross_section_z(RSI_14)",
            "features": "Volume_Z20 and Wilder RSI14 use daily futures data through prior Sunday only.",
            "cross_section": "Fixed eight tradable assets; minimum four eligible symbols; deterministic score-descending then symbol-ascending tie-break.",
            "execution": "Decision from prior Sunday; enter Monday open; exit Friday close; non-overlapping weekly windows.",
            "portfolio": "Bull regime: 100% long top two, equal 50/50, 1x notional. Bear regime: 100% cash. No shorts.",
            "costs": {
                "fee_per_side": 0.0004, "slippage_per_side": 0.0002,
                "round_trip_trading_cost": ROUND_TRIP_COST,
                "funding": "Sum of actual Binance USD-M funding events while position is open; positive rates are costs to longs, negative rates are credits.",
                "application": "Round-trip fee and slippage charged on invested weeks; funding is added/subtracted per selected asset and averaged across equal-weight positions.",
            },
            "funding_window": "Funding events strictly after Monday 00:00 UTC and through Friday 23:59:59.999 UTC. Adjacent event gaps are checked against funding_interval_hours; incomplete windows are cash.",
            "walk_forward": "6-month rolling history / 2-month test / 1-month step; fixed rules are not fitted. Overlapping OOS weeks are counted once in the combined OOS series.",
            "universe_bias": "The eight assets were fixed from prior research and are not a point-in-time universe. Results remain exploratory.",
        },
        "strategy": {
            "entire_period": {k: v for k, v in result["entire_period"].items() if k != "weekly_results"},
            "year_by_year": result["year_by_year"],
            "walk_forward": wf,
            "acceptance_gate": gate,
        },
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/momentum_cash_futures_results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "research_status": output["research_status"],
        "data_cutoff_utc": output["data"]["data_cutoff_utc"],
        "oos": wf.get("oos_metrics"),
        "gate": gate,
    }, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
