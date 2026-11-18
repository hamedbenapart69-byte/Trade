# STAGE 2 — LFS RESILIENCE (V18.2)

**Branch:** `feat/cpp-stage2-lfs-v1`  
**Base:** `main` at `16cb5e874e89649e049abb6debc6300572e24f09` (Stage 1 merged and verified on main)  
**Implementation language:** C++20  
**Delivery:** Telegram only  
**Status:** STAGE 2 PASS for LFS resilience and the required L1/L2/L3 vertical slice. v1 FAIL (D1 + D2); v2 PASS on fresh real BTC+ETH inputs with 5/5 component coverage; v2 L3 has a real Telegram HTTP 200 receipt (message_id=50) persisted to `signals`. v3 is NOT_BUILT under R11 because v2 passed. The v2 output remains PROXY / NOT_CALIBRATED research-only and cannot emit trades.

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
- The first v1 run predates the C++ LFS probe executable; the subsequent v2 run executed both the v1 probe and v2 scorer against fresh real inputs.

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
- v2: BUILT after the measured v1 FAIL under R11. Live L1/L2 validation PASS in GitHub Actions runs `44245558287`, `44245999599`, `44246628061`, `44292375181`, and final end-to-end run `44292775092`. A first compile attempt exposed D3 (a constexpr string type error); corrected before subsequent successful builds. Deterministic aggregate and future-perturbation assertions pass. Final live Telegram L3 receipt is recorded below.
- v3: NOT_BUILT; only after an actual v2 FAIL and specific D-code evidence.
- Maximum three versions. No parameter-only rewrites.

## v2 — LFS_V2_PROXY

Earlier measured run `44246628061` / `okx-cpp-1794981358236`:
- BTC/USDT:USDT: score `0.3519646037470697`, `CALCULATED`, `PROXY`, coverage 5/5, 720 contract-level long/short rows.
- ETH/USDT:USDT: score `0.4324390060617947`, `CALCULATED`, `PROXY`, coverage 5/5, 720 contract-level long/short rows.
- L1 SHA-256: `e077f04cd4462ebace6845c44d3c12b03192b5b2739c4708acc093abc264b6eb`.
- L2 SHA-256: `403603ea0bb0df25e6d2a964770558449261a9d9b228eb912c80358e0ce9a2e6`.
- LFS v2 SHA-256: `28006fc62b5fb5682b9daf9293ba5ad35df2f15d1d778320bba08301e98c1690`.

Final end-to-end measured run `44292775092` / `okx-cpp-1795000537259`:
- BTC/USDT:USDT: score `0.41505333368644903`, `CALCULATED`, `PROXY`, coverage 5/5.
- ETH/USDT:USDT: score `0.4391550681652331`, `CALCULATED`, `PROXY`, coverage 5/5.
- Final canonical report hash / outbox report ID: `061fddcc33bbbcfa1ca3f43ead32f4f60b52233364aedcda7aab443b0c808413`.
- The report was generated from a fresh real OKX L1 collection and delivered through the same run's C++ Telegram L3.
- These are feature scores only. Neither value is a trade signal, calibrated probability or evidence of profitability.
- Earlier independent runs `44245558287` and `44245999599` also returned 5/5 for BTC and ETH.
- JSON Schema validation: PASS.
- CTest: 4/4 PASS in both live runs; future-perturbation guards for candles, funding, long/short and OI passed. Deterministic aggregate assertion: PASS in run `44246628061`; future-perturbation guards for candles, funding, long/short and OI also passed.
- No Actions artifact upload: PASS.
- The report is a feature score only. It does not create BUY/SELL states, trade instructions, or calibrated confidence.

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
- Outbox reservation is committed to `signals` before the Telegram network send; `DELIVERED` then records the Telegram message ID.
- Interrupted/uncertain attempts become `DELIVERY_UNKNOWN` and are not automatically resent.
- Delivery is gated by a dedicated `[LFS_STAGE2_REPORT]` commit marker; routine CI runs do not send messages.
- Receipt state is persisted on the `signals` branch.
- First attempt (GitHub Actions run `44290154942`) reached the C++ send step but returned an unconfirmed response; the outbox correctly persisted `DELIVERY_UNKNOWN` and blocked automatic replay. The first attempt did not retain the Telegram HTTP response body, so its exact API rejection is unavailable.
- Read-only diagnostics verified `getMe`, `getChat`, and `getChatMember`: HTTP 200; bot is an administrator and `can_post_messages=true`.
- The first report was not present in the latest 20-message public channel preview; latest visible post was `2026-11-18T05:35:04Z`, earlier than the first send reservation at `2026-11-18T11:03:04Z`. The reconciliation evidence was persisted and the original receipt changed to `RECONCILED_NOT_DELIVERED`; no duplicate send was attempted for that report ID.
- Code-level diagnosis (inference): the original sender used Telegram Markdown while the report contained underscore-delimited status strings such as `NOT_CALIBRATED`. The sender was corrected to send this report as plain text and to log the HTTP response safely.
- Recovery/final run `44292775092`: fresh report reserved before network delivery; Telegram returned HTTP `200`, `ok=true`, and `message_id=50`; C++ persisted `DELIVERED` at `2026-11-18T11:16:48Z`.
- Final report ID: `061fddcc33bbbcfa1ca3f43ead32f4f60b52233364aedcda7aab443b0c808413`.
## SLRP diagnosis codes
D1 Data; D2 Assumption/formula; D3 Implementation; D4 Threshold/Calibration; D5 Regime; D6 Expectations.

## Five-question self-critique
1. Future data used? No; point-in-time filtering and future-perturbation tests cover candles, funding, long/short and OI.
2. Parameters tuned on test? No tunable parameters introduced.
3. Costs included? No trade or EV is generated in Stage 2.
4. No-signal report? Missing/invalid inputs produce UNAVAILABLE, never a trade.
5. Weakest assumption? LFS1 remains an OHLCV proxy, and funding/long-short/OI percentile references cover about 30 days rather than the 90-day research reference.

## Final SLRP result

```text
STAGE 2 — LFS RESILIENCE
├── Acceptance: 5/5 valid bounded components, canonical weights, point-in-time timestamps, deterministic aggregate, real L1 + C++ L2 + Telegram L3 receipt
├── v1 → FAIL → D1/D2 + measured missing order-book and long/short source fields; no zero-fill or weight redistribution
├── v2 → PASS → BTC and ETH each CALCULATED / PROXY / 5-of-5; schema valid; CTest 4/4 PASS; real Telegram HTTP 200, message_id=50 persisted
├── v3 → NOT_BUILT → prohibited by R11 because v2 passed
├── Active: v2 (PROXY / NOT_CALIBRATED; research-only)
└── Handoff: Stage 2 PASS; next stage requires explicit owner approval
```

Budget: 2 of 3 versions used; 1 remains unused. No parameter-only rewrite was made.

## Delivery policy note
The GitHub PR received an automatic Cloudflare Pages preview deployment comment from the repository's existing Cloudflare integration. This was not used by the Stage 2 pipeline or as a user delivery channel; Telegram remained the only report delivery. The current session has no Cloudflare account control to disable that pre-existing preview integration. It remains a C16 governance cleanup item before treating the repository's deployment surface as fully aligned with the Telegram-only rule.

## Handoff
Stage 2 measured acceptance is PASS. Do not start Stage 3 until the owner explicitly approves the handoff. The Cloudflare Pages preview integration noted above remains a separate C16 cleanup item; no dashboard or email was used for routine delivery.
