#!/usr/bin/env python3
"""Apex-Synergy: causal cross-sectional crypto futures research engine.

Research-only Python harness. Production decisions remain C++ per MASTER SOURCE V19.
All structure labels derived from OHLCV are PROXY, not proof of institutional activity.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm
from backtest_guard import pbo, deflated_sharpe_ratio

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "INJUSDT", "UNIUSDT", "FILUSDT",
    "ARBUSDT", "ENAUSDT", "SUIUSDT", "TAOUSDT", "WLDUSDT",
    "ZECUSDT", "AAVEUSDT", "QNTUSDT", "RSRUSDT", "ONEUSDT",
]
START = pd.Timestamp("2024-11-01", tz="UTC")
END = pd.Timestamp("2026-10-31", tz="UTC")
TRAIN_MONTHS, TEST_MONTHS, STEP_MONTHS = 6, 2, 1

# Fixed, pre-registered engineering constants. No parameter sweep or post-result tuning.
ATR_N = 14
ADX_N = 14
MOMENTUM_WINDOWS = (20, 60)
VOLUME_WINDOW = 20
BREAKOUT_WINDOW = 20
FVG_MAX_AGE = 10
OB_LOOKBACK = 5
OB_MAX_DISTANCE_ATR = 2.0
VOLATILITY_WINDOW = 20
VOLATILITY_REGIME_LOOKBACK = 180
VOLATILITY_Q = 0.90
ADX_TREND_MIN = 20.0
TOP_BOTTOM_COUNT = 3
MAX_HOLD_DAYS = 10
INITIAL_STOP_ATR = 2.0
TRAIL_STOP_ATR = 2.5
FEE_PER_SIDE = 0.0004
SLIPPAGE_PER_SIDE = 0.0002
BASE_RISK_BUDGET = 0.0025
KELLY_FRACTION = 0.25
KELLY_LOOKBACK_TRADES = 60
KELLY_MIN_TRADES = 30
MAX_POSITION_WEIGHT = 0.20
MAX_GROSS_EXPOSURE = 1.00
MIN_FLOW_CONFIRMATION = 0.0

FACTOR_NAMES = [
    "momentum_20d", "momentum_60d", "abnormal_volume",
    "break_of_structure", "market_structure", "derivatives_flow",
]
VARIANTS = ["apex_composite"] + [f"ablation_{x}" for x in FACTOR_NAMES]


def _read_table(root: Path, stem: str) -> pd.DataFrame:
    pq = root / f"{stem}.parquet"
    csv = root / f"{stem}.csv"
    # CSV is retained in both source artifacts and avoids engine-specific parquet decoding.
    if csv.exists():
        return pd.read_csv(csv)
    if pq.exists():
        return pd.read_parquet(pq)
    raise FileNotFoundError(f"Required source file missing: {pq} or {csv}")


def _validate_manifest(path: Path, expected_status: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required source manifest missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("overall_status") != expected_status:
        raise ValueError(f"Dataset manifest is not {expected_status}: {path}")
    return payload


def load_inputs() -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, pd.DataFrame]], dict[str, Any]]:
    """Load source artifacts without filling missing values or fabricating observations."""
    ohlcv_root = Path("data/ohlcv")
    deriv_root = Path("data/derivatives")
    ohlcv_manifest = _validate_manifest(ohlcv_root / "dataset_manifest.json", "PASS")
    deriv_manifest = _validate_manifest(deriv_root / "derivatives_manifest.json", "PASS")

    ohlcv: dict[str, pd.DataFrame] = {}
    deriv: dict[str, dict[str, pd.DataFrame]] = {}
    coverage: dict[str, Any] = {}
    for symbol in SYMBOLS:
        x = _read_table(ohlcv_root, f"{symbol}_1d")
        x.columns = [str(c).strip().lower() for c in x.columns]
        if "open_time" in x.columns:
            idx = pd.to_datetime(x["open_time"], unit="ms", utc=True).dt.floor("D")
        elif "open_time_utc" in x.columns:
            idx = pd.to_datetime(x["open_time_utc"], utc=True).dt.floor("D")
        elif "date" in x.columns:
            idx = pd.to_datetime(x["date"], utc=True).dt.floor("D")
        else:
            raise ValueError(f"{symbol}: OHLCV timestamp column unavailable")
        x = x.assign(date=idx).sort_values("date").drop_duplicates("date").set_index("date")
        required = ["open", "high", "low", "close", "volume"]
        if not set(required).issubset(x.columns):
            raise ValueError(f"{symbol}: OHLCV schema mismatch")
        x = x.loc[START:END, required].astype(float)
        if len(x) != 730 or not x.index.is_monotonic_increasing or x.index.has_duplicates:
            raise ValueError(f"{symbol}: expected 730 unique sorted daily bars; got {len(x)}")
        if x[required].isna().any().any() or (x[["open", "high", "low", "close"]] <= 0).any().any() or (x.volume < 0).any():
            raise ValueError(f"{symbol}: invalid OHLCV values")
        if (x.high < x[["open", "close", "low"]].max(axis=1)).any() or (x.low > x[["open", "close", "high"]].min(axis=1)).any():
            raise ValueError(f"{symbol}: OHLC consistency failure")
        ohlcv[symbol] = x

        m = _read_table(deriv_root, f"{symbol}_metrics_1d")
        m["source_day"] = pd.to_datetime(m["source_day"], utc=True).dt.floor("D")
        m = m.sort_values("source_day").drop_duplicates("source_day").set_index("source_day")
        required_m = [
            "sum_open_interest_value", "count_long_short_ratio",
            "sum_toptrader_long_short_ratio", "sum_taker_long_short_vol_ratio",
        ]
        if not set(required_m).issubset(m.columns) or len(m) != 730:
            raise ValueError(f"{symbol}: derivatives metrics coverage/schema mismatch")
        f = _read_table(deriv_root, f"{symbol}_funding")
        f["calc_time_utc"] = pd.to_datetime(f["calc_time"], unit="ms", utc=True)
        f["date"] = f["calc_time_utc"].dt.floor("D")
        f["last_funding_rate"] = pd.to_numeric(f["last_funding_rate"], errors="coerce")
        funding_daily = f.groupby("date")["last_funding_rate"].sum(min_count=1)
        # All source fields are aligned with a one-day lag: no same-day end-of-day leakage.
        aligned = m[required_m].reindex(x.index).shift(1)
        aligned["funding_daily_sum"] = funding_daily.reindex(x.index).shift(1)
        deriv[symbol] = {"metrics": aligned}
        coverage[symbol] = {
            "ohlcv_rows": len(x),
            "metrics_rows": len(m),
            "funding_rows": len(f),
            "metrics_non_null": {c: int(m[c].notna().sum()) for c in required_m},
            "funding_days": int(funding_daily.notna().sum()),
        }

    meta = {
        "ohlcv_manifest": ohlcv_manifest,
        "derivatives_manifest": deriv_manifest,
        "coverage": coverage,
    }
    return ohlcv, deriv, meta


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = ADX_N) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def _order_block_score(x: pd.DataFrame, bos: pd.Series, atr: pd.Series) -> pd.Series:
    """OHLCV-derived order-block proxy: last opposing candle before a confirmed 20-bar BOS."""
    out = pd.Series(0.0, index=x.index)
    zone_side = 0
    zone_low = zone_high = np.nan
    for i in range(len(x)):
        close = float(x.close.iloc[i])
        if zone_side == 1 and close < zone_low:
            zone_side, zone_low, zone_high = 0, np.nan, np.nan
        elif zone_side == -1 and close > zone_high:
            zone_side, zone_low, zone_high = 0, np.nan, np.nan

        direction = int(bos.iloc[i]) if pd.notna(bos.iloc[i]) else 0
        if direction:
            start = max(0, i - OB_LOOKBACK)
            chosen = None
            for j in reversed(list(range(start, i))):
                if (direction == 1 and x.close.iloc[j] < x.open.iloc[j]) or (
                    direction == -1 and x.close.iloc[j] > x.open.iloc[j]
                ):
                    chosen = j
                    break
            if chosen is not None:
                zone_side = direction
                zone_low = float(x.low.iloc[chosen])
                zone_high = float(x.open.iloc[chosen]) if direction == 1 else float(x.high.iloc[chosen])
                if zone_low > zone_high:
                    zone_low, zone_high = zone_high, zone_low

        a = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else np.nan
        if zone_side and np.isfinite(a) and a > 0:
            midpoint = (zone_low + zone_high) / 2
            distance = abs(close - midpoint) / a
            if distance <= OB_MAX_DISTANCE_ATR:
                out.iloc[i] = zone_side * (1.0 - distance / OB_MAX_DISTANCE_ATR)
    return out


def build_features(
    symbol: str, x: pd.DataFrame, deriv: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    f = x.copy()
    tr = pd.concat(
        [f.high - f.low, (f.high - f.close.shift()).abs(), (f.low - f.close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    f["atr"] = tr.rolling(ATR_N, min_periods=ATR_N).mean()
    f["adx"] = _adx(f.high, f.low, f.close)
    f["momentum_20d"] = f.close.pct_change(20)
    f["momentum_60d"] = f.close.pct_change(60)
    f["relative_volume"] = f.volume / f.volume.rolling(VOLUME_WINDOW).mean().shift(1)

    prior_high = f.high.rolling(BREAKOUT_WINDOW).max().shift(1)
    prior_low = f.low.rolling(BREAKOUT_WINDOW).min().shift(1)
    f["bos"] = np.select([f.close > prior_high, f.close < prior_low], [1.0, -1.0], default=0.0)

    sweep_low = f.low < prior_low
    sweep_high = f.high > prior_high
    f["liquidity_sweep"] = np.select(
        [sweep_low & (f.close > prior_low), sweep_high & (f.close < prior_high)],
        [1.0, -1.0], default=0.0,
    )

    bull_fvg = f.low > f.high.shift(2)
    bear_fvg = f.high < f.low.shift(2)
    fvg_event = pd.Series(np.select([bull_fvg, bear_fvg], [1.0, -1.0], default=np.nan), index=f.index)
    f["fvg_direction"] = fvg_event.ffill(limit=FVG_MAX_AGE).fillna(0.0)
    f["order_block_score"] = _order_block_score(f, f["bos"], f["atr"])
    f["market_structure"] = (
        f["liquidity_sweep"] + f["fvg_direction"] + f["order_block_score"] + f["bos"]
    ) / 4.0

    d = deriv["metrics"].reindex(f.index)
    f["oi_change_5d"] = d["sum_open_interest_value"].pct_change(5)
    f["global_ls_ratio"] = d["count_long_short_ratio"]
    f["toptrader_position_ls"] = d["sum_toptrader_long_short_ratio"]
    f["taker_buy_sell_ratio"] = d["sum_taker_long_short_vol_ratio"]
    f["funding_daily_sum"] = d["funding_daily_sum"]
    f["symbol"] = symbol
    return f


def build_panel(features: dict[str, pd.DataFrame]) -> pd.DataFrame:
    frames = []
    for symbol, f in features.items():
        z = f.reset_index().rename(columns={f.index.name or "index": "date"})
        if "date" not in z.columns:
            z = z.rename(columns={z.columns[0]: "date"})
        frames.append(z)
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"], utc=True)
    panel = panel.sort_values(["date", "symbol"]).reset_index(drop=True)

    def cs_rank(col: str, reverse: bool = False) -> pd.Series:
        r = panel.groupby("date")[col].rank(pct=True, method="average")
        if reverse:
            r = 1.0 - r
        return (r - 0.5) * 2.0

    panel["factor_mom20"] = cs_rank("momentum_20d")
    panel["factor_mom60"] = cs_rank("momentum_60d")
    panel["factor_volume"] = cs_rank("relative_volume")
    panel["factor_bos"] = panel["bos"]
    panel["factor_structure"] = panel["market_structure"]

    # Derivatives are real Binance Vision observations lagged by one UTC day.
    # Missing components remain NaN; no zero-fill or forward-fill is used.
    panel["flow_oi"] = np.sign(panel["momentum_20d"]) * cs_rank("oi_change_5d")
    panel["flow_funding"] = cs_rank("funding_daily_sum", reverse=True)
    panel["flow_global_ls"] = cs_rank("global_ls_ratio", reverse=True)
    panel["flow_toptrader_ls"] = cs_rank("toptrader_position_ls", reverse=True)
    panel["flow_taker"] = cs_rank("taker_buy_sell_ratio")
    flow_cols = ["flow_oi", "flow_funding", "flow_global_ls", "flow_toptrader_ls", "flow_taker"]
    panel["factor_flow"] = panel[flow_cols].mean(axis=1, skipna=True)
    panel["flow_components_available"] = panel[flow_cols].notna().sum(axis=1)

    factor_cols = [
        "factor_mom20", "factor_mom60", "factor_volume",
        "factor_bos", "factor_structure", "factor_flow",
    ]
    panel["apex_score"] = panel[factor_cols].mean(axis=1, skipna=False)
    # At least four of five flow observations are required; unavailable data is never neutralized.
    panel.loc[panel["flow_components_available"] < 4, "apex_score"] = np.nan

    btc = panel[panel.symbol == "BTCUSDT"].set_index("date").sort_index()
    btc_ret = btc.close.pct_change()
    btc_vol = btc_ret.rolling(VOLATILITY_WINDOW).std() * math.sqrt(365)
    vol_limit = btc_vol.rolling(VOLATILITY_REGIME_LOOKBACK, min_periods=60).quantile(VOLATILITY_Q).shift(1)
    regime = pd.Series(
        np.select(
            [btc_vol > vol_limit, btc.adx >= ADX_TREND_MIN],
            ["VOLATILE", "TREND"],
            default="RANGE",
        ),
        index=btc.index,
    )
    panel["market_regime"] = panel.date.map(regime)
    return panel


@dataclass
class Position:
    symbol: str
    side: int
    entry_date: pd.Timestamp
    entry_price: float
    prev_close: float
    stop: float
    high_water: float
    low_water: float
    weight: float
    hold_days: int = 0
    funding_paid: float = 0.0


def _kelly_risk(history: list[float]) -> tuple[float, str]:
    """Fractional Kelly from past closed trades only; warm-up is fixed and disclosed."""
    recent = history[-KELLY_LOOKBACK_TRADES:]
    if len(recent) < KELLY_MIN_TRADES:
        return BASE_RISK_BUDGET, "WARMUP_FIXED_RISK"
    wins = [x for x in recent if x > 0]
    losses = [-x for x in recent if x < 0]
    if not wins or not losses:
        return 0.0, "KELLY_ZERO_OR_UNDEFINED"
    p = len(wins) / len(recent)
    b = float(np.mean(wins) / np.mean(losses))
    full_kelly = p - (1.0 - p) / b if b > 0 else 0.0
    return min(BASE_RISK_BUDGET, max(0.0, KELLY_FRACTION * full_kelly)), "FRACTIONAL_KELLY"


def _select_candidates(day: pd.DataFrame) -> list[tuple[str, int]]:
    eligible = day[(day.market_regime == "TREND") & day.apex_score.notna()].copy()
    if eligible.empty:
        return []
    eligible = eligible.sort_values("apex_score", ascending=False)
    longs = eligible.head(TOP_BOTTOM_COUNT)
    shorts = eligible.tail(TOP_BOTTOM_COUNT).sort_values("apex_score")
    selected: list[tuple[str, int]] = []
    for row in longs.itertuples():
        if row.apex_score > 0 and row.factor_flow > MIN_FLOW_CONFIRMATION:
            selected.append((row.symbol, 1))
    for row in shorts.itertuples():
        if row.apex_score < 0 and row.factor_flow < -MIN_FLOW_CONFIRMATION:
            selected.append((row.symbol, -1))
    return selected


def simulate(
    panel: pd.DataFrame,
    score_col: str = "apex_score",
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    report_start: pd.Timestamp | None = None,
    use_kelly: bool = True,
) -> tuple[pd.Series, list[dict[str, Any]], dict[str, Any]]:
    """Causal daily portfolio simulation; signals at close t enter at open t+1."""
    dates = sorted(panel.date.unique())
    by_date = {d: panel[panel.date == d].set_index("symbol") for d in dates}
    positions: dict[str, Position] = {}
    closed_returns: list[float] = []
    trades: list[dict[str, Any]] = []
    daily_returns: dict[pd.Timestamp, float] = {}
    risk_modes: dict[str, int] = {}
    start = start or pd.Timestamp(dates[0])
    end = end or pd.Timestamp(dates[-1])
    report_start = report_start or start
    date_positions = {d: i for i, d in enumerate(dates)}

    for date in dates:
        dt = pd.Timestamp(date)
        day = by_date[date]
        pnl = 0.0
        exited_today: set[str] = set()
        date_i = date_positions[date]
        is_last_training_bar = (
            report_start is not None
            and dt < report_start
            and date_i + 1 < len(dates)
            and pd.Timestamp(dates[date_i + 1]) >= report_start
        )

        # Mark/exit positions that were already open before today's bar.
        for symbol in list(positions):
            pos = positions[symbol]
            if symbol not in day.index:
                continue
            prev_atr = np.nan
            if date_i > 0:
                prev_row = by_date[dates[date_i - 1]].loc[symbol]
                prev_atr = float(prev_row.atr) if pd.notna(prev_row.atr) else np.nan
            if np.isfinite(prev_atr) and prev_atr > 0:
                if pos.side == 1:
                    pos.stop = max(pos.stop, pos.high_water - TRAIL_STOP_ATR * prev_atr)
                else:
                    pos.stop = min(pos.stop, pos.low_water + TRAIL_STOP_ATR * prev_atr)

            row = day.loc[symbol]
            if pos.side == 1:
                hit = float(row.low) <= pos.stop
                fill = min(float(row.open), pos.stop) if hit else float(row.close)
            else:
                hit = float(row.high) >= pos.stop
                fill = max(float(row.open), pos.stop) if hit else float(row.close)

            pos.hold_days += 1
            regime_exit = row.market_regime != "TREND"
            score = float(row[score_col]) if pd.notna(row[score_col]) else 0.0
            reversal_exit = score * pos.side < 0
            time_exit = pos.hold_days >= MAX_HOLD_DAYS
            exit_now = hit or regime_exit or reversal_exit or time_exit or is_last_training_bar
            reason = "ATR_TRAILING_STOP" if hit else (
                "REGIME_EXIT" if regime_exit else (
                    "FACTOR_REVERSAL" if reversal_exit else (
                        "MAX_HOLD" if time_exit else ("TRAIN_OOS_FLATTEN" if is_last_training_bar else None)
                    )
                )
            )
            funding = float(row.funding_daily_sum) if pd.notna(row.funding_daily_sum) else 0.0
            # Funding is charged/credited according to position direction.
            asset_return = pos.side * (fill / pos.prev_close - 1.0) - pos.side * funding
            if exit_now:
                asset_return -= FEE_PER_SIDE + SLIPPAGE_PER_SIDE
                pnl += pos.weight * asset_return
                net = pos.side * (fill / pos.entry_price - 1.0) - 2 * (FEE_PER_SIDE + SLIPPAGE_PER_SIDE) - pos.side * pos.funding_paid - pos.side * funding
                trade = {
                    "symbol": symbol, "side": "LONG" if pos.side == 1 else "SHORT",
                    "entry_date": pos.entry_date.date().isoformat(), "exit_date": dt.date().isoformat(),
                    "entry_price": pos.entry_price, "exit_price": fill,
                    "net_return": net, "exit_reason": reason, "weight": pos.weight,
                }
                trades.append(trade)
                closed_returns.append(net)
                del positions[symbol]
                exited_today.add(symbol)
            else:
                pnl += pos.weight * asset_return
                pos.prev_close = float(row.close)
                pos.high_water = max(pos.high_water, float(row.high))
                pos.low_water = min(pos.low_water, float(row.low))
                pos.funding_paid += funding

        # New entries use yesterday's close-ranked signals and today's open.
        if dt >= start and dt <= end and len(dates) > 1 and not is_last_training_bar:
            prev_idx = date_positions[date] - 1
            if prev_idx >= 0:
                prev_day = by_date[dates[prev_idx]].reset_index()
                if score_col != "apex_score":
                    # Ablation strategy ranks on the named factor while retaining identical risk/exit logic.
                    prev_day["apex_score"] = prev_day[score_col]
                candidates = _select_candidates(prev_day)
                available = [c for c in candidates if c[0] not in positions and c[0] not in exited_today]
                if use_kelly:
                    risk_pct, mode = _kelly_risk(closed_returns)
                else:
                    risk_pct, mode = BASE_RISK_BUDGET, "FIXED_RISK_RESEARCH_BASELINE"
                risk_modes[mode] = risk_modes.get(mode, 0) + 1
                for symbol, side in available:
                    if len(positions) >= 2 * TOP_BOTTOM_COUNT:
                        break
                    row = day.loc[symbol]
                    sig = by_date[dates[prev_idx]].loc[symbol]
                    if not np.isfinite(sig.atr) or sig.atr <= 0:
                        continue
                    entry = float(row.open) * (1 + side * SLIPPAGE_PER_SIDE)
                    stop_distance = INITIAL_STOP_ATR * float(sig.atr)
                    stop_pct = stop_distance / entry
                    if stop_pct <= 0:
                        continue
                    raw_weight = min(MAX_POSITION_WEIGHT, risk_pct / stop_pct)
                    current_gross = sum(p.weight for p in positions.values())
                    weight = min(raw_weight, max(0.0, MAX_GROSS_EXPOSURE - current_gross))
                    if weight <= 0:
                        continue
                    stop = entry - side * stop_distance
                    pos = Position(
                        symbol=symbol, side=side, entry_date=dt, entry_price=entry,
                        prev_close=entry, stop=stop, high_water=entry, low_water=entry,
                        weight=weight,
                    )
                    # Entry-day return is measured from the executable open, not the prior close.
                    if side == 1:
                        hit = float(row.low) <= stop
                        fill = min(float(row.open), stop) if hit else float(row.close)
                    else:
                        hit = float(row.high) >= stop
                        fill = max(float(row.open), stop) if hit else float(row.close)
                    funding = float(row.funding_daily_sum) if pd.notna(row.funding_daily_sum) else 0.0
                    entry_and_exit_cost = (2.0 if hit else 1.0) * (FEE_PER_SIDE + SLIPPAGE_PER_SIDE)
                    asset_return = side * (fill / entry - 1.0) - entry_and_exit_cost - side * funding
                    pnl += weight * asset_return
                    if hit:
                        exit_net = side * (fill / entry - 1.0) - 2 * (FEE_PER_SIDE + SLIPPAGE_PER_SIDE) - side * funding
                        trades.append({
                            "symbol": symbol, "side": "LONG" if side == 1 else "SHORT",
                            "entry_date": dt.date().isoformat(), "exit_date": dt.date().isoformat(),
                            "entry_price": entry, "exit_price": fill, "net_return": exit_net,
                            "exit_reason": "SAME_DAY_INITIAL_STOP", "weight": weight,
                        })
                        closed_returns.append(exit_net)
                        exited_today.add(symbol)
                    else:
                        pos.prev_close = float(row.close)
                        pos.high_water = max(entry, float(row.high))
                        pos.low_water = min(entry, float(row.low))
                        pos.hold_days = 1
                        pos.funding_paid = funding
                        positions[symbol] = pos

        daily_returns[dt] = pnl

    # Close residual positions at the final observed close; terminal closure is included in the last return.
    if positions:
        dt = pd.Timestamp(dates[-1])
        day = by_date[dates[-1]]
        for symbol, pos in list(positions.items()):
            row = day.loc[symbol]
            fill = float(row.close)
            asset_return = pos.side * (fill / pos.prev_close - 1.0) - (FEE_PER_SIDE + SLIPPAGE_PER_SIDE)
            daily_returns[dt] = daily_returns.get(dt, 0.0) + pos.weight * asset_return
            net = pos.side * (fill / pos.entry_price - 1.0) - 2 * (FEE_PER_SIDE + SLIPPAGE_PER_SIDE) - pos.side * pos.funding_paid
            trades.append({
                "symbol": symbol, "side": "LONG" if pos.side == 1 else "SHORT",
                "entry_date": pos.entry_date.date().isoformat(), "exit_date": dt.date().isoformat(),
                "entry_price": pos.entry_price, "exit_price": fill, "net_return": net,
                "exit_reason": "END_OF_DATA", "weight": pos.weight,
            })
            closed_returns.append(net)

    returns = pd.Series(daily_returns, dtype=float).sort_index()
    returns = returns.loc[(returns.index >= report_start) & (returns.index <= end)]
    trades = [t for t in trades if report_start.date().isoformat() <= t["entry_date"] <= end.date().isoformat()]
    final_kelly, final_kelly_mode = _kelly_risk(closed_returns)
    return returns, trades, {
        "kelly_modes": risk_modes,
        "closed_trades_including_training": len(closed_returns),
        "training_and_oos_trade_mean": float(np.mean(closed_returns)) if closed_returns else None,
        "final_kelly_risk_budget": final_kelly,
        "final_kelly_mode": final_kelly_mode,
        "kelly_applied_to_this_run": use_kelly,
    }


def compute_metrics(returns: pd.Series, trades: list[dict[str, Any]]) -> dict[str, Any]:
    r = returns.fillna(0.0).astype(float)
    equity = (1.0 + r).cumprod()
    drawdown = equity / equity.cummax() - 1.0 if len(equity) else pd.Series(dtype=float)
    wins = [float(t["net_return"]) for t in trades if t["net_return"] > 0]
    losses = [-float(t["net_return"]) for t in trades if t["net_return"] < 0]
    gross_loss = sum(losses)
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return {
        "win_rate": len(wins) / len(trades) if trades else None,
        "profit_factor": sum(wins) / gross_loss if gross_loss > 0 else (None if wins else 0.0),
        "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
        "sharpe": float(r.mean() / sd * math.sqrt(365)) if sd > 0 else 0.0,
        "total_trades": len(trades),
        "net_return": float(equity.iloc[-1] - 1.0) if len(equity) else 0.0,
        "annualized_volatility": float(sd * math.sqrt(365)),
        "avg_trade_return": float(np.mean([t["net_return"] for t in trades])) if trades else None,
    }


def make_walk_forward(index: pd.DatetimeIndex) -> list[dict[str, pd.Timestamp]]:
    folds = []
    first_test = index.min() + pd.DateOffset(months=TRAIN_MONTHS)
    last = index.max()
    test_start = first_test
    while test_start <= last:
        test_end = min(test_start + pd.DateOffset(months=TEST_MONTHS), last + pd.Timedelta(days=1))
        scored_end = min(test_start + pd.DateOffset(months=STEP_MONTHS), test_end)
        folds.append({
            "train_start": test_start - pd.DateOffset(months=TRAIN_MONTHS),
            "test_start": test_start,
            "test_end": test_end,
            "scored_end": scored_end,
        })
        test_start += pd.DateOffset(months=STEP_MONTHS)
    return folds


def baseline_returns(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.Series]:
    """Simple non-optimized reference baselines, not candidates for production."""
    piv = panel.pivot(index="date", columns="symbol", values="close").sort_index()
    daily_asset = piv.pct_change().replace([np.inf, -np.inf], np.nan)
    out: dict[str, pd.Series] = {}
    out["equal_weight_buy_hold"] = daily_asset.mean(axis=1).fillna(0.0).loc[start:end]

    rows = []
    for symbol, g in panel.groupby("symbol"):
        g = g.sort_values("date").copy()
        e20 = g.close.ewm(span=20, adjust=False).mean()
        e50 = g.close.ewm(span=50, adjust=False).mean()
        side = np.sign(e20 - e50).shift(1).fillna(0.0)
        ret = g.close.pct_change().fillna(0.0)
        rows.append(pd.Series(side.to_numpy() * ret.to_numpy(), index=g.date.to_numpy(), name=symbol))
    out["ema20_50"] = pd.concat(rows, axis=1).mean(axis=1).sort_index().loc[start:end]

    rows = []
    for symbol, g in panel.groupby("symbol"):
        g = g.sort_values("date").copy()
        delta = g.close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        side = pd.Series(np.where(rsi < 30, 1.0, np.where(rsi > 70, -1.0, 0.0)), index=g.index).shift(1).fillna(0.0)
        ret = g.close.pct_change().fillna(0.0)
        rows.append(pd.Series(side.to_numpy() * ret.to_numpy(), index=g.date.to_numpy(), name=symbol))
    out["rsi14_30_70"] = pd.concat(rows, axis=1).mean(axis=1).sort_index().loc[start:end]
    return out


def main() -> None:
    ohlcv, deriv, meta = load_inputs()
    features = {s: build_features(s, ohlcv[s], deriv[s]) for s in SYMBOLS}
    panel = build_panel(features)
    folds = make_walk_forward(pd.DatetimeIndex(sorted(panel.date.unique())))
    if not folds:
        raise RuntimeError("Insufficient history for the registered 6m/2m/1m walk-forward schedule")
    oos_start = folds[0]["test_start"]
    oos_end = END

    # Main strategy is fixed. Ablations are pre-registered diagnostics for PBO, not parameter tuning.
    candidate_returns: dict[str, pd.Series] = {}
    candidate_trades: dict[str, list[dict[str, Any]]] = {}
    candidate_diag: dict[str, Any] = {}
    ablation_columns = {
        "momentum_20d": "factor_mom20",
        "momentum_60d": "factor_mom60",
        "abnormal_volume": "factor_volume",
        "break_of_structure": "factor_bos",
        "market_structure": "factor_structure",
        "derivatives_flow": "factor_flow",
    }
    for variant in VARIANTS:
        score_col = "apex_score" if variant == "apex_composite" else ablation_columns[variant.removeprefix("ablation_")]
        r, t, diag = simulate(
            panel, score_col=score_col, start=START, end=oos_end,
            report_start=oos_start, use_kelly=False,
        )
        candidate_returns[variant] = r
        candidate_trades[variant] = t
        candidate_diag[variant] = diag

    index = pd.date_range(oos_start, oos_end, freq="D", tz="UTC")
    matrix = np.column_stack([candidate_returns[v].reindex(index).fillna(0.0).to_numpy() for v in VARIANTS])
    pbo_result = pbo(matrix, n_splits=8)
    pbo_value = float(pbo_result.pbo)
    main_returns = candidate_returns["apex_composite"].reindex(index).fillna(0.0)
    main_trades = candidate_trades["apex_composite"]
    kelly_returns_raw, kelly_trades, kelly_diagnostics = simulate(
        panel, score_col="apex_score", start=START, end=oos_end,
        report_start=oos_start, use_kelly=True,
    )
    kelly_returns = kelly_returns_raw.reindex(index).fillna(0.0)
    dsr_probability = float(deflated_sharpe_ratio(main_returns.to_numpy(), n_trials=len(VARIANTS)))
    dsr_z = float(norm.ppf(np.clip(dsr_probability, 1e-12, 1 - 1e-12)))
    overall = compute_metrics(main_returns, main_trades)

    fold_results = []
    for fold in folds:
        a, b = fold["test_start"], fold["scored_end"]
        if a > oos_end or a >= b:
            continue
        fr = main_returns.loc[(main_returns.index >= a) & (main_returns.index < b)]
        ft = [t for t in main_trades if a.date().isoformat() <= t["entry_date"] < b.date().isoformat()]
        fold_results.append({
            **{k: v.date().isoformat() for k, v in fold.items()},
            "scored_oos_end": b.date().isoformat(),
            "metrics": compute_metrics(fr, ft),
        })

    baselines = {}
    for name, r in baseline_returns(panel, oos_start, oos_end).items():
        baselines[name] = compute_metrics(r, [])

    gates = {
        "win_rate_gt_55_or_profit_factor_gt_1_5": (
            (overall["win_rate"] is not None and overall["win_rate"] > 0.55)
            or (overall["profit_factor"] is not None and overall["profit_factor"] > 1.5)
        ),
        "pbo_lt_0_40": pbo_value < 0.40,
        "dsr_z_gt_1_0": dsr_z > 1.0,
        "max_drawdown_lt_20pct": overall["max_drawdown"] > -0.20,
    }
    gates["status"] = "PASS" if all(v for k, v in gates.items() if k != "status") else "NOT_VALIDATED"

    summary = {
        "schema": "apex_synergy.backtest.v1",
        "system": "Apex-Synergy",
        "status": "RESEARCH_ONLY",
        "validation_status": gates["status"],
        "data": {
            "ohlcv_source": "Binance Vision USD-M Futures daily klines",
            "derivatives_source": "Binance Vision USD-M Futures daily metrics and funding archives",
            "ohlcv_type": "REAL",
            "derivatives_type": "REAL",
            "symbols": len(SYMBOLS),
            "bars_per_symbol": 730,
            "ohlcv_run_id": 45055606760,
            "derivatives_run_id": 45055804237,
            "metrics_availability_lag_days": 1,
            "coverage": meta["coverage"],
            "order_book_depth": "UNAVAILABLE",
            "institutional_order_flow": "UNAVAILABLE",
            "ohlcv_structure_features": "PROXY",
        },
        "architecture": {
            "regime_filter": "BTCUSDT ADX(14) >= 20 and 20d annualized realized volatility <= prior 180d 90th percentile; otherwise RANGE or VOLATILE. Trade only TREND.",
            "cross_sectional_factors": FACTOR_NAMES,
            "factor_weights": "Equal weight 1/6; fixed before run; no optimization.",
            "candidate_selection": "Top 3 positive composite scores LONG and bottom 3 negative composite scores SHORT, only with same-direction derivatives flow confirmation.",
            "structure_features": {
                "BOS": "Close beyond prior 20-day high/low; PROXY",
                "FVG": "Three-candle gap, active for at most 10 bars; PROXY",
                "Order_Block": "Last opposing candle within five bars before BOS; zone invalidated by close-through; PROXY",
                "Liquidity_Sweep": "Prior 20-day high/low breach followed by same-bar close reclaim; PROXY",
            },
            "derivatives_confirmation": {
                "OI": "5-day change in USD open-interest value, one-day lag",
                "Funding": "Sum of funding payments per UTC day, one-day lag",
                "Long_Short": "Global and top-trader position ratios, one-day lag",
                "Taker_Flow": "Taker buy/sell volume ratio, one-day lag",
                "missing_policy": "No zero-fill; at least four of five flow components required",
            },
            "risk": {
                "volatility_sizing": "Position risk weight inversely proportional to initial ATR stop distance",
                "kelly": "0.25 fractional Kelly from prior 60 closed trades, only after 30 observations",
                "kelly_warmup": f"Fixed {BASE_RISK_BUDGET:.4%} risk budget until 30 closed trades; disclosed fallback",
                "initial_stop": f"{INITIAL_STOP_ATR} x ATR({ATR_N})",
                "trailing_stop": f"{TRAIL_STOP_ATR} x ATR({ATR_N}), updated using prior-bar ATR",
                "max_holding_days": MAX_HOLD_DAYS,
                "max_position_weight": MAX_POSITION_WEIGHT,
                "max_gross_exposure": MAX_GROSS_EXPOSURE,
            },
            "execution_costs": {
                "fee_per_side": FEE_PER_SIDE,
                "slippage_per_side": SLIPPAGE_PER_SIDE,
                "funding": "Observed historical funding, lagged one UTC day",
            },
        },
        "walk_forward": {
            "train_months": TRAIN_MONTHS,
            "test_months": TEST_MONTHS,
            "step_months": STEP_MONTHS,
            "fold_count": len(fold_results),
            "oos_start": oos_start.date().isoformat(),
            "oos_end": oos_end.date().isoformat(),
            "overlap_policy": "Unique one-month scored window per rolling fold; OOS daily returns are not duplicated.",
            "fold_results": fold_results,
        },
        "metrics": {
            **overall,
            "pbo": pbo_value,
            "dsr_probability": dsr_probability,
            "dsr_z": dsr_z,
            "candidate_count_for_pbo_dsr": len(VARIANTS),
        },
        "gates": gates,
        "baselines": baselines,
        "candidate_diagnostics": {
            name: compute_metrics(candidate_returns[name].reindex(index).fillna(0.0), candidate_trades[name])
            for name in VARIANTS
        },
        "risk_engine_diagnostics": {
            **kelly_diagnostics,
            "kelly_managed_oos_metrics": compute_metrics(kelly_returns, kelly_trades),
        },
        "fixed_risk_research_metrics": overall,
        "limitations": [
            "Apex-Synergy is a research implementation, not a production C++ signal engine.",
            "OHLCV-derived BOS, FVG, order blocks and sweeps are PROXY structure labels, not verified institutional orders.",
            "Historical order-book depth and true aggressor-level order flow are UNAVAILABLE.",
            "No XGBoost model was trained: 730 daily bars per symbol are insufficient to justify a high-capacity learner without stronger labeled data and leakage controls.",
            "Kelly warm-up uses the fixed disclosed fallback until 30 prior closed trades; no future outcomes are used.",
            "The 25-symbol universe is fixed and survivorship/contract-list bias may remain.",
            "No exchange account, private key, or order execution is used.",
        ],
    }

    out = Path("results")
    out.mkdir(exist_ok=True)
    (out / "apex_synergy_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (out / "apex_synergy_trades.json").write_text(json.dumps(main_trades, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (out / "apex_synergy_daily_returns.csv").write_text(
        main_returns.rename("portfolio_return").to_csv(), encoding="utf-8"
    )
    (out / "apex_synergy_candidate_metrics.json").write_text(
        json.dumps(summary["candidate_diagnostics"], indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps({
        "system": summary["system"], "validation_status": gates["status"],
        "metrics": summary["metrics"], "gates": gates,
        "oos": [summary["walk_forward"]["oos_start"], summary["walk_forward"]["oos_end"]],
    }, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
