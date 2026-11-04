"""Transparent quantitative factor models.

Outputs are normalized factor scores (0-100), NOT probabilities of profit. Each model
requires explicit numeric evidence; absent inputs produce an unavailable model result.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Mapping


@dataclass(frozen=True)
class ModelScore:
    name: str
    score: float | None
    coverage: float
    inputs_used: tuple[str, ...]
    status: str


def _number(features: Mapping[str, object], key: str) -> float | None:
    value = features.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if isfinite(result) else None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _mapped(value: float, scale: float) -> float:
    return _clamp(50.0 + 50.0 * value / scale)


def _result(name: str, features: Mapping[str, object], formula) -> ModelScore:
    required = formula[0]
    vals = {key: _number(features, key) for key in required}
    used = tuple(key for key, value in vals.items() if value is not None)
    coverage = len(used) / len(required) if required else 1.0
    if coverage < 1.0:
        return ModelScore(name, None, coverage, used, "INSUFFICIENT_INPUTS")
    score = _clamp(float(formula[1](vals)))
    return ModelScore(name, round(score, 2), coverage, used, "CALCULATED")


def score_all(features: Mapping[str, object]) -> tuple[ModelScore, ...]:
    """Calculate ten distinct factor scores from explicitly supplied normalized features.

    Feature conventions are documented in docs/QUANT-MODELS.md. Scores are not
    calibrated probabilities and must not be represented as such.
    """
    specs = [
        ("momentum", ("return_1h_pct", "return_4h_pct", "return_1d_pct", "rsi_14"),
         lambda v: 0.25*_mapped(v["return_1h_pct"], 3) + 0.30*_mapped(v["return_4h_pct"], 6) + 0.30*_mapped(v["return_1d_pct"], 10) + 0.15*_clamp(v["rsi_14"])),
        ("early_accumulation", ("volume_ratio_20", "obv_slope_pct", "price_return_7d_pct", "range_compression_pct"),
         lambda v: 0.30*_mapped(v["volume_ratio_20"]-1, 2) + 0.30*_mapped(v["obv_slope_pct"], 10) + 0.20*_mapped(-abs(v["price_return_7d_pct"]), 10) + 0.20*_mapped(v["range_compression_pct"], 50)),
        ("breakout", ("distance_to_resistance_pct", "volume_ratio_20", "adx_14", "close_above_resistance"),
         lambda v: 0.25*_mapped(-v["distance_to_resistance_pct"], 5) + 0.25*_mapped(v["volume_ratio_20"]-1, 2) + 0.25*_clamp(v["adx_14"]*2) + 0.25*(100 if v["close_above_resistance"] >= 1 else 0)),
        ("mean_reversion", ("rsi_14", "bollinger_percent_b", "zscore_20", "adx_14"),
         lambda v: 0.30*_clamp(100-abs(v["rsi_14"]-35)*2) + 0.25*_clamp(100-abs(v["bollinger_percent_b"])*50) + 0.25*_clamp(100-abs(v["zscore_20"]+2)*25) + 0.20*_clamp(100-v["adx_14"]*2)),
        ("relative_strength", ("relative_return_7d_vs_btc_pct", "relative_return_30d_vs_btc_pct"),
         lambda v: 0.45*_mapped(v["relative_return_7d_vs_btc_pct"], 10) + 0.55*_mapped(v["relative_return_30d_vs_btc_pct"], 20)),
        ("fundamental_growth", ("revenue_growth_yoy_pct", "active_users_growth_yoy_pct", "developer_growth_yoy_pct", "token_value_capture_score"),
         lambda v: 0.30*_mapped(v["revenue_growth_yoy_pct"], 100) + 0.25*_mapped(v["active_users_growth_yoy_pct"], 100) + 0.20*_mapped(v["developer_growth_yoy_pct"], 100) + 0.25*_clamp(v["token_value_capture_score"])),
        ("onchain_accumulation", ("exchange_netflow_supply_pct", "whale_balance_change_30d_pct", "active_address_growth_30d_pct"),
         lambda v: 0.40*_mapped(-v["exchange_netflow_supply_pct"], 2) + 0.35*_mapped(v["whale_balance_change_30d_pct"], 5) + 0.25*_mapped(v["active_address_growth_30d_pct"], 50)),
        ("catalyst", ("verified_catalyst_score", "catalyst_days", "catalyst_delivery_risk_score"),
         lambda v: 0.50*_clamp(v["verified_catalyst_score"]) + 0.25*_clamp(100-abs(v["catalyst_days"]-30)*1.5) + 0.25*_clamp(v["catalyst_delivery_risk_score"])),
        ("risk_adjusted", ("liquidity_score", "volatility_penalty_score", "drawdown_penalty_score", "unlock_risk_score", "contract_risk_score"),
         lambda v: 0.30*_clamp(v["liquidity_score"]) + 0.20*_clamp(100-v["volatility_penalty_score"]) + 0.20*_clamp(100-v["drawdown_penalty_score"]) + 0.15*_clamp(100-v["unlock_risk_score"]) + 0.15*_clamp(100-v["contract_risk_score"])),
        ("multi_timeframe_confluence", ("trend_15m_score", "trend_1h_score", "trend_4h_score", "trend_1d_score"),
         lambda v: 0.10*_clamp(v["trend_15m_score"]) + 0.20*_clamp(v["trend_1h_score"]) + 0.30*_clamp(v["trend_4h_score"]) + 0.40*_clamp(v["trend_1d_score"])),
    ]
    return tuple(_result(name, features, (keys, fn)) for name, keys, fn in specs)
