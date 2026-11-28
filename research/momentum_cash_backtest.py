"""Fixed-universe Momentum + Cash weekly backtest.

Research-only SPOT proxy. BTC is a regime benchmark, never tradable.
Decision: prior Sunday close/features; execution: Monday open to Friday close.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile
import json
import math
import time

import numpy as np
import pandas as pd
import requests

BASE = "https://data.binance.vision/data/spot"
# Universe aligned with the V21.1 nine-asset candidate seed; BTC is benchmark-only.
ASSETS = ("ETHUSDT", "NEARUSDT", "XRPUSDT", "SOLUSDT",
          "BNBUSDT", "UNIUSDT", "DOGEUSDT", "ADAUSDT")
BTC = "BTCUSDT"
SCAN_START = "2017-01"
FEE_PER_SIDE = 0.0004
SLIPPAGE_PER_SIDE = 0.0002
COST_PER_SIDE = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
ROUND_TRIP_COST = 2.0 * COST_PER_SIDE
TOP_N = 2
# Inherited from the immediately preceding full-history experiment.
MIN_ELIGIBLE_ASSETS = 4
WARMUP_OBSERVATIONS = 50
WEEKS_PER_YEAR = 52
CSV_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]


def month_range(first: str, last: str) -> list[str]:
    return [str(x) for x in pd.period_range(first, last, freq="M")]


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def monthly_url(symbol: str, month: str) -> str:
    name = f"{symbol}-1d-{month}.zip"
    return f"{BASE}/monthly/klines/{symbol}/1d/{name}"


def daily_url(symbol: str, day: date) -> str:
    name = f"{symbol}-1d-{day.isoformat()}.zip"
    return f"{BASE}/daily/klines/{symbol}/1d/{name}"


def parse_zip(payload: bytes, label: str) -> pd.DataFrame:
    with ZipFile(BytesIO(payload)) as zf:
        csvs = [n for n in zf.namelist() if n.endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"{label}: expected one CSV, got {csvs}")
        with zf.open(csvs[0]) as stream:
            df = pd.read_csv(stream, header=None, names=CSV_COLUMNS)
    if df.empty:
        raise ValueError(f"{label}: empty CSV")
    ts = pd.to_numeric(df["open_time"], errors="coerce")
    valid = ts[np.isfinite(ts)]
    if valid.empty:
        raise ValueError(f"{label}: no timestamps")
    median = float(valid.median())
    unit = "us" if median >= 1e14 else "ms" if median >= 1e11 else "s" if median >= 1e8 else None
    if unit is None:
        raise ValueError(f"{label}: unsupported timestamp magnitude {median}")
    df["date"] = pd.to_datetime(ts, unit=unit, utc=True).dt.floor("D")
    for c in ("open", "high", "low", "close", "volume", "quote_asset_volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[["date", "open", "high", "low", "close", "volume", "quote_asset_volume"]]
    df = df.dropna().drop_duplicates("date").sort_values("date")
    if (df[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{label}: non-positive OHLC")
    if (df[["volume", "quote_asset_volume"]] < 0).any().any():
        raise ValueError(f"{label}: negative volume")
    return df


def get_bytes(session: requests.Session, url: str, attempts: int = 4) -> bytes | None:
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=45)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.content
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def first_archive_months(symbols: list[str], months: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    futures = {}
    with ThreadPoolExecutor(max_workers=24) as pool:
        for symbol in symbols:
            for month in months:
                future = pool.submit(requests.head, monthly_url(symbol, month), timeout=20)
                futures[future] = (symbol, month)
        for future in as_completed(futures):
            symbol, month = futures[future]
            try:
                if future.result().status_code == 200:
                    if symbol not in found or month < found[symbol]:
                        found[symbol] = month
            except requests.RequestException:
                continue
    missing = sorted(set(symbols) - set(found))
    if missing:
        raise RuntimeError("No monthly Binance Vision archive found: " + ",".join(missing))
    return found


def download_symbol(symbol: str, first_month: str, complete_months: list[str],
                    cutoff: date) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Trade-Momentum-Cash-Research/1.0"})
    for month in complete_months:
        if month < first_month:
            continue
        blob = get_bytes(session, monthly_url(symbol, month))
        if blob is None:
            raise RuntimeError(f"D1_DATA_GAP: missing monthly archive {symbol} {month}")
        parts.append(parse_zip(blob, f"{symbol} {month}"))
    if month_of(cutoff) > complete_months[-1]:
        month_start = date(cutoff.year, cutoff.month, 1)
        for day_no in range(1, cutoff.day + 1):
            day = date(month_start.year, month_start.month, day_no)
            blob = get_bytes(session, daily_url(symbol, day), attempts=3)
            if blob is None:
                if day < cutoff - timedelta(days=1):
                    raise RuntimeError(f"D1_DATA_GAP: missing daily archive {symbol} {day}")
                continue
            parts.append(parse_zip(blob, f"{symbol} {day}"))
    if not parts:
        raise RuntimeError(f"No data downloaded for {symbol}")
    out = pd.concat(parts, ignore_index=True).drop_duplicates("date").sort_values("date")
    out = out[out["date"].dt.date <= cutoff].reset_index(drop=True)
    if out.empty:
        raise RuntimeError(f"No observations through cutoff for {symbol}")
    return out


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy().sort_values("date").reset_index(drop=True)
    mean = x["volume"].rolling(20, min_periods=20).mean()
    std = x["volume"].rolling(20, min_periods=20).std(ddof=0)
    x["volume_z20"] = (x["volume"] - mean) / std.replace(0.0, np.nan)
    delta = x["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    x["rsi14"] = 100.0 - 100.0 / (1.0 + rs)
    x.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "rsi14"] = 100.0
    x.loc[(avg_gain == 0.0) & (avg_loss > 0.0), "rsi14"] = 0.0
    x["observations_since_inception"] = np.arange(1, len(x) + 1)
    return x


def zscore(series: pd.Series) -> pd.Series:
    sd = float(series.std(ddof=0))
    if not np.isfinite(sd) or sd <= 1e-12:
        return pd.Series(np.nan, index=series.index)
    return (series - float(series.mean())) / sd


def weekly_panel(frames: dict[str, pd.DataFrame], btc: pd.DataFrame,
                 cutoff: date) -> list[dict]:
    indexed = {symbol: frame.set_index("date") for symbol, frame in frames.items()}
    btc_i = btc.set_index("date").copy()
    btc_i["sma50"] = btc_i["close"].rolling(50, min_periods=50).mean()
    earliest = min(frame["date"].min() for frame in frames.values())
    first_monday = earliest + pd.Timedelta(days=(7 - earliest.weekday()) % 7)
    last = pd.Timestamp(cutoff, tz="UTC")
    mondays = pd.date_range(first_monday, last - pd.Timedelta(days=4),
                            freq="W-MON", tz="UTC")
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
            prior_row = f.loc[prior]
            monday_row = f.loc[monday]
            friday_row = f.loc[friday]
            if isinstance(prior_row, pd.DataFrame):
                prior_row = prior_row.iloc[-1]
            if isinstance(monday_row, pd.DataFrame):
                monday_row = monday_row.iloc[-1]
            if isinstance(friday_row, pd.DataFrame):
                friday_row = friday_row.iloc[-1]
            if int(prior_row["observations_since_inception"]) < WARMUP_OBSERVATIONS:
                continue
            volume_z = float(prior_row["volume_z20"])
            rsi = float(prior_row["rsi14"])
            if not np.isfinite(volume_z) or not np.isfinite(rsi):
                continue
            eligible.append(symbol)
            features[symbol] = (volume_z, rsi)
            returns[symbol] = float(friday_row["close"] / monday_row["open"] - 1.0)

        regime = None
        if prior in btc_i.index:
            b = btc_i.loc[prior]
            if isinstance(b, pd.DataFrame):
                b = b.iloc[-1]
            if pd.notna(b["sma50"]):
                regime = bool(float(b["close"]) > float(b["sma50"]))

        scores: dict[str, float] = {}
        if regime is True and len(eligible) >= MIN_ELIGIBLE_ASSETS:
            volume = pd.Series({s: features[s][0] for s in eligible})
            rsi = pd.Series({s: features[s][1] for s in eligible})
            zv, zr = zscore(volume), zscore(rsi)
            if zv.notna().all() and zr.notna().all():
                composite = 0.5 * zv + 0.5 * zr
                scores = {s: float(composite[s]) for s in eligible}
        ranked = sorted(scores, key=lambda s: (-scores[s], s))
        rows.append({
            "monday": monday,
            "friday": friday,
            "year": int(monday.year),
            "eligible_assets": eligible,
            "scores": scores,
            "top2": ranked[:TOP_N] if len(ranked) >= MIN_ELIGIBLE_ASSETS else [],
            "asset_returns": returns,
            "btc_bull_regime": regime,
        })
    return rows


def metrics(returns: list[float]) -> dict:
    values = np.asarray(returns, dtype=float)
    if len(values) == 0:
        return {"net_return": None, "max_drawdown": None,
                "sharpe_ratio": None, "profit_factor": None, "weeks": 0}
    equity = np.cumprod(1.0 + values)
    peaks = np.maximum.accumulate(np.r_[1.0, equity])
    drawdowns = np.r_[1.0, equity] / peaks - 1.0
    sd = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    sharpe = float(np.mean(values) / sd * math.sqrt(WEEKS_PER_YEAR)) if sd > 1e-15 else None
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    return {
        "net_return": round(float(equity[-1] - 1.0), 10),
        "max_drawdown": round(float(drawdowns.min()), 10),
        "sharpe_ratio": round(sharpe, 8) if sharpe is not None else None,
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else None,
        "weeks": int(len(values)),
    }


def evaluate(panel: list[dict]) -> dict:
    by_year: dict[int, list[float]] = {}
    year_cash: dict[int, int] = {}
    year_invested: dict[int, int] = {}
    all_returns: list[float] = []
    cash_reasons = {"BTC_AT_OR_BELOW_SMA50": 0, "BTC_SMA50_UNAVAILABLE": 0,
                    "INSUFFICIENT_ELIGIBLE_ASSETS": 0, "FEATURE_CROSS_SECTION_INVALID": 0}
    weekly_cash = 0
    weekly_invested = 0
    for row in panel:
        year = row["year"]
        by_year.setdefault(year, [])
        year_cash.setdefault(year, 0)
        year_invested.setdefault(year, 0)
        chosen: list[str] = []
        if row["btc_bull_regime"] is False:
            reason = "BTC_AT_OR_BELOW_SMA50"
        elif row["btc_bull_regime"] is None:
            reason = "BTC_SMA50_UNAVAILABLE"
        elif len(row["eligible_assets"]) < MIN_ELIGIBLE_ASSETS:
            reason = "INSUFFICIENT_ELIGIBLE_ASSETS"
        elif not row["scores"] or not row["top2"]:
            reason = "FEATURE_CROSS_SECTION_INVALID"
        else:
            chosen = row["top2"]
            reason = "BULL_REGIME_LONG_TOP2"
        gross = float(np.mean([row["asset_returns"][s] for s in chosen])) if chosen else 0.0
        # Same conservative linear cost convention as the preceding experiment:
        # two-way fee+slippage charged on fully invested portfolio notional.
        net = gross - ROUND_TRIP_COST if chosen else 0.0
        all_returns.append(net)
        by_year[year].append(net)
        if chosen:
            weekly_invested += 1
            year_invested[year] += 1
        else:
            weekly_cash += 1
            year_cash[year] += 1
            cash_reasons[reason] += 1

    yearly = {}
    for year, values in sorted(by_year.items()):
        total = len(values)
        yearly[str(year)] = {
            "metrics": metrics(values),
            "invested_weeks": year_invested[year],
            "cash_weeks": year_cash[year],
            "cash_pct": round(100.0 * year_cash[year] / total, 6) if total else None,
        }
    total_weeks = len(all_returns)
    return {
        "strategy": "MOMENTUM_CASH_LONG_TOP2",
        "year_by_year": yearly,
        "entire_period": {
            "start_monday": str(panel[0]["monday"].date()) if panel else None,
            "end_friday": str(panel[-1]["friday"].date()) if panel else None,
            "metrics": metrics(all_returns),
            "invested_weeks": weekly_invested,
            "cash_weeks": weekly_cash,
            "cash_pct": round(100.0 * weekly_cash / total_weeks, 6) if total_weeks else None,
            "cash_time_definition": "Share of non-overlapping Monday-open-to-Friday-close weekly decision windows with zero portfolio exposure; includes bear-regime and data/eligibility cash.",
            "cash_reason_counts": cash_reasons,
        },
    }


def main() -> None:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=2)
    current_month = month_of(cutoff)
    prior_month_end = date(cutoff.year, cutoff.month, 1) - timedelta(days=1)
    last_complete_month = month_of(prior_month_end)
    months = month_range(SCAN_START, last_complete_month)
    symbols = [BTC, *ASSETS]
    first_months = first_archive_months(symbols, months)

    raw = {
        symbol: download_symbol(symbol, first_months[symbol], months, cutoff)
        for symbol in symbols
    }
    frames = {symbol: add_features(raw[symbol]) for symbol in ASSETS}
    btc = add_features(raw[BTC])
    panel = weekly_panel(frames, btc, cutoff)
    result = evaluate(panel)

    output = {
        "schema_version": "1.0",
        "research_status": "EXPLORATORY_NOT_APPROVED_FOR_TRADING",
        "data": {
            "provider": "Binance Vision",
            "market": "SPOT",
            "interval": "1d",
            "data_cutoff_utc": str(cutoff),
            "benchmark_only": BTC,
            "fixed_tradable_assets": list(ASSETS),
            "first_available_archive_month_by_symbol": first_months,
            "first_observation_date_by_symbol": {
                symbol: str(raw[symbol]["date"].min().date()) for symbol in symbols
            },
            "last_observation_date_by_symbol": {
                symbol: str(raw[symbol]["date"].max().date()) for symbol in symbols
            },
            "spot_proxy_limitation": "SPOT returns are not perpetual-futures returns; funding, basis, liquidation and contract-specific execution are not modeled.",
        },
        "methodology": {
            "regime": "BTC Close(T-1) > SMA50(T-1): bullish; otherwise 100% cash. Missing BTC SMA: 100% cash.",
            "ranking": "0.5 * cross_section_z(Volume_Z20) + 0.5 * cross_section_z(RSI_14)",
            "volume_z20": "20-observation rolling z-score of base-asset daily volume, using data through prior Sunday only.",
            "rsi14": "Wilder RSI(14), using data through prior Sunday only.",
            "cross_section": "Rank fixed eight-asset universe among symbols with valid prior-Sunday features and Monday Open/Friday Close; inherited minimum eligible cross-section is 4 assets.",
            "execution": "Decision from prior Sunday; enter Monday Open; exit same-week Friday Close; non-overlapping five-session holding window.",
            "portfolio": "Bull regime: 100% long top 2, equal 50/50. Bear regime: 100% cash. No shorts and no mean reversion.",
            "costs": {
                "fee_per_side": FEE_PER_SIDE,
                "slippage_per_side": SLIPPAGE_PER_SIDE,
                "combined_cost_per_side": COST_PER_SIDE,
                "round_trip_cost": ROUND_TRIP_COST,
                "application": "Linear 0.12% deduction from gross portfolio return on invested weeks only, matching the preceding experiment's cost convention."
            },
            "warmup_observations": WARMUP_OBSERVATIONS,
            "universe_bias": "The eight assets are fixed as explicitly requested, but they were selected in prior research using information available at the current cutoff; this historical test therefore retains selection/survivorship bias and is exploratory, not unbiased point-in-time OOS evidence.",
            "cash_time": "Percentage of weekly Monday-open-to-Friday-close decision windows with zero exposure; cash includes bear regime and unavailable/insufficient data weeks. Breakdown is supplied by reason.",
        },
        "strategy": result,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
