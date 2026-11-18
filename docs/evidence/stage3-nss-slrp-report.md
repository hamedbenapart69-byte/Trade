# STAGE 3 — NSS RESILIENCE (V18.2)

**Canonical source:** V18.2  
**Implementation:** C++20  
**Delivery:** Telegram only  
**Stage status:** IN PROGRESS — v1 measured FAIL; v2 implemented on a dependent feature branch and undergoing live validation.

## Objective

Implement the five-component Narrative Momentum Score (NSS) with deterministic, versioned, point-in-time and source-quality-aware component scores. Do not fabricate missing values, substitute zero, or redistribute missing weights.

## Normative source contract

`NSS = 0.30*NSS1 + 0.20*NSS2 + 0.20*NSS3 + 0.15*NSS4 + 0.15*NSS5`

- NSS1: Open Interest Growth.
- NSS2: Healthy Funding.
- NSS3: Basis Expansion.
- NSS4: Volume Expansion.
- NSS5: Pre-Breakout Compression.

V18.2 requires explicit direction of desirability, normalized scores in [0,1], point-in-time timestamps and source-quality labels. It also requires funding to be interpreted relative to trade direction and historical conditions. A score of 0.5 is not automatically a neutral market state.

## Numeric acceptance criteria

1. Five ordered components and canonical weights 0.30 / 0.20 / 0.20 / 0.15 / 0.15.
2. Every score finite and within [0,1].
3. Every component has a versioned definition, direction and source-quality label.
4. Every timestamp is positive and no later than decision time.
5. Full score requires 5/5 valid components; no zero-fill or weight redistribution.
6. REAL and PROXY are never conflated.
7. Identical inputs are deterministic.
8. Future perturbations cannot change earlier outputs.
9. Clean C++20 configure/build and full CTest pass.
10. BTC plus at least one eligible altcoin are evaluated from fresh public data.
11. No actionable signal is emitted by the NSS resilience stage.
12. A real Telegram HTTP 200 receipt with message ID is persisted to `signals`.

## v1 — NSS_V1_FORMULA

### Implementation

- `cpp/include/cfss/nss.hpp`: strict REAL-only weighted aggregator.
- `cpp/tests/nss_v1_test.cpp`: canonical weights, missing component, PROXY rejection, future timestamp, score range and component identity.
- `cpp/apps/nss_v1_probe/main.cpp`: real L1 source-coverage and transform-definition diagnostic.
- `cpp/apps/nss_telegram_report/main.cpp`: C++ Telegram reporting, hash identity, outbox reservation and delivery receipt.
- `cpp-stage3-nss-v1.yml`: C++20 build, CTest and live OKX diagnostic.
- `cpp-stage3-telegram-report.yml`: one-time non-actionable Telegram report with persistent idempotency state.

### Measured evidence

GitHub Actions run: `44300459901`  
C++ run ID: `okx-cpp-1795003539945`  
L1 SHA-256: `565e11ba78aecf1b8f4eb2dda2f228fac067c3798a9a12af5c9a5451daa92f7f`

- Clean C++20 configure/build: PASS.
- CTest: 5/5 PASS.
- Fresh OKX L1 collection: PASS.
- Real instruments: BTC/USDT:USDT and ETH/USDT:USDT.
- Both instruments: raw OI present = true; raw funding present = true; real spot/perpetual basis series present = false.
- NSS v1 output: both symbols `UNAVAILABLE`; zero scored components.
- No score was fabricated.

### Diagnosis

**v1: FAIL for full-score availability.**

- **D1 — Data:** Stage 1 L1 does not contain the required spot/perpetual basis time series. The live probe confirmed this for both BTC and ETH.
- **D2 — Assumption / formula:** V18.2 names the five NSS components and weights but does not fully specify every raw-to-score mathematical transform, direction convention and 0.5 interpretation. The strict aggregator cannot invent these definitions.

The arithmetic contract tests passed; the full NSS score acceptance failed. This distinction is retained.

## v1 Telegram L3

First attempt run `44300507416` failed before the Telegram network request because the outbox writer used `refuse_existing=true` while updating an already reserved state. This is **D3 — Implementation**, not a Telegram API rejection. The old report ID `428e9cc2cf62cf292707835aefabc6997bc17f837f746aac9f4904c7bd609a45` was reconciled as `ABORTED_PRE_SEND_D3`; the logs confirm the send function was not invoked.

Correction:
- Outbox state updates now use replace-safe atomic persistence (`refuse_existing=false`).
- A fresh report ID was generated.
- Automatic replay of the old reservation was not attempted.

Recovery run: `44300966736`

- C++ build: PASS.
- Real OKX collection: PASS.
- Strict v1 diagnosis: PASS as a truthful UNAVAILABLE diagnostic.
- Telegram API: HTTP 200, `DELIVERED`, message_id `51`.
- Receipt persisted on the `signals` branch.
- No Actions artifact upload used.

## v2 — NSS_V2_PROXY

v2 was authorized only after the measured v1 FAIL and D1/D2 diagnosis, consistent with SLRP R11.

### Implemented on dependent branch

Branch: `feat/cpp-stage3-nss-v2`

- `cpp/include/cfss/nss_basis.hpp`: timestamp-aligned spot/perpetual close basis in basis points, REAL raw-source provenance and future-time filtering.
- `cpp/apps/nss_basis_collector/main.cpp`: fetches public OKX spot candles and derives synchronized basis from real spot and perpetual closes.
- `cpp/include/cfss/nss_v2.hpp`: directional long/short proxy transforms for all five components; canonical NSS weights retained.
- `cpp/apps/nss_v2_probe/main.cpp`: computes NSS_LONG and NSS_SHORT, records input hashes, coverage, PROXY and NOT_CALIBRATED.
- `cpp/tests/nss_basis_test.cpp`: basis alignment and future-data exclusion.
- `cpp/tests/nss_v2_test.cpp`: directional scores, bounds, determinism, missing-basis behavior and future-perturbation invariance.
- `contracts/nss-v2-proxy.v1.schema.json`: output schema.
- `cpp-stage3-nss-v2.yml`: fresh real perpetual/spot collection, C++ tests, schema validation and Telegram L3.

### v2 transform definitions

Each transform is explicitly PROXY. For a component raw feature (x), its directional score is:

`score = 1 / (1 + exp(-clamp((x - mean(prior))/sd(prior), -8, 8)))`

At least 20 prior finite observations and non-zero reference deviation are required. A score of 0.5 means the current transformed feature equals its prior reference mean; it does not mean neutral market conditions.

- NSS1: 24h OI percentage change aligned with 24h price return; separate LONG and SHORT polarity.
- NSS2: funding rate sign interpreted as direction-specific funding cost/benefit.
- NSS3: 24h change in synchronized spot/perpetual basis, with direction-specific polarity. Raw basis is computed from public spot and perpetual closes.
- NSS4: 24h quote-volume expansion relative to the preceding 20-day rolling reference, aligned with price direction.
- NSS5: inverse 20-period Bollinger Band width; lower width scores higher as a compression condition.

The formulas are research hypotheses, not empirically calibrated probabilities. All five component scores are required. Any missing or invalid component makes that direction UNAVAILABLE. The v2 output is never an actionable signal.

### v2 evidence status

- Implementation: committed.
- C++ live build, tests, spot basis coverage, BTC/ETH scores, schema and Telegram receipt: **PENDING**.
- No PASS is claimed before the live workflow completes.

## Version control / SLRP

- v1: **FAIL — D1 + D2**, measured with real BTC and ETH inputs.
- v2: **IMPLEMENTED — LIVE VALIDATION PENDING**.
- v3: **NOT_BUILT**. Permitted only after a measured v2 FAIL and a specific D-code diagnosis.
- Version budget: maximum three; no parameter-only rewrites.
- No actionable signal or trade is generated by this stage.

## Five-question self-critique

1. Future data used? No by design; point-in-time filtering and future-perturbation tests are included. Live test result pending.
2. Parameters tuned on test? No strategy thresholds were tuned on a test set; v2 reference transform is fixed and predeclared.
3. Costs included? No trade or EV is generated in Stage 3; cost modeling is not applicable to a feature-resilience report.
4. No-signal report? Yes. Missing basis or invalid components produce UNAVAILABLE; Telegram L3 records the diagnostic.
5. Weakest assumption? v2's z-score/sigmoid transforms are proxies and are not calibrated. Spot/perpetual basis coverage must be measured live.

## Current SLRP result

```text
STAGE 3 — NSS RESILIENCE
├── Acceptance: 5/5 valid directional components, canonical weights, point-in-time integrity, deterministic C++ tests, real BTC + altcoin, Telegram receipt
├── v1 → FAIL → D1 (basis absent from Stage 1 L1) + D2 (raw-to-score transforms not fully specified)
├── v2 → IMPLEMENTED / LIVE_TEST_PENDING → directional PROXY transforms + real spot/perpetual basis collector
├── v3 → NOT_BUILT → requires measured v2 FAIL + specific D-code
├── Active: NONE until v2 live acceptance
└── Handoff: BLOCKED pending v2 evidence and owner stage approval
```
