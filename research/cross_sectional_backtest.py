"""Full-history, point-in-time, long-only cross-sectional research.

Universe selection is data-driven from Binance Vision SPOT archives.
BTC is a regime benchmark only and is never tradable.
The portfolio is equal-weight long top-2 or bottom-2; otherwise cash.
Execution: Monday open to same-week Friday close (5 sessions, not 7 days).
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
CANDIDATES = (
    "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "UNIUSDT", "FILUSDT", "AAVEUSDT",
)
BENCHMARK = "BTCUSDT"
SCAN_START = "2017-01"
FEE_SIDE = 0.0004
SLIPPAGE_SIDE = 0.0002
COST_SIDE = FEE_SIDE + SLIPPAGE_SIDE
TOP_N = 2
MIN_ELIGIBLE = 4
MIN_DOLLAR_VOLUME_90D = 10_000_000.0
MIN_HISTORY_DAYS = 730
MIN_CORR_OBS = 180
SELECTION_LOOKBACK_DAYS = 365
WARMUP_DAYS = 50
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


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Trade-Full-History-Research/1.0"})
    return s


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
            r = session.get(url, timeout=45)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt + 1 == attempts:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def first_archive_months(symbols: list[str], months: list[str]) -> dict[str, str]:
    """Find first actually present monthly archive; no guessed listing dates."""
    found: dict[str, str] = {}
    tasks = {}
    with ThreadPoolExecutor(max_workers=24) as pool:
        for symbol in symbols:
            for month in months:
                fut = pool.submit(requests.head, monthly_url(symbol, month), timeout=20)
                tasks[fut] = (symbol, month)
        for fut in as_completed(tasks):
            symbol, month = tasks[fut]
            try:
                response = fut.result()
                if response.status_code == 200:
                    if symbol not in found or month < found[symbol]:
                        found[symbol] = month
            except requests.RequestException:
                continue
    missing = sorted(set(symbols) - set(found))
    if missing:
        raise RuntimeError("No monthly Binance Vision archive found for: " + ",".join(missing))
    return found


def download_symbol(symbol: str, first_month: str, complete_months: list[str],
                    cutoff: date) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    session = make_session()
    for month in complete_months:
        if month < first_month:
            continue
        blob = get_bytes(session, monthly_url(symbol, month))
        if blob is None:
            # Missing monthly archive after first listing is not silently forward-filled.
            raise RuntimeError(f"D1_DATA_GAP: missing monthly archive {symbol} {month}")
        parts.append(parse_zip(blob, f"{symbol} {month}"))
    # Current partial month: use daily archives only through the last completed UTC day.
    if month_of(cutoff) > complete_months[-1]:
        start = date(cutoff.year, cutoff.month, 1)
        for day_no in range(1, cutoff.day + 1):
            day = date(start.year, start.month, day_no)
            blob = get_bytes(session, daily_url(symbol, day), attempts=3)
            if blob is None:
                # The last daily archive can lag publication; only trailing missing day is tolerated.
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


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy().sort_values("date").reset_index(drop=True)
    vmean = x["volume"].rolling(20, min_periods=20).mean()
    vstd = x["volume"].rolling(20, min_periods=20).std(ddof=0)
    x["volume_z20"] = (x["volume"] - vmean) / vstd.replace(0.0, np.nan)
    delta = x["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    # Wilder smoothing; min_periods enforces the indicator warm-up.
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    x["rsi14"] = 100.0 - 100.0 / (1.0 + rs)
    x.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "rsi14"] = 100.0
    x.loc[(avg_gain == 0.0) & (avg_loss > 0.0), "rsi14"] = 0.0
    x["obs_from_inception"] = np.arange(1, len(x) + 1)
    return x


def select_universe(frames: dict[str, pd.DataFrame], cutoff: date) -> tuple[list[str], dict]:
    end = pd.Timestamp(cutoff, tz="UTC")
    start90 = end - pd.Timedelta(days=89)
    start365 = end - pd.Timedelta(days=SELECTION_LOOKBACK_DAYS - 1)
    stats: dict[str, dict] = {}
    for symbol, frame in frames.items():
        recent90 = frame.loc[frame["date"] >= start90, "quote_asset_volume"].dropna()
        recent365 = frame.loc[frame["date"] >= start365].copy()
        history_days = int((frame["date"].max() - frame["date"].min()).days + 1)
        coverage = len(frame) / max(history_days, 1)
        med90 = float(recent90.median()) if len(recent90) >= 60 else 0.0
        med365 = float(recent365["quote_asset_volume"].median()) if len(recent365) >= 180 else 0.0
        stats[symbol] = {
            "first_observation": str(frame["date"].min().date()),
            "last_observation": str(frame["date"].max().date()),
            "observations": int(len(frame)),
            "history_calendar_days": history_days,
            "daily_coverage_ratio": round(float(coverage), 6),
            "median_quote_volume_90d_usdt": round(med90, 2),
            "median_quote_volume_365d_usdt": round(med365, 2),
            "eligible": bool(history_days >= MIN_HISTORY_DAYS and med90 >= MIN_DOLLAR_VOLUME_90D and coverage >= 0.995),
        }
    qualified = [s for s in frames if stats[s]["eligible"]]
    if len(qualified) < 8:
        raise RuntimeError(
            "UNIVERSE_GATE_FAIL: fewer than 8 candidates meet history/liquidity/coverage gates; "
            + json.dumps({"qualified": qualified, "candidate_stats": stats})
        )

    # Pairwise correlations use only the common trailing 365-day return window.
    returns = {}
    for symbol in qualified:
        f = frames[symbol].set_index("date")
        r = f["close"].pct_change()
        returns[symbol] = r.loc[r.index >= start365]
    corr = pd.DataFrame(returns).corr(min_periods=MIN_CORR_OBS).abs()
    liquidity_order = sorted(qualified, key=lambda s: stats[s]["median_quote_volume_90d_usdt"], reverse=True)
    selected = [liquidity_order[0]]
    while len(selected) < 8:
        remaining = [s for s in qualified if s not in selected]
        def candidate_score(s: str) -> tuple[float, str]:
            vals = corr.loc[s, selected].dropna()
            mean_corr = float(vals.mean()) if len(vals) else 1.0
            liq_rank = liquidity_order.index(s)
            liq_pct = 1.0 - liq_rank / max(len(liquidity_order) - 1, 1)
            hist_pct = min(stats[s]["history_calendar_days"] / max(
                stats[z]["history_calendar_days"] for z in qualified), 1.0)
            score = 0.45 * (1.0 - mean_corr) + 0.40 * liq_pct + 0.15 * hist_pct
            return score, s
        chosen = max(remaining, key=candidate_score)
        selected.append(chosen)
    corr_out = {}
    for a in selected:
        corr_out[a] = {}
        for b in selected:
            value = corr.loc[a, b]
            corr_out[a][b] = round(float(value), 6) if pd.notna(value) else None
    audit = {
        "selection_method": "greedy_liquidity_history_and_low_abs_correlation",
        "selection_window": {"start": str(start365.date()), "end": str(cutoff)},
        "minimum_median_quote_volume_90d_usdt": MIN_DOLLAR_VOLUME_90D,
        "minimum_history_calendar_days": MIN_HISTORY_DAYS,
        "minimum_daily_coverage_ratio": 0.995,
        "minimum_pairwise_correlation_observations": MIN_CORR_OBS,
        "candidate_stats": stats,
        "selected_pairwise_abs_return_correlations": corr_out,
        "survivorship_warning": "EXPLORATORY_SURVIVORSHIP_BIAS: selected from currently listed candidates using trailing-period liquidity and correlation; not a point-in-time historical constituent universe.",
    }
    return selected, audit


def zscore(s: pd.Series) -> pd.Series:
    sd = float(s.std(ddof=0))
    if not np.isfinite(sd) or sd <= 1e-12:
        return pd.Series(np.nan, index=s.index)
    return (s - float(s.mean())) / sd


def portfolio_metrics(weekly_returns: list[float]) -> dict:
    arr = np.asarray(weekly_returns, dtype=float)
    if len(arr) == 0:
        return {
            "net_return": None, "max_drawdown": None, "sharpe_ratio": None,
            "profit_factor": None, "weeks": 0, "positive_weeks": 0,
            "negative_weeks": 0, "cash_weeks": 0,
        }
    nav = np.cumprod(1.0 + arr)
    peak = np.maximum.accumulate(np.r_[1.0, nav])
    dd = np.r_[1.0, nav] / peak - 1.0
    sd = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = float(np.mean(arr) / sd * math.sqrt(WEEKS_PER_YEAR)) if sd > 1e-15 else None
    gains = float(arr[arr > 0].sum())
    losses = float(-arr[arr < 0].sum())
    return {
        "net_return": round(float(nav[-1] - 1.0), 10),
        "max_drawdown": round(float(dd.min()), 10),
        "sharpe_ratio": round(sharpe, 8) if sharpe is not None else None,
        "profit_factor": round(gains / losses, 8) if losses > 0 else None,
        "weeks": int(len(arr)),
        "positive_weeks": int((arr > 0).sum()),
        "negative_weeks": int((arr < 0).sum()),
        "cash_weeks": int((arr == 0).sum()),
    }


def build_weekly_panel(frames: dict[str, pd.DataFrame], symbols: list[str],
                       btc: pd.DataFrame, cutoff: date) -> list[dict]:
    indexed = {s: frames[s].set_index("date") for s in symbols}
    btc_i = btc.set_index("date").copy()
    btc_i["sma50"] = btc_i["close"].rolling(50, min_periods=50).mean()
    first = min(frames[s]["date"].min() for s in symbols)
    first_monday = first + pd.Timedelta(days=(7 - first.weekday()) % 7)
    last = pd.Timestamp(cutoff, tz="UTC")
    mondays = pd.date_range(first_monday, last - pd.Timedelta(days=4), freq="W-MON", tz="UTC")
    panel = []
    for monday in mondays:
        prior = monday - pd.Timedelta(days=1)
        friday = monday + pd.Timedelta(days=4)
        available = []
        feature_values = {}
        prices = {}
        for s in symbols:
            f = indexed[s]
            if prior not in f.index or monday not in f.index or friday not in f.index:
                continue
            row = f.loc[prior]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            monday_row = f.loc[monday]
            friday_row = f.loc[friday]
            if isinstance(monday_row, pd.DataFrame):
                monday_row = monday_row.iloc[-1]
            if isinstance(friday_row, pd.DataFrame):
                friday_row = friday_row.iloc[-1]
            if int(row["obs_from_inception"]) < WARMUP_DAYS:
                continue
            if not np.isfinite(row["volume_z20"]) or not np.isfinite(row["rsi14"]):
                continue
            if not np.isfinite(monday_row["open"]) or not np.isfinite(friday_row["close"]):
                continue
            available.append(s)
            feature_values[s] = (float(row["volume_z20"]), float(row["rsi14"]))
            prices[s] = float(friday_row["close"] / monday_row["open"] - 1.0)
        btc_regime = None
        if prior in btc_i.index:
            b = btc_i.loc[prior]
            if isinstance(b, pd.DataFrame):
                b = b.iloc[-1]
            if pd.notna(b["sma50"]) and float(b["close"]) > 0:
                btc_regime = bool(float(b["close"]) > float(b["sma50"]))
        scores = {}
        if len(available) >= MIN_ELIGIBLE:
            vol = pd.Series({s: feature_values[s][0] for s in available})
            rsi = pd.Series({s: feature_values[s][1] for s in available})
            zv, zr = zscore(vol), zscore(rsi)
            if zv.notna().all() and zr.notna().all():
                composite = 0.5 * zv + 0.5 * zr
                scores = {s: float(composite[s]) for s in available}
        ranked = sorted(scores, key=lambda s: (-scores[s], s))
        top = ranked[:TOP_N] if len(ranked) >= MIN_ELIGIBLE else []
        bottom = ranked[-TOP_N:] if len(ranked) >= MIN_ELIGIBLE else []
        panel.append({
            "monday": monday, "friday": friday, "year": int(monday.year),
            "available_symbols": available, "scores": scores,
            "top2": top, "bottom2": bottom, "asset_returns": prices,
            "btc_bull_regime": btc_regime,
        })
    return panel


def run_strategy(panel: list[dict], strategy: str) -> tuple[dict, dict]:
    all_returns: list[float] = []
    by_year: dict[int, list[float]] = {}
    year_trade_counts: dict[int, int] = {}
    year_selected: dict[int, dict[str, int]] = {}
    weekly_log = []
    for row in panel:
        year = row["year"]
        by_year.setdefault(year, [])
        year_trade_counts.setdefault(year, 0)
        year_selected.setdefault(year, {})
        chosen: list[str] = []
        reason = "CASH_INSUFFICIENT_ELIGIBLE_ASSETS"
        if len(row["available_symbols"]) >= MIN_ELIGIBLE and row["top2"]:
            if strategy == "PURE_MOMENTUM_LONG_TOP2":
                chosen, reason = row["top2"], "LONG_TOP2"
            elif strategy == "PURE_MEAN_REVERSION_LONG_BOTTOM2":
                chosen, reason = row["bottom2"], "LONG_BOTTOM2"
            elif strategy == "HYBRID_BTC_MA50_SWITCH":
                if row["btc_bull_regime"] is True:
                    chosen, reason = row["top2"], "BTC_ABOVE_MA50_LONG_TOP2"
                elif row["btc_bull_regime"] is False:
                    chosen, reason = row["bottom2"], "BTC_AT_OR_BELOW_MA50_LONG_BOTTOM2"
                else:
                    reason = "CASH_BTC_MA50_UNAVAILABLE"
        gross = float(np.mean([row["asset_returns"][s] for s in chosen])) if chosen else 0.0
        # 100% long exposure: entry and exit costs on total portfolio notional.
        cost = 2.0 * COST_SIDE if chosen else 0.0
        net = gross - cost
        all_returns.append(net)
        by_year[year].append(net)
        if chosen:
            year_trade_counts[year] += 1
            for s in chosen:
                year_selected[year][s] = year_selected[year].get(s, 0) + 1
        weekly_log.append({
            "monday": str(row["monday"].date()),
            "friday": str(row["friday"].date()),
            "strategy_state": reason,
            "eligible_assets": row["available_symbols"],
            "selected_longs": chosen,
            "btc_bull_regime": row["btc_bull_regime"],
            "gross_return": round(gross, 10),
            "round_trip_cost": round(cost, 10),
            "net_return": round(net, 10),
        })
    years = {}
    for year, returns in sorted(by_year.items()):
        years[str(year)] = {
            "status": "COMPLETED" if returns else "NO_WEEKS",
            "metrics": portfolio_metrics(returns),
            "invested_weeks": year_trade_counts[year],
            "selection_counts": year_selected[year],
        }
    result = {
        "strategy": strategy,
        "year_by_year": years,
        "entire_period": {
            "start_monday": weekly_log[0]["monday"] if weekly_log else None,
            "end_friday": weekly_log[-1]["friday"] if weekly_log else None,
            "metrics": portfolio_metrics(all_returns),
        },
    }
    return result, {"weekly_log": weekly_log}


def main() -> None:
    now_utc = datetime.now(timezone.utc).date()
    cutoff = now_utc - timedelta(days=2)  # completed daily bars only
    current_month = month_of(cutoff)
    previous_month_end = date(cutoff.year, cutoff.month, 1) - timedelta(days=1)
    last_complete_month = month_of(previous_month_end)
    scan_months = month_range(SCAN_START, last_complete_month)
    symbols_to_fetch = [BENCHMARK, *CANDIDATES]
    first_months = first_archive_months(symbols_to_fetch, scan_months)

    frames_raw = {}
    for symbol in symbols_to_fetch:
        frames_raw[symbol] = download_symbol(
            symbol, first_months[symbol], scan_months, cutoff
        )
    frames = {s: add_features(frames_raw[s]) for s in CANDIDATES}
    selected, selection_audit = select_universe(frames, cutoff)
    btc = add_features(frames_raw[BENCHMARK])
    panel = build_weekly_panel(frames, selected, btc, cutoff)

    strategy_names = (
        "PURE_MOMENTUM_LONG_TOP2",
        "PURE_MEAN_REVERSION_LONG_BOTTOM2",
        "HYBRID_BTC_MA50_SWITCH",
    )
    results = {}
    for name in strategy_names:
        results[name], _ = run_strategy(panel, name)

    output = {
        "schema_version": "3.0",
        "research_status": "EXPLORATORY_NOT_APPROVED_FOR_TRADING",
        "data": {
            "provider": "Binance Vision",
            "market": "SPOT",
            "interval": "1d",
            "data_cutoff_utc": str(cutoff),
            "latest_complete_month": last_complete_month,
            "current_partial_month_daily_archives_included": current_month if current_month > last_complete_month else None,
            "benchmark_only": BENCHMARK,
            "candidate_universe": list(CANDIDATES),
            "selected_tradable_assets": selected,
            "first_available_archive_month_by_symbol": first_months,
            "asset_first_observation_dates": {
                s: str(frames_raw[s]["date"].min().date()) for s in symbols_to_fetch
            },
            "funding": "NOT_APPLICABLE_TO_SPOT_PROXY; NO PERPETUAL FUNDING DATA USED",
            "data_integrity": "No forward-fill; missing monthly archive or material historical gaps fail the run.",
        },
        "universe_selection": selection_audit,
        "methodology": {
            "ranking": "0.5 * cross_section_z(Volume_Z20) + 0.5 * cross_section_z(RSI_14)",
            "volume_z20": "20-day rolling z-score of base-asset volume",
            "rsi14": "Wilder RSI(14)",
            "cross_section": "At each Monday, rank only assets already listed and with valid prior-Sunday features plus Monday Open and Friday Close; require at least 4 eligible assets.",
            "warmup": "At least 50 observations since first available daily archive for each tradable asset; BTC SMA50 uses prior close only.",
            "execution": "Monday Open to same-week Friday Close; 5 weekday sessions, non-overlapping; not 7 calendar days.",
            "portfolio": "Long-only, equal-weight top 2 or bottom 2; 100% cash when fewer than 4 assets or required benchmark data is unavailable.",
            "costs": {
                "fee_per_side": FEE_SIDE,
                "slippage_per_side": SLIPPAGE_SIDE,
                "combined_cost_per_side": COST_SIDE,
                "round_trip_cost_on_fully_invested_portfolio": 2 * COST_SIDE,
            },
            "btc_regime": "BTC Close(T-1) > SMA50(T-1) => bullish; <= => bearish; missing SMA => cash for Hybrid only.",
            "selection_bias": "The eight assets are selected using trailing-period liquidity and correlation as of the run cutoff. Historical results are exploratory and contain universe-selection/survivorship bias; they are not unbiased OOS evidence.",
            "spot_proxy_limitation": "Spot returns are not perpetual-futures returns; funding, basis, liquidation, and contract-specific microstructure are not modeled.",
        },
        "strategies": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
