"""Small dependency-free portfolio analytics for aligned daily return series."""
from __future__ import annotations
from math import isfinite, sqrt
from statistics import mean
from typing import Mapping, Sequence
from app.quant.indicators import MarketDataValidationError, correlation


def _clean_returns(series: Sequence[float], name: str) -> list[float]:
    values = [float(x) for x in series]
    if len(values) < 3 or any(not isfinite(x) for x in values):
        raise MarketDataValidationError(f"{name}_requires_at_least_3_finite_returns")
    return values


def covariance_matrix(returns: Mapping[str, Sequence[float]]) -> tuple[list[str], list[list[float]]]:
    names = list(returns)
    if len(names) < 2:
        raise MarketDataValidationError("at_least_two_assets_required")
    data = {name: _clean_returns(returns[name], name) for name in names}
    lengths = {len(v) for v in data.values()}
    if len(lengths) != 1:
        raise MarketDataValidationError("return_series_must_be_aligned_to_same_dates")
    means = {name: mean(data[name]) for name in names}
    n = len(next(iter(data.values())))
    matrix: list[list[float]] = []
    for a in names:
        row = []
        for b in names:
            cov = sum((x-means[a])*(y-means[b]) for x, y in zip(data[a], data[b])) / (n-1)
            row.append(cov)
        matrix.append(row)
    return names, matrix


def correlation_matrix(returns: Mapping[str, Sequence[float]]) -> tuple[list[str], list[list[float]]]:
    names = list(returns)
    if len(names) < 2:
        raise MarketDataValidationError("at_least_two_assets_required")
    data = {name: _clean_returns(returns[name], name) for name in names}
    lengths = {len(v) for v in data.values()}
    if len(lengths) != 1:
        raise MarketDataValidationError("return_series_must_be_aligned_to_same_dates")
    return names, [[1.0 if a == b else correlation(data[a], data[b]) for b in names] for a in names]


def _project_capped_simplex(values: list[float], cap: float) -> list[float]:
    """Euclidean projection onto sum(w)=1 and 0<=w<=cap."""
    n = len(values)
    if cap * n < 1.0 - 1e-12:
        raise MarketDataValidationError("max_weight_cap_infeasible_for_asset_count")
    lo, hi = min(values) - cap, max(values)
    for _ in range(100):
        mid = (lo + hi) / 2
        total = sum(max(0.0, min(cap, x-mid)) for x in values)
        if total > 1.0:
            lo = mid
        else:
            hi = mid
    projected = [max(0.0, min(cap, x-(lo+hi)/2)) for x in values]
    total = sum(projected)
    if total <= 0:
        raise MarketDataValidationError("portfolio_projection_failed")
    return [x/total for x in projected]


def minimum_variance_weights(returns: Mapping[str, Sequence[float]], *, max_weight: float = 0.50,
                             iterations: int = 4000) -> dict[str, float]:
    """Long-only constrained minimum-variance weights via projected gradient descent.

    Uses historical sample covariance only. It is not a return forecast and does not
    account for fees, taxes, liquidity constraints, or future regime changes.
    """
    if not 0 < max_weight <= 1 or iterations < 1:
        raise MarketDataValidationError("invalid_optimizer_parameters")
    names, cov = covariance_matrix(returns)
    n = len(names)
    if max_weight * n < 1.0 - 1e-12:
        raise MarketDataValidationError("max_weight_cap_infeasible_for_asset_count")
    lipschitz = max(sum(abs(x) for x in row) for row in cov) * 2.0
    if not isfinite(lipschitz) or lipschitz <= 0:
        raise MarketDataValidationError("covariance_matrix_has_no_positive_scale")
    step = 1.0 / lipschitz
    weights = [1.0 / n] * n
    for _ in range(iterations):
        gradient = [2.0 * sum(cov[i][j] * weights[j] for j in range(n)) for i in range(n)]
        candidate = _project_capped_simplex([weights[i] - step*gradient[i] for i in range(n)], max_weight)
        if max(abs(candidate[i]-weights[i]) for i in range(n)) < 1e-12:
            weights = candidate
            break
        weights = candidate
    return {name: round(weight, 10) for name, weight in zip(names, weights)}


def portfolio_volatility(returns: Mapping[str, Sequence[float]], weights: Mapping[str, float], *, periods_per_year: int = 365) -> float:
    names, cov = covariance_matrix(returns)
    if set(names) != set(weights):
        raise MarketDataValidationError("weights_must_match_return_assets")
    if periods_per_year < 1 or any(not isfinite(float(weights[n])) or float(weights[n]) < 0 for n in names):
        raise MarketDataValidationError("invalid_weights_or_annualization")
    total = sum(float(weights[n]) for n in names)
    if abs(total - 1.0) > 1e-6:
        raise MarketDataValidationError("portfolio_weights_must_sum_to_one")
    variance = sum(float(weights[names[i]]) * cov[i][j] * float(weights[names[j]]) for i in range(len(names)) for j in range(len(names)))
    return sqrt(max(0.0, variance) * periods_per_year)
