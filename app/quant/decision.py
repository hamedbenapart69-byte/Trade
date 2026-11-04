"""Deterministic decision gates. Thresholds are explicit policy, not learned probabilities."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from math import isfinite


class Decision(str, Enum):
    BUY_NOW = "BUY_NOW"
    CONDITIONAL_BUY = "CONDITIONAL_BUY"
    WAIT = "WAIT"
    REJECT = "REJECT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class DecisionInput:
    data_age_seconds: float | None
    required_data_complete: bool
    technical_score: float | None
    fundamental_score: float | None
    liquidity_score: float | None
    risk_score: float | None
    entry_trigger_confirmed: bool
    stop_loss_pct: float | None
    take_profit_pct: float | None
    hard_risk_veto: bool = False


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    reason_codes: tuple[str, ...]
    risk_reward: float | None
    composite_score: float | None


def decide(data: DecisionInput, *, max_data_age_seconds: float = 900.0,
           min_composite_score: float = 70.0, min_risk_reward: float = 2.0) -> DecisionResult:
    """Return a reproducible state; never infer missing inputs or manufacture a buy."""
    if data.hard_risk_veto:
        return DecisionResult(Decision.REJECT, ("HARD_RISK_VETO",), None, None)
    required = (data.data_age_seconds, data.technical_score, data.liquidity_score, data.risk_score,
                data.stop_loss_pct, data.take_profit_pct)
    if not data.required_data_complete or any(v is None for v in required):
        return DecisionResult(Decision.INSUFFICIENT_DATA, ("REQUIRED_EVIDENCE_MISSING",), None, None)
    numeric = [float(v) for v in required if v is not None]
    if any(not isfinite(v) for v in numeric):
        return DecisionResult(Decision.INSUFFICIENT_DATA, ("NON_FINITE_INPUT",), None, None)
    if data.data_age_seconds < 0 or data.data_age_seconds > max_data_age_seconds:
        return DecisionResult(Decision.INSUFFICIENT_DATA, ("MARKET_DATA_STALE",), None, None)
    if not 0 <= data.technical_score <= 100 or not 0 <= data.liquidity_score <= 100 or not 0 <= data.risk_score <= 100:
        return DecisionResult(Decision.INSUFFICIENT_DATA, ("SCORE_OUT_OF_RANGE",), None, None)
    if data.fundamental_score is not None and not 0 <= data.fundamental_score <= 100:
        return DecisionResult(Decision.INSUFFICIENT_DATA, ("FUNDAMENTAL_SCORE_OUT_OF_RANGE",), None, None)
    if data.stop_loss_pct <= 0 or data.take_profit_pct <= 0:
        return DecisionResult(Decision.REJECT, ("INVALID_STOP_OR_TARGET",), None, None)
    rr = data.take_profit_pct / data.stop_loss_pct
    weights = [(data.technical_score, 0.45), (data.liquidity_score, 0.20), (data.risk_score, 0.20)]
    if data.fundamental_score is not None:
        weights.append((data.fundamental_score, 0.15))
    total_weight = sum(weight for _, weight in weights)
    score = sum(value * weight for value, weight in weights) / total_weight
    if rr < min_risk_reward:
        return DecisionResult(Decision.REJECT, ("RISK_REWARD_BELOW_MINIMUM",), rr, score)
    if data.risk_score < 50 or data.liquidity_score < 40:
        return DecisionResult(Decision.REJECT, ("RISK_OR_LIQUIDITY_FLOOR_FAILED",), rr, score)
    if score < min_composite_score:
        return DecisionResult(Decision.WAIT, ("COMPOSITE_SCORE_BELOW_THRESHOLD",), rr, score)
    if not data.entry_trigger_confirmed:
        return DecisionResult(Decision.CONDITIONAL_BUY, ("ENTRY_TRIGGER_NOT_CONFIRMED",), rr, score)
    return DecisionResult(Decision.BUY_NOW, ("ALL_ENTRY_GATES_PASSED",), rr, score)
