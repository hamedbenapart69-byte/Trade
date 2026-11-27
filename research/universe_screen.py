"""Evidence-only implementation of the V21.1 13-criterion candidate universe screen.

This script never freezes or mutates the production universe. Missing evidence is
reported as UNAVAILABLE/BLOCKED; it is never replaced by a proxy without a label.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_ASSETS = {"BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX"}
MIN_HOURLY_BARS_2Y = 24 * 365 * 2
MIN_FUNDING_EVENTS_30D = 90
MIN_OI_SNAPSHOTS_30D = 720
LIQUIDITY_THRESHOLD_USD = 10_000_000.0


def finite_or_none(value):
    if value is None:
        return None
    value = float(value)
    return value if np.isfinite(value) else None


def asset_symbol(instrument: dict) -> str:
    instrument_id = str(instrument.get("instrument_id", ""))
    if instrument_id.endswith("-USDT-SWAP"):
        return instrument_id[:-len("-USDT-SWAP")]
    raise ValueError(f"unsupported instrument identity: {instrument_id}")


def compute_asset_statistics(instrument: dict, as_of: datetime) -> dict:
    symbol = asset_symbol(instrument)
    coverage = instrument.get("coverage") or {}
    candles = instrument.get("candles") or []
    daily_returns = pd.Series(dtype=float)
    annualized_vol = None
    daily_count = 0
    if candles:
        frame = pd.DataFrame(candles)
        required = {"timestamp_ms", "close"}
        if required.issubset(frame.columns):
            frame["timestamp"] = pd.to_datetime(
                pd.to_numeric(frame["timestamp_ms"], errors="coerce"),
                unit="ms", utc=True, errors="coerce",
            )
            frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
            frame = frame.dropna(subset=["timestamp", "close"]).drop_duplicates("timestamp")
            frame = frame.sort_values("timestamp").set_index("timestamp")
            hourly_returns = np.log(frame["close"]).diff().dropna()
            if len(hourly_returns) > 100:
                annualized_vol = finite_or_none(float(hourly_returns.std(ddof=1)) * np.sqrt(24 * 365))
            daily_close = frame["close"].resample("1D").last().dropna()
            daily_returns = daily_close.pct_change().dropna()
            daily_count = int(len(daily_returns))

    listing_ms = instrument.get("listing_time_ms")
    listing_age_days = None
    if isinstance(listing_ms, (int, float)) and listing_ms > 0:
        listing_date = datetime.fromtimestamp(float(listing_ms) / 1000, timezone.utc)
        listing_age_days = max(0, int((as_of - listing_date).total_seconds() // 86400))

    funding = instrument.get("funding") or []
    open_interest = instrument.get("open_interest") or []
    turnover = finite_or_none(instrument.get("turnover_24h_usd"))
    return {
        "canonical_symbol": symbol,
        "instrument_id": instrument.get("instrument_id"),
        "venue_provider_id": instrument.get("provider_id"),
        "availability": instrument.get("availability"),
        "liquidity_status": instrument.get("liquidity_status"),
        "perpetual_turnover_24h_usd_proxy": turnover,
        "listing_age_days": listing_age_days,
        "ohlcv_rows": int(coverage.get("ohlcv_rows", len(candles))),
        "ohlcv_coverage_pct": finite_or_none(coverage.get("ohlcv_coverage_pct")),
        "funding_rows": int(len(funding)),
        "funding_coverage_days": finite_or_none(coverage.get("funding_coverage_days")),
        "funding_freshness_status": coverage.get("funding_freshness_status"),
        "open_interest_rows": int(len(open_interest)),
        "open_interest_coverage_days": finite_or_none(coverage.get("open_interest_coverage_days")),
        "open_interest_freshness_status": coverage.get("open_interest_freshness_status"),
        "daily_return_observations": daily_count,
        "annualized_volatility_1h": annualized_vol,
        "daily_returns": daily_returns,
    }


def main(input_path: str, output_path: str) -> None:
    source = Path(input_path)
    raw = source.read_bytes()
    l1 = json.loads(raw)
    as_of = datetime.now(timezone.utc)
    instruments = l1.get("instruments") or []
    stats = [compute_asset_statistics(item, as_of) for item in instruments]
    stats_by_symbol = {item["canonical_symbol"]: item for item in stats}
    actual_assets = set(stats_by_symbol)
    if actual_assets != EXPECTED_ASSETS or len(stats) != 9:
        raise SystemExit(f"candidate_universe_identity_mismatch:{sorted(actual_assets)}")

    market = l1.get("market_wide_provider_federation") or {}
    provider_count = int(market.get("production_eligible_fresh_provider_count", 0))
    matched_asset_count = int(market.get("matched_asset_count", 0))
    seed = {item.get("canonical_symbol"): item for item in market.get("candidate_seed", [])}

    correlation_frame = pd.DataFrame({
        symbol: item["daily_returns"] for symbol, item in stats_by_symbol.items()
    })
    correlation = correlation_frame.corr(min_periods=90)
    high_corr_pairs = []
    for i, left in enumerate(sorted(actual_assets)):
        for right in sorted(actual_assets)[i + 1:]:
            value = correlation.loc[left, right] if left in correlation.index and right in correlation.columns else np.nan
            if pd.notna(value) and float(value) > 0.70:
                high_corr_pairs.append({"left": left, "right": right, "correlation": round(float(value), 6)})

    all_derivatives = all(
        item.get("availability") == "AVAILABLE" and
        str(item.get("instrument_id", "")).endswith("-USDT-SWAP")
        for item in instruments
    )
    all_ohlcv = all(
        item["ohlcv_rows"] >= MIN_HOURLY_BARS_2Y and
        item["ohlcv_coverage_pct"] is not None and item["ohlcv_coverage_pct"] >= 99.0
        for item in stats
    )
    all_funding_oi = all(
        item["funding_rows"] >= MIN_FUNDING_EVENTS_30D and
        item["open_interest_rows"] >= MIN_OI_SNAPSHOTS_30D and
        item["funding_coverage_days"] is not None and item["funding_coverage_days"] >= 29.5 and
        item["open_interest_coverage_days"] is not None and item["open_interest_coverage_days"] >= 29.5 and
        item["funding_freshness_status"] == "FRESH" and
        item["open_interest_freshness_status"] == "FRESH"
        for item in stats
    )
    all_liquid_perpetuals = all(
        item["perpetual_turnover_24h_usd_proxy"] is not None and
        item["perpetual_turnover_24h_usd_proxy"] >= LIQUIDITY_THRESHOLD_USD and
        item["liquidity_status"] == "ELIGIBLE"
        for item in stats
    )
    identity_one_source = all(
        seed.get(symbol, {}).get("classification") in {
            "ONE_SOURCE_IDENTITY_MATCHED", "TWO_SOURCE_IDENTITY_MATCHED"
        }
        for symbol in EXPECTED_ASSETS
    )
    identity_two_sources = all(
        seed.get(symbol, {}).get("classification") == "TWO_SOURCE_IDENTITY_MATCHED"
        for symbol in EXPECTED_ASSETS
    )
    data_quality = all_derivatives and all_ohlcv and all_funding_oi and all(
        item["daily_return_observations"] >= 365 for item in stats
    )

    criteria = [
        {
            "id": 1, "name": "independent_market_wide_liquidity",
            "status": "UNAVAILABLE",
            "evidence": f"{provider_count} fresh license-eligible market-wide provider(s); {matched_asset_count}/9 two-provider asset matches.",
            "reason": "The L1 contract currently exposes provider identity/status, not a two-source per-asset market-wide liquidity history.",
        },
        {
            "id": 2, "name": "stable_spot_volume",
            "status": "UNAVAILABLE",
            "evidence": "No historical spot-volume series is present in this perpetual L1 artifact.",
            "reason": "Perpetual venue turnover is not relabelled as spot volume.",
        },
        {
            "id": 3, "name": "compatible_public_derivatives_instrument",
            "status": "PASS" if all_derivatives else "FAIL",
            "evidence": f"{sum(x.get('availability') == 'AVAILABLE' for x in instruments)}/9 active USDT swap instruments available.",
        },
        {
            "id": 4, "name": "historical_ohlcv_depth_and_continuity",
            "status": "PASS" if all_ohlcv else "FAIL",
            "evidence": f"Requires at least {MIN_HOURLY_BARS_2Y} hourly bars per asset and at least 99% coverage.",
        },
        {
            "id": 5, "name": "funding_and_open_interest_coverage",
            "status": "PASS" if all_funding_oi else "FAIL",
            "evidence": f"Requires at least {MIN_FUNDING_EVENTS_30D} funding events and {MIN_OI_SNAPSHOTS_30D} OI snapshots per asset, fresh within the L1 contract.",
        },
        {
            "id": 6, "name": "listing_age_and_delisting_history",
            "status": "PARTIAL",
            "evidence": "Current instrument listing timestamps are available; a complete historical delisting/suspension register is not included.",
        },
        {
            "id": 7, "name": "survivorship_bias",
            "status": "LIMITATION",
            "evidence": "The nine-asset candidate set is fixed from current research; point-in-time historical universe membership is unavailable.",
        },
        {
            "id": 8, "name": "volatility_and_regime_representation",
            "status": "MEASURED" if all(x["annualized_volatility_1h"] is not None for x in stats) else "UNAVAILABLE",
            "evidence": "Annualized hourly realized volatility and daily-return history are reported per asset; no unapproved volatility cut-off is introduced.",
        },
        {
            "id": 9, "name": "correlation_and_redundancy",
            "status": "MEASURED" if len(correlation_frame.columns) == 9 else "UNAVAILABLE",
            "evidence": f"{len(high_corr_pairs)} asset pairs have daily-return correlation above 0.70; portfolio G5 remains a separate exposure guard.",
        },
        {
            "id": 10, "name": "provider_diversity",
            "status": "PASS" if provider_count >= 2 and matched_asset_count == 9 else "BLOCKED",
            "evidence": f"{provider_count} fresh license-eligible provider(s); {matched_asset_count}/9 assets independently matched by two providers.",
        },
        {
            "id": 11, "name": "instrument_identity_reliability",
            "status": "PASS" if identity_two_sources else "PARTIAL" if identity_one_source else "FAIL",
            "evidence": "Every candidate has at least one identity match." if identity_one_source else "One or more candidate identities lack a provider match.",
        },
        {
            "id": 12, "name": "data_quality_and_operational_reachability",
            "status": "PASS" if data_quality else "FAIL",
            "evidence": "Real L1 instrument availability, OHLCV coverage, funding freshness, OI freshness and daily-return sample checks.",
        },
        {
            "id": 13, "name": "statistical_sample_sufficiency",
            "status": "PASS" if all_ohlcv and all(x["daily_return_observations"] >= 365 for x in stats) else "FAIL",
            "evidence": "At least two years of hourly OHLCV and at least 365 daily return observations per asset are required.",
        },
    ]
    blocking_statuses = {"UNAVAILABLE", "FAIL", "BLOCKED", "PARTIAL"}
    blockers = [
        f"CRITERION_{item['id']:02d}_{item['name'].upper()}_{item['status']}"
        for item in criteria if item["status"] in blocking_statuses
    ]
    blockers.append("OWNER_APPROVAL_NOT_RECORDED")
    output_assets = []
    for item in stats:
        output_assets.append({k: v for k, v in item.items() if k != "daily_returns"})
    output = {
        "schema_version": "1.0.0",
        "artifact_type": "cfss_v21_candidate_universe_screen_v1",
        "status": "PROVISIONAL_NOT_FROZEN",
        "selection_method": "BINARY_EVIDENCE_GATES_NO_WEIGHTS; numeric thresholds are used only where explicitly specified by V21.1 or its inherited guards.",
        "screened_at_utc": as_of.isoformat(),
        "source_l1_artifact": str(source),
        "source_l1_artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_assets": sorted(actual_assets),
        "candidate_count": len(actual_assets),
        "criteria_count": len(criteria),
        "criteria": criteria,
        "assets": output_assets,
        "correlation": {
            "method": "Pearson correlation of daily close-to-close returns derived from hourly candles",
            "minimum_pairwise_observations": 90,
            "pairs_above_0_70": high_corr_pairs,
            "pairs_above_0_70_count": len(high_corr_pairs),
            "matrix": {
                left: {
                    right: finite_or_none(correlation.loc[left, right])
                    for right in sorted(actual_assets)
                    if left in correlation.index and right in correlation.columns
                }
                for left in sorted(actual_assets)
            },
        },
        "provider_evidence": {
            "fresh_license_eligible_provider_count": provider_count,
            "two_source_matched_asset_count": matched_asset_count,
            "status": market.get("status"),
            "production_universe_status": market.get("production_universe_status"),
        },
        "liquidity_note": {
            "perpetual_turnover_threshold_usd": LIQUIDITY_THRESHOLD_USD,
            "all_candidates_pass_perpetual_turnover": all_liquid_perpetuals,
            "classification": "PROXY_NOT_SPOT_VOLUME",
        },
        "blockers": blockers,
        "owner_approval_required": True,
        "owner_approval_status": "NOT_RECORDED",
        "production_freeze_allowed": False,
        "non_mutation_guarantee": "This screen is evidence-only and never edits config/universe.json or any frozen production manifest.",
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "production_freeze_allowed": output["production_freeze_allowed"],
        "criteria_count": output["criteria_count"],
        "blockers": output["blockers"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    source_path = sys.argv[1] if len(sys.argv) > 1 else "artifacts/l1-market-data.v1.json"
    destination_path = sys.argv[2] if len(sys.argv) > 2 else "artifacts/universe-screen.v1.json"
    main(source_path, destination_path)
