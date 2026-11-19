# STAGE 5 — INDEPENDENT LRT / NMT ENGINES (V18.2)

## Objective

Implement two independent Plan A engines in C++20:
- LRT: Liquidity Reversion Trade, 30m–4h.
- NMT: Narrative Momentum Trade, 1–7d.

Each engine owns its hypothesis, inputs, gate, candidate state, falsification rule and output artifact. They must not share a blended score. The only cross-engine interaction is the mandatory Golden Rule veto.

## Shared input contract

- One L1 snapshot per run.
- LFS v2 and NSS v2 computed from the exact same L1 bytes, run ID, scan ID and decision timestamp.
- Stage 4 liquidity/phase output must reference the same L1 hash and decision timestamp.
- All LFS/NSS components must be 5/5 for both directions before either engine can produce a candidate.
- LFS/NSS remain PROXY and NOT_CALIBRATED. Candidate output is never BUY_NOW/SELL_NOW and never actionable.

## LRT v1 hypothesis and gate

**Hypothesis:** A confirmed active demand/supply zone is swept and reclaimed/rejected by a closed 4H candle with relative quote volume >= 1.20; the event is a candidate for a short-horizon liquidity reversion.

- LONG: last closed 4H low < active demand-zone low AND close > demand-zone high.
- SHORT: last closed 4H high > active supply-zone high AND close < supply-zone low.
- The zone must have been confirmed before the trigger candle closed.
- LFS v2 score is the independent LRT feature score; it is not blended with NSS.
- Entry/invalidation/target fields are reference prices only, not orders, stop-losses or take-profits.
- Falsification: a later closed 4H candle closes beyond the sweep extreme or the originating zone is invalidated.

## NMT v1 hypothesis and gate

**Hypothesis:** A directional market-structure phase, 20-bar 4H breakout, relative quote-volume expansion >= 1.20 and directional NSS score jointly support a 1–7 day continuation candidate.

- LONG: phase UPTREND AND last closed 4H close > preceding 20-bar high.
- SHORT: phase DOWNTREND AND last closed 4H close < preceding 20-bar low.
- Relative quote volume must be >= 1.20 against the preceding 20 closed 4H bars.
- NSS_LONG or NSS_SHORT is used only by NMT; it is not blended with LFS.
- Narrative evidence is explicitly market-derived (OI, funding, basis, volume, compression) and remains PROXY; no external-news claim is made.
- Falsification: a later 4H close returns through the breakout level or the phase is no longer directionally aligned.

## Golden Rule — mandatory veto

At the same decision timestamp:

`LFS > 0.70 AND max(NSS_LONG, NSS_SHORT) > 0.70 => NO_TRADE`

- Strict greater-than; exactly 0.70 does not trigger.
- If LFS or either NSS direction is missing/invalid, the veto cannot be safely evaluated; both engines return INSUFFICIENT_DATA.
- Veto overrides both engines and clears candidate reference prices.
- No override, averaging, weighting or exception is permitted.

## Numeric acceptance criteria

1. Exact L1 hash, run ID, scan ID and decision timestamp match across LFS, NSS and Stage 4 artifacts.
2. Both engines receive 5/5 LFS/NSS component coverage; otherwise neither may emit a candidate.
3. LRT and NMT artifacts remain separate and have independent status, direction, score, hypothesis and falsification.
4. LRT candidate requires the registered sweep/reclaim/rejection condition and relative volume >= 1.20.
5. NMT candidate requires directional phase, 20-bar breakout and relative volume >= 1.20.
6. Golden Rule test passes for scores strictly above 0.70 and does not trigger at exactly 0.70.
7. Golden Rule veto blocks both engines.
8. Missing Golden Rule inputs block both engines.
9. Changing NSS below the veto threshold does not change LRT logic; changing LFS below the veto threshold does not change NMT logic.
10. Every candidate has a numeric hypothesis, a falsification condition and NOT_CALIBRATED status.
11. Every output is non-actionable; no order, account connection or execution code exists.
12. C++20 build, full CTest, three JSON schemas and Telegram HTTP 200 receipt pass.
13. Real BTC plus at least one altcoin are evaluated from the same snapshot.

## SLRP versions

- v1: independent sweep/reclaim LRT and phase-breakout NMT, with the hard Golden Rule veto.
- v2 (NOT BUILT): if v1 has a measured FAIL, investigate a distinct retest/volume-profile LRT assumption and a distinct multi-timeframe continuation NMT assumption. Not a parameter-only rewrite.
- v3 (NOT BUILT): if v2 has a measured FAIL, simplify to confirmed structural events and directional score availability, removing secondary confluence layers.
- R11: v2/v3 are built only after a real FAIL of the preceding version.
- Maximum three versions.

## Diagnosis codes

- D1 Data: missing inputs, incomplete component coverage, or cross-artifact timestamp/hash mismatch.
- D2 Assumption: the sweep/reclaim or breakout/continuation hypothesis is falsified.
- D3 Implementation: code, integration, schema, causal or Golden Rule defect.
- D4 Threshold/Calibration: candidate gates or score references fail their predeclared validation; no test-set tuning.
- D5 Regime: the engine's premise is not valid in the observed market regime.
- D6 Expectations: no candidate is a valid output; absence of a setup is not an implementation failure.

## Escalation and budget

Measured v1 FAIL -> specific D-code and evidence -> v2. Measured v2 FAIL -> specific D-code and evidence -> v3. Measured v3 FAIL -> Innovation Protocol. No acceptance threshold is relaxed. Maximum three versions.

## Five-question self-critique

1. Future data used? Must be no; all artifacts share one decision timestamp.
2. Parameters tuned on test? Must be no; the 1.20 volume gate is predeclared.
3. Costs included? No trade/EV is emitted at this stage; cost-aware execution gates belong to later stages.
4. No-signal report? Must be explicit through NO_QUALIFIED_SETUP or INSUFFICIENT_DATA.
5. Weakest assumption? LRT sweep/reclaim and NMT breakout/phase gates are hypotheses, not calibrated probabilities.
