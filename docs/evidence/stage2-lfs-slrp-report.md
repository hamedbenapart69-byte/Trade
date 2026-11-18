# STAGE 2 — LFS RESILIENCE (V18.2)

**Branch:** `feat/cpp-stage2-lfs-v1`  
**Base:** `feat/cpp-stage1-clean` at `190b0270ccb1425f4ed77503825aeaf26668baa4`  
**Implementation language:** C++20  
**Delivery:** Telegram only  
**Status:** v1 FAIL (D1 + D2); v2 L1/L2 PASS on real BTC+ETH data; v2 L3 Telegram receipt is still pending. v3 is NOT_BUILT. The v2 output remains research-only and cannot emit trades.

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
- Added `cpp/include/cfss/lfs.hpp`: strict five-component REAL-only weighted aggregator.
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
- v2: BUILT after the measured v1 FAIL under R11. Live L1/L2 validation PASS in GitHub Actions run `44245558287`, C++ run ID `okx-cpp-1794980311216`. A first compile attempt exposed D3 (a constexpr string type error); the v2 implementation was corrected and the subsequent build passed. Live Telegram L3 is pending.
- v3: NOT_BUILT; only after an actual v2 FAIL and specific D-code evidence.
- Maximum three versions. No parameter-only rewrites.

## v2 — LFS_V2_PROXY

Measured real run `44245558287` / `okx-cpp-1794980311216`:
- BTC/USDT:USDT: score `0.3594750349014508`, `CALCULATED`, `PROXY`, coverage 5/5, 720 contract-level long/short rows.
- ETH/USDT:USDT: score `0.43494248311325506`, `CALCULATED`, `PROXY`, coverage 5/5, 720 contract-level long/short rows.
- L1 SHA-256: `34a3ac0f2d59b038bf897b049af539809fb6fd5b31e9f757b893c684aa5eb4b3`.
- L2 SHA-256: `8a37633b1d959e2042706504c0517937d5d23d151457b5885d79dcf0fe6929ee`.
- LFS v2 SHA-256: `8dc176bb80394b7c498e9041aa13d01d729e2a9eb593427717e07e935e5d1170`.
- JSON Schema validation: PASS.
- CTest: 4/4 PASS; no Actions artifact upload: PASS.
- The report is a feature score only. It does not create BUY/SELL states, trade instructions, or calibrated confidence.

## v2 — LFS_V2_PROXY

v2 was created only after the measured v1 FAIL and D1/D2 diagnosis above.

Component transforms:
- LFS1 PROXY: 14-period ATR as a fraction of close, ranked against the preceding 90-day ATR history; plus rolling 24-hour contract volume ranked against the preceding 90-day history. Score = 0.5 × ATR percentile + 0.5 × (1 − volume percentile). This is explicitly an OHLCV proxy, not REAL order-book depth.
- LFS2 REAL: percentile rank of absolute funding rate against the available 30-day REAL funding history.
- LFS3 REAL: percentile rank of absolute log(long/short account ratio) from OKX's public contract-level long/short account ratio endpoint; 1H observations, up to 30 days.
- LFS4 REAL: inverse percentile rank of 20-period Bollinger Band width against the preceding 90-day REAL OHLCV history. Band width = 4 × population standard deviation / 20-period mean.
- LFS5 REAL: percentile rank of absolute 24-hour percentage change in USD open interest against available REAL OI history (approximately 30 days).

Percentile rank uses only prior observations; the current observation is ranked against that prior history. A minimum of 20 prior finite observations is required. The V2 aggregate retains the canonical weights and requires 5/5 valid components. If any component is missing, no aggregate is emitted. If any component is PROXY, the aggregate is PROXY.

V2 acceptance gates:
1. BTC and at least one eligible altcoin have 5/5 component scores.
2. Every component and aggregate is finite and within [0,1].
3. All component timestamps are no later than decision time.
4. LFS1 is explicitly PROXY; no claim of REAL order-book depth is made.
5. Identical inputs produce identical output.
6. Prefix/future-perturbation tests show no change to earlier scores.
7. C++ build, unit tests and JSON schema validation pass.
8. No actionable trade is emitted; V2 is a research score only.
9. Final stage report is delivered through Telegram with a real receipt.
10. Telegram report delivery is idempotent by report hash; an interrupted or uncertain send is blocked from automatic replay.

Calibration remains NOT_CALIBRATED. The 30-day funding, long/short and OI distributions are shorter than the 90-day research reference. V2 does not claim statistical optimality, probability or profitability. The LFS score alone is not a trade signal.

## L3 Telegram delivery

- Added `cpp/include/cfss/lfs_delivery.hpp` and `cpp/apps/lfs_telegram_report/main.cpp`.
- Report ID is SHA-256 of the canonical LFS v2 report.
- Outbox is persisted before sending; `DELIVERED` records Telegram message ID.
- Interrupted/uncertain attempts become `DELIVERY_UNKNOWN` and are not automatically resent.
- Delivery is gated by a dedicated `[LFS_STAGE2_REPORT]` commit marker; routine CI runs do not send messages.
- Receipt state is persisted on the `signals` branch. Live Telegram receipt is pending final v2 validation.

## SLRP diagnosis codes
D1 Data; D2 Assumption/formula; D3 Implementation; D4 Threshold/Calibration; D5 Regime; D6 Expectations.

## Five-question self-critique
1. Future data used? No; timestamps checked against decision time.
2. Parameters tuned on test? No tunable parameters introduced.
3. Costs included? No trade or EV is generated in Stage 2.
4. No-signal report? Missing/invalid inputs produce UNAVAILABLE, never a trade.
5. Weakest assumption? LFS1 remains an OHLCV proxy, and funding/long-short/OI percentile references cover about 30 days rather than the 90-day research reference.

## Handoff
No Stage 3 work until Stage 2 measured PASS and owner approval. v1 has failed with D1/D2; v2 is under live validation. If v2 fails, publish the exact D-code and evidence before considering v3.
