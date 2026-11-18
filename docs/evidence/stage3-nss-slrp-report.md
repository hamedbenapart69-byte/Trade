# STAGE 3 — NSS RESILIENCE (V18.2)

**Stage result:** PASS via `NSS_V2_PROXY`.  
**Production language:** C++20.  
**Delivery:** Telegram only.  
**Active version:** v2 (PROXY; NOT_CALIBRATED).  
**v3:** NOT BUILT under R11.

## Objective and acceptance

Calculate the five NSS components with canonical weights, deterministic versioned transforms, explicit direction, bounded [0,1] scores, point-in-time timestamps and source-quality metadata. Missing components must not be zero-filled or have their weights redistributed.

Acceptance:
1. Five ordered components with weights 0.30 / 0.20 / 0.20 / 0.15 / 0.15.
2. All five components present for both LONG and SHORT.
3. Every score finite and within [0,1].
4. Funding is direction-aware and normalized to a common 8-hour equivalent.
5. Real spot/perpetual basis is timestamp-aligned and separately labelled REAL at the raw-input layer.
6. Proxy transformations are labelled PROXY and confidence remains NOT_CALIBRATED.
7. Future observations cannot affect earlier scores; stale inputs are rejected.
8. Deterministic C++20 build and full CTest pass.
9. Real BTC plus at least one altcoin are calculated.
10. NSS output is non-actionable.
11. Output schema validates.
12. Telegram HTTP 200 receipt is persisted on the `signals` branch.

## v1 — NSS_V1_FORMULA

**Result: FAIL — D1 + D2, measured.**

Run: `44300459901`  
L1 run ID: `okx-cpp-1795003539945`  
L1 SHA-256: `565e11ba78aecf1b8f4eb2dda2f228fac067c3798a9a12af5c9a5451daa92f7f`

- C++20 build: PASS.
- CTest: 5/5 PASS.
- Live OKX data: PASS for BTC/USDT:USDT and ETH/USDT:USDT.
- Raw OI and funding present.
- Real spot/perpetual basis series absent from the Stage 1 L1 contract.
- NSS v1: both instruments UNAVAILABLE, 0/5 scored components.

Diagnosis:
- **D1 Data:** no synchronized spot/perpetual basis series in the original L1 contract.
- **D2 Assumption:** the master source defines component names and weights but not every raw-to-score transform and direction convention. The strict REAL-only v1 aggregator did not invent these transforms.

## v1 L3 correction

Run `44300507416` failed before a Telegram network call because outbox persistence was configured to refuse replacement of the reserved state. This was D3 implementation. The reservation was reconciled as `ABORTED_PRE_SEND_D3`; no duplicate send was attempted.

Recovery run: `44300966736`
- Telegram HTTP 200, status DELIVERED, message_id 51.
- Receipt persisted to `signals`.

## v2 — NSS_V2_PROXY

**Result: PASS.**

Final validation run: `44302880627`  
Branch: `feat/cpp-stage3-nss-v2`  
L1 run ID: `okx-cpp-1795004458735`  
L1 SHA-256: `972dea03e2b2c323c73bb3791bf84cf47c1a65723db3cde2690a98dab831f578`  
Basis SHA-256: `f4f06022715139e73c5a2334f4eeaeb24379f4aed6cd57919a774a8bf303ced6`

### L1 — real data

- BTC/USDT:USDT spot candles: 2,160 rows; basis rows: 2,160; quality REAL.
- ETH/USDT:USDT spot candles: 2,160 rows; basis rows: 2,160; quality REAL.
- Both spot/perpetual series cover the requested 90-day hourly window.
- Funding event median interval: 28,800,000 ms (8 hours); skipped gaps: 0.
- Funding normalized to an 8-hour equivalent.
- OI, basis, volume, compression and funding timestamps are point-in-time; stale hourly inputs and funding older than 24 hours are rejected.

### L2 — score results

| Instrument | LONG NSS | SHORT NSS | Coverage | Quality |
|---|---:|---:|---:|---|
| BTC/USDT:USDT | 0.5514897411 | 0.4635417702 | 5/5 each direction | PROXY |
| ETH/USDT:USDT | 0.4864131285 | 0.5520003353 | 5/5 each direction | PROXY |

All component scores are finite and bounded [0,1]. Canonical weights are unchanged. The scorer uses directional z-score/sigmoid transforms against historical observations. A score of 0.5 means the transformed feature equals its reference mean, not that the market is neutral.

Component definitions:
- NSS1: 24h OI growth aligned with 24h price direction.
- NSS2: direction-aware funding cost/benefit, normalized to 8-hour equivalent; gaps are excluded.
- NSS3: 24h change in synchronized spot/perpetual basis.
- NSS4: 24h quote-volume expansion versus the preceding 20-day rolling reference, aligned with price direction.
- NSS5: inverse 20-period Bollinger Band width.

The transforms are research proxies, not calibrated probabilities. Both LONG and SHORT outputs carry `PROXY`, `NOT_CALIBRATED` and `actionable=false`. No trade recommendation is produced by Stage 3.

### Tests and delivery

- Clean C++20 configure/build: PASS.
- Full CTest: 7/7 PASS.
- Tests include deterministic aggregation, component bounds, missing basis, future perturbation, stale-input rejection, funding interval normalization, gap exclusion and basis timestamp alignment.
- JSON Schema: valid.
- Telegram: HTTP 200, `DELIVERED`, message_id `53`.
- Persistent receipt: `signals/cpp_runtime/nss_stage3_v2_telegram_outbox.v1.json`.
- Score artifact persisted: `signals/cpp_runtime/nss_stage3_v2.json`.
- Basis coverage summary persisted: `signals/cpp_runtime/nss_stage3_v2_basis_coverage.json`.
- Evidence commit on `signals`: `a6cf99c`.
- No Actions artifact storage used.

## V3 decision

V3 (`NSS_V3_ROLLING_PERCENTILE`) was not built because v2 passed. This follows R11. The 90-day 80th percentile remains a research reference for the rolling-percentile version, not a universal optimum. Fifty signals or 30 days is a review checkpoint, not an automatic version/threshold switch.

## Five-question self-critique

1. Future data used? No; point-in-time filtering and future-perturbation tests passed.
2. Parameters tuned on test? No test-set tuning; v2 transforms were predeclared.
3. Costs included? No trade or EV is produced by this stage; confidence remains NOT_CALIBRATED.
4. No-signal report? Yes; missing/stale inputs produce UNAVAILABLE and the diagnostic is sent to Telegram.
5. Weakest assumption? The z-score/sigmoid transforms are proxy hypotheses, not calibrated probabilities; their predictive value has not been tested OOS.

## SLRP result

```text
STAGE 3 — NSS RESILIENCE
├── Acceptance: 5/5 directional components, canonical weights, point-in-time integrity, funding interval normalization, deterministic tests, real BTC + altcoin, schema and Telegram receipt
├── v1 → FAIL → D1 (basis absent) + D2 (raw-to-score transforms unspecified)
├── v2 → PASS → live BTC/ETH 5/5 scores, REAL basis inputs, PROXY transforms, 7/7 tests, Telegram HTTP 200
├── v3 → NOT_BUILT → v2 passed (R11)
├── Active: v2 PROXY / NOT_CALIBRATED
└── Handoff: Stage 4 — Liquidity Zones + Market Phase
```
