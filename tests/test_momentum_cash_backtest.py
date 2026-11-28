from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research import momentum_cash_backtest as model


def _row(*, regime=True, eligible=None, top2=None, returns=None):
    eligible = eligible or ["ETHUSDT", "NEARUSDT", "XRPUSDT", "SOLUSDT"]
    top2 = top2 or ["ETHUSDT", "NEARUSDT"]
    returns = returns or {"ETHUSDT": 0.10, "NEARUSDT": 0.20}
    return {
        "monday": pd.Timestamp("2026-01-05", tz="UTC"),
        "friday": pd.Timestamp("2026-01-09", tz="UTC"),
        "year": 2026,
        "eligible_assets": eligible,
        "scores": {symbol: float(i) for i, symbol in enumerate(eligible)},
        "top2": top2,
        "asset_returns": returns,
        "btc_bull_regime": regime,
    }


def test_weekly_cost_is_round_trip_and_applied_only_when_invested():
    result = model.evaluate([_row()])
    observed = result["entire_period"]["metrics"]["net_return"]
    expected = (0.10 + 0.20) / 2.0 - model.ROUND_TRIP_COST
    assert math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-10)
    assert result["entire_period"]["invested_weeks"] == 1
    assert result["entire_period"]["cash_weeks"] == 0


def test_bear_regime_is_one_hundred_percent_cash():
    result = model.evaluate([_row(regime=False)])
    assert result["entire_period"]["metrics"]["net_return"] == 0.0
    assert result["entire_period"]["invested_weeks"] == 0
    assert result["entire_period"]["cash_weeks"] == 1
    assert result["entire_period"]["cash_reason_counts"]["BTC_AT_OR_BELOW_SMA50"] == 1


def test_missing_btc_regime_fails_closed_to_cash():
    result = model.evaluate([_row(regime=None)])
    assert result["entire_period"]["metrics"]["net_return"] == 0.0
    assert result["entire_period"]["cash_reason_counts"]["BTC_SMA50_UNAVAILABLE"] == 1


def test_insufficient_cross_section_fails_closed_to_cash():
    result = model.evaluate([_row(eligible=["ETHUSDT", "NEARUSDT", "XRPUSDT"], top2=[])])
    assert result["entire_period"]["metrics"]["net_return"] == 0.0
    assert result["entire_period"]["cash_reason_counts"]["INSUFFICIENT_ELIGIBLE_ASSETS"] == 1


def test_metrics_compound_weekly_returns_and_measure_drawdown():
    result = model.metrics([0.10, -0.10, 0.0])
    assert math.isclose(result["net_return"], -0.01, abs_tol=1e-10)
    assert math.isclose(result["max_drawdown"], -0.10, abs_tol=1e-10)
    assert result["weeks"] == 3
    assert math.isclose(result["profit_factor"], 1.0, abs_tol=1e-10)


def test_constant_cross_section_is_not_given_a_fake_zscore():
    scores = model.zscore(pd.Series([7.0, 7.0, 7.0]))
    assert scores.isna().all()


def test_wilder_rsi_and_volume_features_are_warmed_up_without_future_rows():
    n = 70
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
        "open": np.linspace(100.0, 110.0, n),
        "high": np.linspace(101.0, 111.0, n),
        "low": np.linspace(99.0, 109.0, n),
        "close": np.linspace(100.0, 110.0, n),
        "volume": np.linspace(1000.0, 3000.0, n),
        "quote_asset_volume": np.linspace(100000.0, 300000.0, n),
    })
    featured = model.add_features(frame)
    assert featured.loc[19, "volume_z20"] == featured.loc[19, "volume_z20"]
    assert np.isnan(featured.loc[18, "volume_z20"])
    assert featured.loc[50, "observations_since_inception"] == 51
    assert featured.loc[50, "rsi14"] > 99.0
