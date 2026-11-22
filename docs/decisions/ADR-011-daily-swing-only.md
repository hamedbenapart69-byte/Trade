# ADR-011 — Daily/Swing-Only Operating Profile

- Decision ID: ADR-011
- Status: OWNER-APPROVED
- Effective date: 2026-11-22
- Supersedes: V19.0 Scalp activation sequence and its 15m/5m/1m implementation roadmap
- Scope: Stage 2 and all subsequent production signal generation

## Owner decision

The system is Daily/Swing only. Scalp is removed from the active roadmap.

Allowed production analysis timeframes:
- 1D
- 4H

Prohibited production analysis timeframes:
- 15m
- 5m
- 1m

No hidden lower-timeframe confirmation, entry trigger, feature, fallback, or execution instruction may reintroduce a prohibited timeframe. Historical legacy code may remain archived, but it must not be called by the active Daily/Swing pipeline.

## Operating target

- Target output: 0–2 qualified signals per day.
- This is a target, not a minimum, quota, or acceptance requirement.
- A valid scan may produce zero signals.
- No threshold may be relaxed to increase signal count.

## Strategy horizon and research targets

- Intended holding horizon: 1–7 days.
- Target win rate: 55–62%.
- Target reward/risk: 1:2 to 1:4.
- These are research objectives, not verified performance and not PASS criteria until supported by cost-adjusted out-of-sample evidence.

## Data policy

- Binance Vision is the owner-directed initial historical OHLCV source for the 27-symbol target universe on 1D and 4H.
- Contract identity must be independently revalidated against live USD-M exchange metadata; the old 27-symbol snapshot is not current proof.
- Maximum accepted archive staleness: 32 hours, owner-directed.
- Every candle must be completed, timestamp-aligned, gap-checked, checksum-verified, and tied to the exact perpetual contract.
- 32 hours is an outer rejection boundary, not a statement that a 4H observation 32 hours old is suitable for every feature. Each feature must record actual age; strategy eligibility may impose stricter freshness.
- Spot data, synthetic data, and unverified provider substitutions are prohibited.
- Missing or stale data yields PARTIAL, STALE, UNAVAILABLE, or MARKET_DATA_DEGRADED; it must never be silently replaced.

## Stage 2 execution order

2A. Provider gate:
- Verify all 27 target instruments as active USDT-margined perpetual contracts.
- Probe 1D and 4H Binance Vision archives for each symbol.
- Verify checksums, completed candles, interval alignment, OHLC integrity, coverage, and staleness.
- Emit an auditable L1 artifact.
- Independently validate the artifact in C++ L2.
- Deliver a non-trading status report through Telegram L3.
- No strategy signal may be generated in 2A.

2B. LRT Daily/Swing:
- Begin only after 2A passes.
- Implement independent LRT-1D and LRT-4H engines.
- Use completed candles only and preserve separate timeframe outcomes.
- Build v1 first. v2/v3 are allowed only after a real v1 failure and a specific D1–D6 diagnosis.
- Do not claim calibration or profitability before sufficient out-of-sample evidence.

## Three-month research plan

- Month 1: LRT-1D development and shadow evaluation, with LRT-4H as a separately validated companion engine.
- Month 2: Calibration, Brier Score, reliability curves, and confidence intervals when sample sufficiency permits. Otherwise remain UNCALIBRATED.
- Month 3: VERIFIED decision only if all applicable gates pass on independently reproducible out-of-sample evidence. Calendar time alone cannot confer VERIFIED status.

## Governance

- C++ remains authoritative for L2 decisions and L3 Telegram delivery.
- Python remains restricted to L1 acquisition and serialization.
- No exchange account connection, private trading API key, or order execution.
- L1, L2, and L3 are mandatory for stage acceptance.
- Stage 2 stops at its acceptance gate; later stages require explicit owner approval.
