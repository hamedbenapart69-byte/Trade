"""Institutional-style cross-sectional long/short research backtest.

Research-only. Public Binance Vision SPOT daily klines are used as price/volume
proxies; this is not executable perpetual-futures performance.

Timing convention (UTC daily bars):
- Signal date T uses features calculated through close of T-1.
- Entry is Open(T+1); exit is Open(T+4), exactly three open-to-open intervals.
- One new 1/3-capital tranche is opened each signal day; three tranches overlap.
- Long and short gross notionals are each 50% of each tranche's capital.

Experiment C ranks on Volume_Z20 exactly like A and evaluates each asset's
realized return after subtracting the equal-weight market return. Because the
portfolio is dollar-neutral (equal long and short notionals), that common
market subtraction cancels from the combined portfolio return by construction.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
import json
from pathlib import PurePosixPath
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
)
TEST_YEARS = (2023, 2024)
FIRST_MONTH = "2022-10"
LAST_MONTH = "2025-01"
FEE_PER_SIDE = 0.0004
SLIPPAGE_PER_SIDE = 0.0002
COST_PER_SIDE = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
SHORT_FUNDING_PER_DAY = 0.0001
TRANCHE_WEIGHT = 1.0 / 3.0
LONG_GROSS_WEIGHT = 0.5
SHORT_GROSS_WEIGHT = 0.5
TOP_N = 2
ANNUALIZATION_DAYS = 365
COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]


def month_range(first: str, last: str) -> list[str]:
    start = pd.Period(first, freq="M")
    end = pd.Period(last, freq="M")
    return [str(p) for p in pd.period_range(start, end, freq="M")]


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5, connect=5, read=5, backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "Trade-CrossSectional-Research/1.0"})
    return session


def download_month(
    session: requests.Session, symbol: str, month: str
) -> pd.DataFrame:
    filename = f"{symbol}-1d-{month}.zip"
    url = f"{BASE_URL}/{symbol}/1d/{filename}"
    response = session.get(url, timeout=60)
    response.raise_for_status()
    with ZipFile(BytesIO(response.content)) as archive:
        csv_files = [n for n in archive.namelist() if n.endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"{filename}: expected one CSV, got {csv_files}")
        with archive.open(csv_files[0]) as stream:
            frame = pd.read_csv(stream, header=None, names=COLUMNS)
    timestamp_values = pd.to_numeric(frame["open_time"], errors="coerce")
    finite_timestamps = timestamp_values[np.isfinite(timestamp_values)]
    if finite_timestamps.empty:
        raise ValueError(f"{filename}: no numeric open_time values")
    # Binance Vision timestamp precision has varied by archive vintage:
    # detect seconds, milliseconds, or microseconds from the numeric magnitude.
    median_timestamp = float(finite_timestamps.median())
    if median_timestamp >= 1e14:
        timestamp_unit = "us"
    elif median_timestamp >= 1e11:
        timestamp_unit = "ms"
    elif median_timestamp >= 1e8:
        timestamp_unit = "s"
    else:
        raise ValueError(
            f"{filename}: unrecognized open_time magnitude {median_timestamp}"
        )
    frame["open_time"] = timestamp_values
    frame = frame.loc[np.isfinite(frame["open_time"])].copy()
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = pd.to_datetime(
        frame["open_time"], unit=timestamp_unit, utc=True
    ).dt.floor("D")
    frame = frame[["date", "open", "high", "low", "close", "volume"]]
    if frame.empty or frame[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError(f"{filename}: empty or invalid OHLCV data")
    return frame


def wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Features on row d use OHLCV through close of d; caller lags by one row."""
    out = frame.sort_values("date").copy()
    vol_mean = out["volume"].rolling(20, min_periods=20).mean()
    vol_std = out["volume"].rolling(20, min_periods=20).std(ddof=0)
    out["Volume_Z20"] = (out["volume"] - vol_mean) / vol_std.replace(0.0, np.nan)

    delta = out["close"].diff()
    avg_gain = wilder(delta.clip(lower=0.0), 14)
    avg_loss = wilder(-delta.clip(upper=0.0), 14)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out["RSI_14"] = 100.0 - 100.0 / (1.0 + rs)
    out.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "RSI_14"] = 100.0
    out.loc[(avg_gain == 0.0) & (avg_loss > 0.0), "RSI_14"] = 0.0
    return out


def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    months = month_range(FIRST_MONTH, LAST_MONTH)
    per_symbol: dict[str, pd.DataFrame] = {}
    with make_session() as session:
        for symbol in SYMBOLS:
            chunks = [download_month(session, symbol, m) for m in months]
            raw = (
                pd.concat(chunks, ignore_index=True)
                .drop_duplicates("date")
                .sort_values("date")
                .reset_index(drop=True)
            )
            per_symbol[symbol] = add_features(raw)

    # Require a complete common daily calendar and complete cross-section.
    common_dates = set(per_symbol[SYMBOLS[0]]["date"])
    for symbol in SYMBOLS[1:]:
        common_dates &= set(per_symbol[symbol]["date"])
    dates = pd.DatetimeIndex(sorted(common_dates), name="date")
    if len(dates) < 800:
        raise ValueError(f"Insufficient common daily history: {len(dates)} dates")
    expected = pd.date_range(dates.min(), dates.max(), freq="D", tz="UTC")
    if not dates.equals(expected):
        missing_common = expected.difference(dates)
        per_symbol_gaps = {}
        for symbol, frame in per_symbol.items():
            symbol_dates = pd.DatetimeIndex(frame["date"])
            gaps = expected.difference(symbol_dates)
            if len(gaps):
                per_symbol_gaps[symbol] = [str(x.date()) for x in gaps[:20]]
        raise ValueError(
            "D1_DATA_GAP: common_calendar_missing="
            + json.dumps([str(x.date()) for x in missing_common[:30]])
            + "; per_symbol_missing_dates="
            + json.dumps(per_symbol_gaps, ensure_ascii=False)
        )

    opens = pd.DataFrame(index=dates)
    features = pd.DataFrame(index=dates)
    for symbol, frame in per_symbol.items():
        indexed = frame.set_index("date").reindex(dates)
        opens[symbol] = indexed["open"].astype(float)
        # Strict point-in-time lag: row T receives the feature known at close T-1.
        features[f"{symbol}:Volume_Z20"] = indexed["Volume_Z20"].shift(1)
        features[f"{symbol}:RSI_14"] = indexed["RSI_14"].shift(1)

    if opens.isna().any().any() or (opens <= 0.0).any().any():
        raise ValueError("Missing/non-positive open prices in common universe")
    return opens, features


def cross_section_z(values: pd.Series) -> pd.Series:
    sd = float(values.std(ddof=0))
    if not np.isfinite(sd) or sd <= 0.0:
        return pd.Series(np.nan, index=values.index)
    return (values - float(values.mean())) / sd


def choose_sides(
    signal_row: pd.Series, experiment: str
) -> tuple[list[str], list[str]] | None:
    vol = pd.Series(
        {s: signal_row[f"{s}:Volume_Z20"] for s in SYMBOLS}, dtype=float
    )
    rsi = pd.Series(
        {s: signal_row[f"{s}:RSI_14"] for s in SYMBOLS}, dtype=float
    )
    if vol.isna().any() or not np.isfinite(vol.to_numpy()).all():
        return None
    if experiment == "B_VOLUME_RSI_50_50_CS_ZSCORE":
        if rsi.isna().any() or not np.isfinite(rsi.to_numpy()).all():
            return None
        score = 0.5 * cross_section_z(vol) + 0.5 * cross_section_z(rsi)
    else:
        score = vol
    if score.isna().any() or not np.isfinite(score.to_numpy()).all():
        return None
    # Stable tie-break: symbol ascending.
    ranked = sorted(SYMBOLS, key=lambda s: (-float(score[s]), s))
    return ranked[:TOP_N], ranked[-TOP_N:]


def validate_ranking_logic() -> None:
    """Deterministic test: the 50/50 composite must actually use RSI."""
    synthetic: dict[str, float] = {}
    for i, symbol in enumerate(SYMBOLS):
        synthetic[f"{symbol}:Volume_Z20"] = float(len(SYMBOLS) - i)
        synthetic[f"{symbol}:RSI_14"] = float(i)
    volume_sides = choose_sides(synthetic, "A_VOLUME_ONLY")
    composite_sides = choose_sides(
        synthetic, "B_VOLUME_RSI_50_50_CS_ZSCORE"
    )
    if volume_sides is None or composite_sides is None:
        raise AssertionError("Ranking self-test unexpectedly returned no basket")
    if volume_sides == composite_sides:
        raise AssertionError("B ranking ignored RSI; composite equals Volume-only")


def metric_pack(
    daily_pnl: np.ndarray,
    daily_returns: np.ndarray,
    nav: np.ndarray,
    cohort_returns: list[float],
) -> dict[str, float | int | None]:
    positive = float(daily_pnl[daily_pnl > 0].sum())
    negative = float(-daily_pnl[daily_pnl < 0].sum())
    cohort_arr = np.asarray(cohort_returns, dtype=float)
    cohort_pos = float(cohort_arr[cohort_arr > 0].sum()) if len(cohort_arr) else 0.0
    cohort_neg = float(-cohort_arr[cohort_arr < 0].sum()) if len(cohort_arr) else 0.0
    peaks = np.maximum.accumulate(nav)
    drawdowns = nav / peaks - 1.0
    std = float(np.std(daily_returns, ddof=1)) if len(daily_returns) > 1 else 0.0
    sharpe = (
        float(np.mean(daily_returns) / std * np.sqrt(ANNUALIZATION_DAYS))
        if std > 0.0 else None
    )
    return {
        "net_return": round(float(nav[-1] - 1.0), 10),
        "max_drawdown": round(float(np.min(drawdowns)), 10),
        "sharpe_ratio": round(sharpe, 8) if sharpe is not None else None,
        "profit_factor_daily_net_pnl": (
            round(positive / negative, 8) if negative > 0.0 else None
        ),
        "win_rate_daily": round(float(np.mean(daily_returns > 0.0)), 8),
        "win_rate_cohort_net": (
            round(float(np.mean(cohort_arr > 0.0)), 8) if len(cohort_arr) else None
        ),
        "profit_factor_cohort_net": (
            round(cohort_pos / cohort_neg, 8) if cohort_neg > 0.0 else None
        ),
        "cohort_count": int(len(cohort_arr)),
    }


def run_experiment(
    year: int,
    experiment: str,
    opens: pd.DataFrame,
    features: pd.DataFrame,
) -> dict[str, object]:
    year_dates = [
        d for d in opens.index
        if d.year == year and d in features.index
    ]
    cohorts: list[dict[str, object]] = []
    skipped = 0
    for signal_date in year_dates:
        signal_idx = opens.index.get_loc(signal_date)
        # Entry Open(T+1), exit Open(T+4): exactly 3 open-to-open days.
        if signal_idx + 4 >= len(opens.index):
            skipped += 1
            continue
        sides = choose_sides(features.loc[signal_date], experiment)
        if sides is None:
            skipped += 1
            continue
        longs, shorts = sides
        entry_idx, exit_idx = signal_idx + 1, signal_idx + 4
        entry_date, exit_date = opens.index[entry_idx], opens.index[exit_idx]
        cohort_gross = 0.0
        for interval_idx in range(entry_idx, exit_idx):
            d0, d1 = opens.index[interval_idx], opens.index[interval_idx + 1]
            all_returns = (
                opens.loc[d1, list(SYMBOLS)].to_numpy(dtype=float)
                / opens.loc[d0, list(SYMBOLS)].to_numpy(dtype=float) - 1.0
            )
            by_symbol = dict(zip(SYMBOLS, all_returns))
            if experiment == "C_MARKET_RESIDUAL":
                market_return = float(np.mean(all_returns))
                long_returns = [by_symbol[s] - market_return for s in longs]
                short_returns = [by_symbol[s] - market_return for s in shorts]
            else:
                long_returns = [by_symbol[s] for s in longs]
                short_returns = [by_symbol[s] for s in shorts]
            cohort_gross += (
                LONG_GROSS_WEIGHT * float(np.mean(long_returns))
                - SHORT_GROSS_WEIGHT * float(np.mean(short_returns))
            )
        cohort_cost = 2.0 * COST_PER_SIDE
        cohort_funding = SHORT_GROSS_WEIGHT * SHORT_FUNDING_PER_DAY * 3.0
        cohorts.append({
            "signal_date": signal_date,
            "feature_asof_date": signal_date - pd.Timedelta(days=1),
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "longs": longs,
            "shorts": shorts,
            "gross_return": cohort_gross,
            "net_return": cohort_gross - cohort_cost - cohort_funding,
        })

    if len(cohorts) != len(year_dates) - skipped or not cohorts:
        raise ValueError(f"{year}/{experiment}: no complete cohorts or inconsistent counts")

    first_idx = min(int(c["entry_idx"]) for c in cohorts)
    last_idx = max(int(c["exit_idx"]) for c in cohorts)
    sim_dates = opens.index[first_idx:last_idx + 1]
    n_days = len(sim_dates)
    gross_pnl = np.zeros(n_days, dtype=float)
    net_pnl = np.zeros(n_days, dtype=float)
    long_gross_pnl = np.zeros(n_days, dtype=float)
    short_gross_pnl = np.zeros(n_days, dtype=float)
    long_cost = np.zeros(n_days, dtype=float)
    short_cost = np.zeros(n_days, dtype=float)
    funding_cost = np.zeros(n_days, dtype=float)
    turnover = np.zeros(n_days, dtype=float)

    for cohort in cohorts:
        entry_idx = int(cohort["entry_idx"])
        exit_idx = int(cohort["exit_idx"])
        longs = list(cohort["longs"])
        shorts = list(cohort["shorts"])
        entry_pos, exit_pos = entry_idx - first_idx, exit_idx - first_idx

        # One-way entry and exit turnover; 1/3 tranche, 100% gross notional.
        turnover[entry_pos] += TRANCHE_WEIGHT
        turnover[exit_pos] += TRANCHE_WEIGHT
        long_cost[entry_pos] += TRANCHE_WEIGHT * LONG_GROSS_WEIGHT * COST_PER_SIDE
        short_cost[entry_pos] += TRANCHE_WEIGHT * SHORT_GROSS_WEIGHT * COST_PER_SIDE
        long_cost[exit_pos] += TRANCHE_WEIGHT * LONG_GROSS_WEIGHT * COST_PER_SIDE
        short_cost[exit_pos] += TRANCHE_WEIGHT * SHORT_GROSS_WEIGHT * COST_PER_SIDE

        for global_idx in range(entry_idx, exit_idx):
            local_idx = global_idx - first_idx
            d0, d1 = opens.index[global_idx], opens.index[global_idx + 1]
            asset_returns = (
                opens.loc[d1, list(SYMBOLS)].to_numpy(dtype=float)
                / opens.loc[d0, list(SYMBOLS)].to_numpy(dtype=float) - 1.0
            )
            ret_by_symbol = dict(zip(SYMBOLS, asset_returns))
            if experiment == "C_MARKET_RESIDUAL":
                market_return = float(np.mean(asset_returns))
                long_returns = np.array([ret_by_symbol[s] - market_return for s in longs])
                short_returns = np.array([ret_by_symbol[s] - market_return for s in shorts])
            else:
                long_returns = np.array([ret_by_symbol[s] for s in longs])
                short_returns = np.array([ret_by_symbol[s] for s in shorts])

            lp = TRANCHE_WEIGHT * LONG_GROSS_WEIGHT * float(np.mean(long_returns))
            sp = -TRANCHE_WEIGHT * SHORT_GROSS_WEIGHT * float(np.mean(short_returns))
            long_gross_pnl[local_idx] += lp
            short_gross_pnl[local_idx] += sp
            gross_pnl[local_idx] += lp + sp
            funding_cost[local_idx] += (
                TRANCHE_WEIGHT * SHORT_GROSS_WEIGHT * SHORT_FUNDING_PER_DAY
            )

    net_pnl[:] = gross_pnl - long_cost - short_cost - funding_cost
    gross_nav = np.cumprod(1.0 + gross_pnl)
    net_nav = np.cumprod(1.0 + net_pnl)
    gross_daily_returns = np.diff(np.r_[1.0, gross_nav]) / np.r_[1.0, gross_nav[:-1]]
    net_daily_returns = np.diff(np.r_[1.0, net_nav]) / np.r_[1.0, net_nav[:-1]]

    gross_metrics = metric_pack(gross_pnl, gross_daily_returns, gross_nav,
                                [float(c["gross_return"]) for c in cohorts])
    net_metrics = metric_pack(net_pnl, net_daily_returns, net_nav,
                              [float(c["net_return"]) for c in cohorts])

    long_net_pnl = long_gross_pnl - long_cost
    short_net_pnl = short_gross_pnl - short_cost - funding_cost
    long_gross_total = float(np.sum(long_gross_pnl))
    short_gross_total = float(np.sum(short_gross_pnl))
    long_net_total = float(np.sum(long_net_pnl))
    short_net_total = float(np.sum(short_net_pnl))

    # C must equal A in combined dollar-neutral PnL because the same market
    # return is subtracted from both 50% legs; this is an algebraic identity.
    total_costs = float(np.sum(long_cost + short_cost))
    total_funding = float(np.sum(funding_cost))
    total_turnover = float(np.sum(turnover))

    return {
        "experiment": experiment,
        "year": year,
        "status": "COMPLETED",
        "signal_count": len(year_dates),
        "cohorts_completed": len(cohorts),
        "signals_skipped": skipped,
        "timing": {
            "feature_asof": "close(T-1)",
            "signal_date": "T",
            "entry": "Open(T+1)",
            "exit": "Open(T+4)",
            "holding_open_to_open_intervals": 3,
            "overlapping_tranches": 3,
            "capital_per_new_tranche": TRANCHE_WEIGHT,
        },
        "portfolio_weights": {
            "long_gross_notional_per_tranche": LONG_GROSS_WEIGHT,
            "short_gross_notional_per_tranche": SHORT_GROSS_WEIGHT,
            "long_symbols": TOP_N,
            "short_symbols": TOP_N,
        },
        "cost_model": {
            "fee_per_side": FEE_PER_SIDE,
            "slippage_per_side": SLIPPAGE_PER_SIDE,
            "total_execution_cost_per_side": COST_PER_SIDE,
            "short_funding_per_day": SHORT_FUNDING_PER_DAY,
            "short_funding_label": "PROXY",
            "short_borrow_and_margin_model": "UNAVAILABLE",
        },
        "metrics": {
            "gross": gross_metrics,
            "net": net_metrics,
            "gross_return": gross_metrics["net_return"],
            "net_return": net_metrics["net_return"],
            "max_drawdown": net_metrics["max_drawdown"],
            "sharpe_ratio": net_metrics["sharpe_ratio"],
            "profit_factor": net_metrics["profit_factor_daily_net_pnl"],
            "win_rate": net_metrics["win_rate_cohort_net"],
        },
        "long_leg": {
            "gross_pnl_on_initial_capital": round(long_gross_total, 10),
            "net_pnl_on_initial_capital": round(long_net_total, 10),
        },
        "short_leg": {
            "gross_pnl_on_initial_capital": round(short_gross_total, 10),
            "net_pnl_on_initial_capital": round(short_net_total, 10),
            "funding_cost_on_initial_capital": round(total_funding, 10),
            "funding_label": "PROXY",
        },
        "costs": {
            "execution_cost_on_initial_capital": round(total_costs, 10),
            "funding_cost_on_initial_capital": round(total_funding, 10),
        },
        "turnover": {
            "total_gross_traded_notional_multiple": round(total_turnover, 8),
            "one_way_traded_notional_multiple": round(total_turnover / 2.0, 8),
            "average_daily_gross_turnover_pct_initial_capital": round(
                float(np.mean(turnover)) * 100.0, 8
            ),
        },
        "sample_window": {
            "first_signal_date": str(cohorts[0]["signal_date"].date()),
            "last_signal_date": str(cohorts[-1]["signal_date"].date()),
            "first_entry_date": str(sim_dates[0].date()),
            "last_exit_date": str(sim_dates[-1].date()),
            "calendar_days_in_portfolio_series": n_days,
        },
        "baseline_equal_weight_buy_and_hold": equal_weight_buy_hold(
            opens, first_idx, last_idx
        ),
        "experiment_c_market_residual_note": (
            "For C, equal-weight market return is subtracted from each selected "
            "asset's realized daily return before leg aggregation. With equal "
            "50% long and 50% short gross notionals, the common market term "
            "cancels exactly in combined portfolio PnL; C is not an independent "
            "alpha test versus A."
            if experiment == "C_MARKET_RESIDUAL" else None
        ),
    }


def equal_weight_buy_hold(
    opens: pd.DataFrame, first_idx: int, last_idx: int
) -> dict[str, object]:
    prices = opens.iloc[first_idx:last_idx + 1][list(SYMBOLS)]
    initial = prices.iloc[0]
    gross_nav = (prices / initial).mean(axis=1).to_numpy(dtype=float)
    net_nav = gross_nav * (1.0 - COST_PER_SIDE)
    net_nav[-1] *= (1.0 - COST_PER_SIDE)
    daily_returns = np.diff(np.r_[1.0, net_nav]) / np.r_[1.0, net_nav[:-1]]
    gross_returns = np.diff(np.r_[1.0, gross_nav]) / np.r_[1.0, gross_nav[:-1]]
    net_pnl = np.diff(np.r_[1.0, net_nav])
    metrics = metric_pack(net_pnl, daily_returns, net_nav, [])
    gross_metrics = metric_pack(
        np.diff(np.r_[1.0, gross_nav]), gross_returns, gross_nav, []
    )
    return {
        "method": "10-symbol equal initial weights; buy at first Open; hold to final Open",
        "gross_return": round(float(gross_nav[-1] - 1.0), 10),
        "net_return": round(float(net_nav[-1] - 1.0), 10),
        "max_drawdown_net": metrics["max_drawdown"],
        "sharpe_ratio_net": metrics["sharpe_ratio"],
        "profit_factor_daily_net_pnl": metrics["profit_factor_daily_net_pnl"],
        "win_rate_daily_net": metrics["win_rate_daily"],
        "entry_exit_cost_each_side": COST_PER_SIDE,
        "gross_metrics": gross_metrics,
    }


def main() -> None:
    validate_ranking_logic()
    opens, features = load_panel()
    results: list[dict[str, object]] = []
    for year in TEST_YEARS:
        for experiment in (
            "A_VOLUME_ONLY",
            "B_VOLUME_RSI_50_50_CS_ZSCORE",
            "C_MARKET_RESIDUAL",
        ):
            results.append(run_experiment(year, experiment, opens, features))

    # Data and methodology invariants.
    by_key = {(int(r["year"]), str(r["experiment"])): r for r in results}
    for year in TEST_YEARS:
        changed = 0
        compared = 0
        for signal_date in [d for d in opens.index if d.year == year]:
            a_sides = choose_sides(features.loc[signal_date], "A_VOLUME_ONLY")
            b_sides = choose_sides(
                features.loc[signal_date], "B_VOLUME_RSI_50_50_CS_ZSCORE"
            )
            if a_sides is not None and b_sides is not None:
                compared += 1
                changed += int(a_sides != b_sides)
        by_key[(year, "B_VOLUME_RSI_50_50_CS_ZSCORE")][
            "selection_diagnostics"
        ] = {
            "dates_compared": compared,
            "dates_with_different_baskets_vs_A": changed,
            "ranking_self_test": "PASS",
        }
    for year in TEST_YEARS:
        a = by_key[(year, "A_VOLUME_ONLY")]["metrics"]["net_return"]
        c = by_key[(year, "C_MARKET_RESIDUAL")]["metrics"]["net_return"]
        if not np.isclose(float(a), float(c), atol=1e-10, rtol=0.0):
            raise AssertionError(f"Experiment C should algebraically match A: {year}")

    output = {
        "schema_version": "1.0",
        "research_status": "EXPLORATORY_NOT_APPROVED_FOR_TRADING",
        "data": {
            "provider": "Binance Vision",
            "market": "SPOT",
            "interval": "1d",
            "universe": list(SYMBOLS),
            "test_years": list(TEST_YEARS),
            "warmup_start_month": FIRST_MONTH,
            "download_end_month": LAST_MONTH,
            "short_futures_data": "UNAVAILABLE",
        },
        "methodology": {
            "feature_timing": "Features on signal date T are shifted from values calculated through close(T-1).",
            "execution_timing": "Entry at Open(T+1); exit at Open(T+4).",
            "holding_period": "3 open-to-open daily intervals",
            "tranching": "One new 1/3 initial-capital tranche per signal day; 3 overlapping cohorts.",
            "ranking": {
                "A": "Raw per-symbol Volume_Z20; cross-sectional rank each signal day.",
                "B": "50% cross-sectional z-score(Volume_Z20) + 50% cross-sectional z-score(RSI_14).",
                "C": "Same Volume_Z20 ranking as A; realized daily asset returns adjusted by equal-weight market return.",
            },
            "missing_cross_section": "Skip the entire signal date unless all 10 symbols have finite required features.",
            "ties": "Deterministic symbol-ascending tie-break.",
            "return_accounting": "Daily open-to-open mark-to-market; fixed 1/3 initial-NAV notional per cohort; portfolio NAV compounds daily PnL.",
            "profit_factor_definition": "Daily net portfolio PnL gains divided by absolute daily net portfolio PnL losses; cohort PF also reported.",
            "win_rate_definition": "Primary win_rate is completed 3-day cohort net win rate; daily win rate also reported.",
            "turnover_definition": "Gross traded notional on entry plus exit, expressed as multiples of initial capital.",
        },
        "limitations": [
            "Fixed 10-symbol universe creates survivorship/selection bias; this is not a point-in-time historical universe.",
            "Binance SPOT prices are proxies for short-leg execution; perpetual funding, borrow availability, borrow fees, margin, liquidation and market impact are not observed.",
            "Short funding is a fixed 0.01% per day PROXY, not exchange-reported funding.",
            "No capacity or order-book slippage model; 0.02% per-side slippage is a fixed assumption.",
            "Experiments A and C are algebraically identical in combined PnL under equal dollar-neutral long/short weights; C is not independent evidence.",
            "2023 and 2024 are historical research windows, not untouched future validation after strategy selection.",
        ],
        "acceptance_gate": {
            "condition": "At least one experiment must have Profit Factor > 1.2 AND positive net return in both 2023 and 2024.",
            "gate_result": None,
            "passing_experiments": [],
        },
        "results": results,
    }
    passing = []
    for experiment in (
        "A_VOLUME_ONLY",
        "B_VOLUME_RSI_50_50_CS_ZSCORE",
        "C_MARKET_RESIDUAL",
    ):
        rows = [
            by_key[(year, experiment)] for year in TEST_YEARS
        ]
        if all(
            float(row["metrics"]["net_return"]) > 0.0
            and row["metrics"]["profit_factor"] is not None
            and float(row["metrics"]["profit_factor"]) > 1.2
            for row in rows
        ):
            passing.append(experiment)
    output["acceptance_gate"]["passing_experiments"] = passing
    output["acceptance_gate"]["gate_result"] = "PASS" if passing else "FAIL"
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
