# STAGE 2 — LFS RESILIENCE (V18.2)

**Branch:** `feat/cpp-stage2-lfs-v1`  
**Base:** `feat/cpp-stage1-clean` at `190b0270ccb1425f4ed77503825aeaf26668baa4`  
**Implementation language:** C++20  
**Delivery:** Telegram only  
**Status:** v1 FAIL (D1 + D2) on the first real two-symbol run. The C++ build and unit tests passed, but the complete LFS score is unavailable because required inputs and raw-to-score definitions are missing. v2 is now eligible under R11; implementation has not yet been claimed.

## Objective
Implement and validate the canonical five-component LFS contract without inventing missing component values, changing weights, or confusing REAL and PROXY data.

## Source contract
`LFS = 0.25*LFS1 + 0.20*LFS2 + 0.20*LFS3 + 0.20*LFS4 + 0.15*LFS5`

- LFS1: Book Thinness.
- LFS2: Funding Extreme.
- LFS3: Long / Short Positioning.
- LFS4: Volatility Compression.
- LFS5: Open Interest Change.

All scores must be deterministic, versioned, point-in-time available and normalized to [0,1]. Missing components cannot be replaced with zero and missing weights cannot be redistributed. REAL order-book depth cannot be replaced with OHLCV-derived values without a PROXY label.

## Numeric acceptance criteria for v1 contract
1. Exactly five ordered components and canonical weights.
2. Each score finite and within [0,1].
3. Each component has a non-empty definition/version identifier.
4. Each availability timestamp is positive and no later than decision time.
5. A full LFS score is emitted only with 5/5 valid components.
6. Missing IDs are reported; no zero fill or weight renormalization.
7. Identical inputs produce identical scores.
8. Provenance preserved: v1 accepts REAL components only; PROXY components are rejected and reserved for v2.
9. C++ unit/contract tests pass under warning-enabled build.
10. Stage handoff requires a versioned report and Telegram receipt; no actionable trade is emitted.

## v1 implementation
- Added `cpp/include/cfss/lfs.hpp`: strict five-component weighted aggregator.
- Added `cpp/tests/lfs_v1_test.cpp`: complete-score, missing-input, range, future-timestamp, definition-version and provenance tests.
- Registered standalone test target in `cpp/CMakeLists.txt`.
- No Python production/release authority.

## v1 evidence / diagnosis
Measured GitHub Actions run: `44244101096`; run ID: `okx-cpp-1794979539131`.

- C++ configure/build: PASS.
- Existing C++ unit tests: PASS.
- New LFS v1 contract tests: PASS (2/2 total CTest targets, 100%).
- Real OKX L1 collection: PASS for BTC/USDT:USDT and ETH/USDT:USDT.
- BTC and ETH each returned 17,532 completed 1h candles, 90 funding rows and 720 OI rows.
- L1 SHA-256: `1c184b36a86a478131f363667629c6c7b43411861243d1af1be6149fa3634a79`.
- L2 SHA-256: `c3834f7718dc8aa0ce76f6c714a3b7db3d610b41281938720704e0540ff9cdeb`.
- For both symbols, orderbook and long/short arrays are absent from the current L1 contract.
- The probe in this first run predates the C++ LFS probe executable; the updated workflow will run it in the next attempt.

**v1 result: FAIL for full-score availability, not for the aggregator's arithmetic contract.** The 5/5 score gate cannot be met. D1: LFS1 order-book and LFS3 long/short inputs are absent. D2: canonical raw-to-score transforms are not fully specified for all five components. No missing component is set to zero and no weights are redistributed.

Directly inspected Stage 1 C++ L1 contract:
- OHLCV, funding and open-interest series exist.
- No order-book depth series is present.
- No long/short positioning series is present.
- Therefore LFS1 and LFS3 cannot be treated as REAL from the current Stage 1 L1 dataset.
- The canonical source does not fully define all raw-to-score mathematical transforms. A normalized-score aggregator alone does not establish those feature formulas.

Expected failure condition: if live L1 lacks LFS1/LFS3 and complete component definitions, v1 must return UNAVAILABLE. This is a measured data/assumption limitation, not permission to fill missing values.

## Version control
- v1: strict REAL-only v1 aggregator contract.
- v2: ELIGIBLE under R11 after the measured v1 FAIL above; conservative PROXY design/implementation is next.
- v3: NOT_BUILT; only after actual v2 FAIL and specific D-code evidence.
- Maximum three versions. No parameter-only rewrites.

## SLRP diagnosis codes
D1 Data; D2 Assumption/formula; D3 Implementation; D4 Threshold/Calibration; D5 Regime; D6 Expectations.

## Five-question self-critique
1. Future data used? No; timestamps checked against decision time.
2. Parameters tuned on test? No tunable parameters introduced.
3. Costs included? No trade or EV is generated in Stage 2.
4. No-signal report? Missing/invalid inputs produce UNAVAILABLE, never a trade.
5. Weakest assumption? Five LFS components and weights are named, but raw-to-score transforms are not fully specified and Stage 1 L1 lacks order-book/long-short inputs.

## Handoff
No Stage 3 work until Stage 2 measured PASS and owner approval. If v1 fails, publish exact D-code and measured evidence before considering v2.
