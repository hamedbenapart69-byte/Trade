"""Experiment B: weekly cross-sectional long/short with BTC MA50 regime filter.

Research-only SPOT proxy. No perpetual execution/funding data is available.
Signal: Monday, using features and BTC regime known at prior UTC daily close.
Execution: Monday Open to same-week Friday Close; one non-overlapping cohort/week.
Note: Monday Open -> Friday Close is a weekly 5-session window, NOT 7 calendar days.
"""
from __future__ import annotations

from io import BytesIO
import json
from zipfile import ZipFile

import numpy as np
import pandas as pd
import requests

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
)
YEARS = (2023, 2024)
FIRST_MONTH = "2022-10"
LAST_MONTH = "2025-01"
FEE_PER_SIDE = 0.0004
SLIPPAGE_PER_SIDE = 0.0002
COST_PER_SIDE = FEE_PER_SIDE + SLIPPAGE_PER_SIDE
TOP_N = 2
LONG_WEIGHT = 0.5
SHORT_WEIGHT = 0.5
WEEKLY_SESSIONS = 5
WEEKS_PER_YEAR = 52
COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
]


def months_between(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def download_month(session: requests.Session, symbol: str, month: str) -> pd.DataFrame:
    filename = f"{symbol}-1d-{month}.zip"
    url = f"{BASE_URL}/{symbol}/1d/{filename}"
    response = session.get(url, timeout=90)
    response.raise_for_status()
    with ZipFile(BytesIO(response.content)) as archive:
        csvs = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"{filename}: expected exactly one CSV; found {csvs}")
        with archive.open(csvs[0]) as stream:
            frame = pd.read_csv(stream, header=None, names=COLUMNS)
    ts = pd.to_numeric(frame["open_time"], errors="coerce")
    ts = ts[np.isfinite(ts)]
    if ts.empty:
        raise ValueError(f"{filename}: no valid timestamps")
    median = float(ts.median())
    unit = "us" if median >= 1e14 else "ms" if median >= 1e11 else "s" if median >= 1e8 else None
    if unit is None:
        raise ValueError(f"{filename}: unsupported timestamp magnitude {median}")
    frame["open_time"] = pd.to_numeric(frame["open_time"], errors="coerce")
    frame = frame.loc[np.isfinite(frame["open_time"])].copy()
    frame["date"] = pd.to_datetime(frame["open_time"], unit=unit, utc=True).dt.floor("D")
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame[["date", "open", "high", "low", "close", "volume"]]
    if frame.empty or frame[["open", "high", "low", "close", "volume"]].isna().any().any():
        raise ValueError(f"{filename}: empty or invalid OHLCV")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError(f"{filename}: non-positive price")
    return frame


def wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values("date").copy()
    mean = out["volume"].rolling(20, min_periods=20).mean()
    std = out["volume"].rolling(20, min_periods=20).std(ddof=0)
    out["Volume_Z20"] = (out["volume"] - mean) / std.replace(0.0, np.nan)
    delta = out["close"].diff()
    avg_gain = wilder(delta.clip(lower=0.0), 14)
    avg_loss = wilder(-delta.clip(upper=0.0), 14)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out["RSI_14"] = 100.0 - 100.0 / (1.0 + rs)
    out.loc[(avg_loss == 0.0) & (avg_gain > 0.0), "RSI_14"] = 100.0
    out.loc[(avg_gain == 0.0) & (avg_loss > 0.0), "RSI_14"] = 0.0
    return out


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    month_list = months_between(FIRST_MONTH, LAST_MONTH)
    frames: dict[str, pd.DataFrame] = {}
    with requests.Session() as session:
        session.headers.update({"User-Agent": "Trade-Weekly-Regime-Research/1.0"})
        for symbol in SYMBOLS:
            pieces = [download_month(session, symbol, month) for month in month_list]
            raw = (
                pd.concat(pieces, ignore_index=True)
                .drop_duplicates("date")
                .sort_values("date")
                .reset_index(drop=True)
            )
            frames[symbol] = add_features(raw)

    common = set(frames[SYMBOLS[0]]["date"])
    for symbol in SYMBOLS[1:]:
        common.intersection_update(set(frames[symbol]["date"]))
    dates = pd.DatetimeIndex(sorted(common), name="date")
    if len(dates) < 800:
        raise ValueError(f"Insufficient common history: {len(dates)} days")
    expected = pd.date_range(dates.min(), dates.max(), freq="D", tz="UTC")
    if not dates.equals(expected):
        gaps = expected.difference(dates)
        raise ValueError("D1_DATA_GAP common dates: " + json.dumps([str(x.date()) for x in gaps[:30]]))

    opens = pd.DataFrame(index=dates)
    closes = pd.DataFrame(index=dates)
    feature_map = pd.DataFrame(index=dates)
    for symbol, frame in frames.items():
        indexed = frame.set_index("date").reindex(dates)
        opens[symbol] = indexed["open"].astype(float)
        closes[symbol] = indexed["close"].astype(float)
        # Point-in-time feature values available before the Monday open.
        feature_map[f"{symbol}:Volume_Z20"] = indexed["Volume_Z20"].shift(1)
        feature_map[f"{symbol}:RSI_14"] = indexed["RSI_14"].shift(1)

    btc_ma50 = closes["BTCUSDT"].rolling(50, min_periods=50).mean()
    # Monday's row is populated only with Sunday's BTC close and MA50.
    btc_close_prior = closes["BTCUSDT"].shift(1)
    btc_ma50_prior = btc_ma50.shift(1)
    if opens.isna().any().any() or closes.isna().any().any():
        raise ValueError("Missing OHLC prices in common calendar")
    return opens, closes, feature_map, btc_close_prior / btc_ma50_prior


def cross_section_z(series: pd.Series) -> pd.Series:
    sd = float(series.std(ddof=0))
    if not np.isfinite(sd) or sd <= 0:
        return pd.Series(np.nan, index=series.index)
    return (series - float(series.mean())) / sd


def select_basket(row: pd.Series) -> tuple[list[str], list[str]]:
    vol = pd.Series({s: row[f"{s}:Volume_Z20"] for s in SYMBOLS}, dtype=float)
    rsi = pd.Series({s: row[f"{s}:RSI_14"] for s in SYMBOLS}, dtype=float)
    if vol.isna().any() or rsi.isna().any():
        raise ValueError("Missing cross-sectional features at a scheduled Monday")
    score = 0.5 * cross_section_z(vol) + 0.5 * cross_section_z(rsi)
    if score.isna().any() or not np.isfinite(score.to_numpy()).all():
        raise ValueError("Invalid composite ranking score")
    ranked = sorted(SYMBOLS, key=lambda symbol: (-float(score[symbol]), symbol))
    return ranked[:TOP_N], ranked[-TOP_N:]


def metrics(returns: list[float]) -> dict[str, float | int | None]:
    arr = np.asarray(returns, dtype=float)
    nav = np.cumprod(1.0 + arr)
    peaks = np.maximum.accumulate(np.r_[1.0, nav])
    nav_with_initial = np.r_[1.0, nav]
    dd = nav_with_initial / peaks - 1.0
    sd = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    sharpe = float(np.mean(arr) / sd * np.sqrt(WEEKS_PER_YEAR)) if sd > 0 else None
    gains = float(arr[arr > 0].sum())
    losses = float(-arr[arr < 0].sum())
    return {
        "net_return": round(float(nav[-1] - 1.0), 10) if len(nav) else 0.0,
        "max_drawdown": round(float(np.min(dd)), 10),
        "sharpe_ratio_weekly_annualized": round(sharpe, 8) if sharpe is not None else None,
        "profit_factor_weekly_net": round(gains / losses, 8) if losses > 0 else None,
        "positive_weeks": int((arr > 0).sum()),
        "negative_weeks": int((arr < 0).sum()),
        "zero_return_weeks": int((arr == 0).sum()),
        "weeks": int(len(arr)),
    }


def run_year(
    year: int,
    opens: pd.DataFrame,
    closes: pd.DataFrame,
    features: pd.DataFrame,
    btc_ratio_prior: pd.Series,
) -> dict[str, object]:
    mondays = [
        d for d in opens.index
        if d.year == year and d.weekday() == 0
        and (d + pd.Timedelta(days=4)) in opens.index
        and (d + pd.Timedelta(days=4)).year == year
    ]
    if not mondays:
        raise ValueError(f"No complete Monday-Friday weeks in {year}")

    weekly_gross: list[float] = []
    weekly_net: list[float] = []
    market_weeks = 0
    cash_weeks = 0
    long_gross_sum = 0.0
    short_gross_sum = 0.0
    long_net_sum = 0.0
    short_net_sum = 0.0
    trade_rows: list[dict[str, object]] = []

    for monday in mondays:
        friday = monday + pd.Timedelta(days=4)
        ratio = float(btc_ratio_prior.loc[monday]) if pd.notna(btc_ratio_prior.loc[monday]) else np.nan
        if not np.isfinite(ratio):
            # Warm-up is not silently counted as market exposure; strict run records it as cash.
            cash_weeks += 1
            weekly_gross.append(0.0)
            weekly_net.append(0.0)
            trade_rows.append({
                "monday": str(monday.date()), "friday": str(friday.date()),
                "regime": "CASH_MA50_UNAVAILABLE", "gross_return": 0.0, "net_return": 0.0
            })
            continue

        # Exact requested rule: prior UTC daily BTC close strictly above prior MA50.
        if ratio <= 1.0:
            cash_weeks += 1
            weekly_gross.append(0.0)
            weekly_net.append(0.0)
            trade_rows.append({
                "monday": str(monday.date()), "friday": str(friday.date()),
                "regime": "CASH_BTC_CLOSE_LE_MA50",
                "btc_close_to_ma50_ratio_prior": round(ratio, 8),
                "gross_return": 0.0, "net_return": 0.0
            })
            continue

        longs, shorts = select_basket(features.loc[monday])
        long_returns = np.array([
            float(closes.loc[friday, s] / opens.loc[monday, s] - 1.0) for s in longs
        ])
        short_returns = np.array([
            float(closes.loc[friday, s] / opens.loc[monday, s] - 1.0) for s in shorts
        ])
        gross = LONG_WEIGHT * float(long_returns.mean()) - SHORT_WEIGHT * float(short_returns.mean())
        # 0.06% one-way cost on 100% gross notional, charged at entry and exit.
        round_trip_cost = 2.0 * COST_PER_SIDE * (LONG_WEIGHT + SHORT_WEIGHT)
        net = gross - round_trip_cost
        market_weeks += 1
        weekly_gross.append(gross)
        weekly_net.append(net)
        lg = LONG_WEIGHT * float(long_returns.mean())
        sg = -SHORT_WEIGHT * float(short_returns.mean())
        long_gross_sum += lg
        short_gross_sum += sg
        long_net_sum += lg - LONG_WEIGHT * 2.0 * COST_PER_SIDE
        short_net_sum += sg - SHORT_WEIGHT * 2.0 * COST_PER_SIDE
        trade_rows.append({
            "monday": str(monday.date()), "friday": str(friday.date()),
            "regime": "MARKET",
            "btc_close_to_ma50_ratio_prior": round(ratio, 8),
            "long_symbols": longs, "short_symbols": shorts,
            "gross_return": round(gross, 10),
            "net_return": round(net, 10),
            "round_trip_cost": round(round_trip_cost, 10)
        })

    gross_stats = metrics(weekly_gross)
    net_stats = metrics(weekly_net)
    total_sessions = len(mondays) * WEEKLY_SESSIONS
    market_sessions = market_weeks * WEEKLY_SESSIONS
    cash_sessions = cash_weeks * WEEKLY_SESSIONS
    # Weekend calendar days are also uninvested under Monday-open/Friday-close execution.
    weekend_days = len(mondays) * 2
    total_calendar_days = len(mondays) * 7
    calendar_market_days = market_sessions
    calendar_cash_days = cash_sessions + weekend_days

    return {
        "year": year,
        "status": "COMPLETED",
        "experiment": "B_VOLUME_RSI_50_50_CS_ZSCORE_WITH_BTC_MA50_FILTER",
        "metrics": {
            "gross_return": gross_stats["net_return"],
            "net_return": net_stats["net_return"],
            "max_drawdown": net_stats["max_drawdown"],
            "sharpe_ratio": net_stats["sharpe_ratio_weekly_annualized"],
            "profit_factor": net_stats["profit_factor_weekly_net"],
            "gross_metrics": gross_stats,
            "net_metrics": net_stats
        },
        "exposure": {
            "total_complete_weeks": len(mondays),
            "market_weeks": market_weeks,
            "cash_weeks": cash_weeks,
            "total_trading_sessions": total_sessions,
            "market_trading_sessions": market_sessions,
            "cash_trading_sessions": cash_sessions,
            "market_exposure_pct_of_trading_sessions": round(100.0 * market_sessions / total_sessions, 6),
            "cash_pct_of_trading_sessions": round(100.0 * cash_sessions / total_sessions, 6),
            "calendar_days_including_weekends": total_calendar_days,
            "calendar_market_days_approx": calendar_market_days,
            "calendar_cash_days_approx_including_weekends": calendar_cash_days,
            "calendar_market_exposure_pct_approx": round(100.0 * calendar_market_days / total_calendar_days, 6)
        },
        "long_leg": {
            "gross_contribution_sum_weekly": round(long_gross_sum, 10),
            "net_contribution_sum_weekly": round(long_net_sum, 10)
        },
        "short_leg": {
            "gross_contribution_sum_weekly": round(short_gross_sum, 10),
            "net_contribution_sum_weekly": round(short_net_sum, 10)
        },
        "cost_model": {
            "fee_per_side": FEE_PER_SIDE,
            "slippage_per_side": SLIPPAGE_PER_SIDE,
            "combined_execution_cost_per_side": COST_PER_SIDE,
            "round_trip_cost_on_100pct_gross_notional": round(2.0 * COST_PER_SIDE, 10),
            "funding": "UNAVAILABLE_NOT_INCLUDED_SPOT_PROXY"
        },
        "holding_period": {
            "requested_label": "7-day non-overlapping",
            "implemented_execution": "Monday Open to same-week Friday Close",
            "actual_window": "weekly 5-session window; not 7 calendar days",
            "non_overlapping": True
        },
        "weekly_trades": trade_rows
    }


def main() -> None:
    opens, closes, features, btc_ratio_prior = load_data()
    results = [run_year(y, opens, closes, features, btc_ratio_prior) for y in YEARS]
    output = {
        "schema_version": "2.0",
        "research_status": "EXPLORATORY_NOT_APPROVED_FOR_TRADING",
        "data": {
            "provider": "Binance Vision",
            "market": "SPOT",
            "interval": "1d",
            "universe": list(SYMBOLS),
            "test_years": list(YEARS),
            "warmup_start_month": FIRST_MONTH,
            "download_end_month": LAST_MONTH,
            "btc_regime_reference": "BTCUSDT close(T-1) > SMA50(BTCUSDT close)(T-1)",
            "short_perpetual_data": "UNAVAILABLE",
            "prices_and_volume": "REAL_BINANCE_VISION_SPOT"
        },
        "methodology": {
            "experiment": "B",
            "ranking": "0.5 * cross_section_z(Volume_Z20) + 0.5 * cross_section_z(RSI_14)",
            "long_selection": "top 2",
            "short_selection": "bottom 2",
            "regime_filter": "Only enter if BTC close(T-1) > BTC MA50(T-1); otherwise 100% cash for the entire weekly cohort.",
            "signal_day": "Monday",
            "feature_and_regime_asof": "prior UTC daily close (Sunday)",
            "entry": "Monday Open",
            "exit": "same-week Friday Close",
            "holding": "5 weekday sessions, non-overlapping; explicit Monday-Friday dates take precedence over inconsistent 7-calendar-day label",
            "portfolio": "50% gross long + 50% gross short",
            "costs": "0.04% fee + 0.02% slippage per side; entry and exit"
        },
        "results": results
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
