# V21 Stage 1 — SLRP Plan

**Status:** v1 FAIL (D3) / v2 IMPLEMENTED ON ISOLATED BRANCH / LIVE ACCEPTANCE PENDING  
**Controlling source:** MASTER SOURCE V21.0 + V21 Execution Protocol Addendum  
**Architecture:** CFSS V21 Architecture Design V1  
**Stage owner approval:** 2026-11-23  
**Active candidate:** v2 (not yet CI-accepted or live-accepted)

## 1. Objective

Establish a reproducible, zero-cost, C++ production vertical slice for V21 using public market data, fail-closed L2 status computation, versioned V21 run provenance, and Telegram delivery. Stage 1 is infrastructure and safe reporting only. It must not execute, rename, or recycle LRT, NMT, or VTM. No strategy engine is admitted in this stage.

## 2. Acceptance Criteria

All criteria are mandatory. Stage 1 requires **two consecutive, independent complete runs** with distinct run IDs and the same accepted code revision.

1. **Build:** C++20 configure and full production build on ubuntu-24.04 complete with exit code 0.
2. **Tests:** all registered CTest tests execute; 100% pass; zero unexpected skips or test failures.
3. **L1:** live public OKX data is fetched for BTCUSDT and at least one liquid non-BTC USDT perpetual. Each selected instrument has 1h OHLCV, funding, and open-interest series with strictly increasing timestamps, completed candles, currency/unit validation, and explicit freshness/coverage.
4. **Provider truth:** primary provider and every fallback status are recorded. An unimplemented or unreachable fallback is NOT_IMPLEMENTED or UNAVAILABLE, never represented as a successful fallback.
5. **L2:** C++ emits one valid C10 state for every selected instrument. actionable=false for every instrument in Stage 1. confidence_status=NOT_CALIBRATED remains explicit. Missing/stale/partial required inputs resolve to MARKET_DATA_DEGRADED, not a fabricated signal.
6. **V21 manifest:** run-manifest.v2.json validates against run-manifest.v2.schema.json; document_version=V21.0; rejected_strategy_families is exactly [LRT,NMT,VTM]; active_strategy_engines is empty.
7. **L3 outbound:** Telegram API returns HTTP 200, ok=true, and a persisted positive message_id; manifest records DELIVERED and L1_L2_L3_PASS; when the controlled inbound test also passes, the final status may be STAGE1_CONTROLLED_ACCEPTANCE_PASS.
8. **L3 inbound:** at least one of the two runs must receive and process a controlled /status update from the authorized chat; the exact same processed update_id is replayed through the production duplicate-update handler; no second send is attempted; the manifest records RECEIVED_PROCESSED, telegram_replay_test_status=PASS, and controlled acceptance.
9. **Persistence:** run manifest, L1/L2 provenance, Telegram outbox and receipts are persisted on the dedicated signals branch. No GitHub Actions artifact upload/storage is used.
10. **Repeatability:** both consecutive runs independently satisfy criteria 1–7 and 9; at least one of the two also satisfies criterion 8; no manual editing of generated artifacts between runs.
11. **Safety:** no private exchange credentials, account endpoints, order placement, paid services, or non-C++ production runtime are used.
12. **Scope:** no strategy-performance, profitability, calibration, or OOS claim is inferred from Stage 1.

A pull-request run may prove build, CTest, live L1/L2, and schema validation, but it skips Telegram delivery and persistent-state writes. It is a pre-merge engineering gate and **does not count** as either of the two complete Stage 1 acceptance runs.

## 3. v1 — Active Implementation

**Assumption:** the existing C++ L1 collector, L2 C10 validator, and Telegram L3 components can be reused safely after replacing the V18.2 run manifest with the V21 contract and explicitly excluding legacy strategy execution.

**Implementation:**
- Keep the existing C++20 build and tested public OKX adapter.
- Emit V21 run-manifest v2.
- Represent LRT/NMT/VTM as rejected and the active strategy engine list as empty.
- Keep the legacy A/B/C/H and H1-H7 system-status fields disabled where the historical system-status contract still requires them.
- Reuse Telegram outbox/inbound deduplication with the V21 manifest.
- Keep all fallback providers explicitly unavailable until separately implemented and equivalence-tested.

**v1 status:** merged to main via PR #175, but failed Stage 1 acceptance. Main run `45223598065` on commit `7ef03f861a9e41906f1aa4787da6ffca21c2cd4d` passed C++ build/tests and delivered Telegram (HTTP 200, message_id=91), but its manifest remained `DATA_DEGRADED`, not `L1_L2_L3_PASS`. ZEC-USDT-SWAP had 9,182 hourly candles and was reported at 52.37% coverage against the global 2-year denominator (17,532 rows). The official OKX listing notice states that the ZEC USDT perpetual began trading on 2025-11-06 at 03:15 UTC: https://www.okx.com/en-us/help/okx-to-list-perpetual-futures-for-dash-zec-crypto . The collector already had `listing_time_ms`, but the final coverage calculation and cache snapshot denominator used the global start time. This is a D3 implementation defect, not missing market history. Because `record_outbound_manifest` promotes the run only from `L1_L2_PASS`, successful Telegram delivery could not repair the degraded run status.

The existing inbound state records update `610176013` and reply message `43`, but that evidence belongs to an older revision. The prior replay workflow only polled Telegram with offset `last_update_id + 1`; it did not pass the same update through the production duplicate-update handler. The `[TELEGRAM_INBOUND_TEST]` push path also skipped outbound delivery, preventing one push-triggered run from proving both outbound and inbound acceptance. Main has only one complete Stage 1 live run on the V21 implementation revision; no two-run same-revision acceptance evidence exists. The pull-request run does not count.

## 4. Diagnosis Protocol (D1–D6)

Only apply a diagnosis after a real v1 failure, using run IDs, logs, schema errors, HTTP responses, timestamps, or test counts.

- **D1 Data:** provider unreachable, stale/partial series, missing funding/OI, timestamp or unit failure.
- **D2 Assumption:** reuse of a legacy contract or data semantics proves insufficient for V21.
- **D3 Implementation:** C++ compile/runtime defect, schema mismatch, manifest mutation defect, Telegram delivery/inbound/replay defect.
- **Confirmed v1 D3:** OHLCV completeness was measured against the global two-year window instead of the instrument's actual listing window. A newly listed perpetual was therefore falsely marked PARTIAL, which forced `DATA_DEGRADED` and prevented L3 promotion. The old replay workflow did not invoke the duplicate-update handler with the same update ID.
- **D4 Threshold/Calibration:** Stage 1 has no strategy threshold tuning. Any proposal to weaken data-quality, freshness, or acceptance rules is rejected unless the owner formally changes the source.
- **D5 Regime:** not applicable to Stage 1 strategy selection; market regime is not used to manufacture a signal.
- **D6 Expectations:** distinguish a successful infrastructure/status report from a calibrated trading signal or profitable strategy.

## 5. v2 — Built After Confirmed v1 FAIL

**Alternative assumption:** OHLCV completeness must be evaluated against each instrument's valid tradable history, bounded by the configured global lookback, rather than assuming every perpetual existed for the entire two-year window. Exact duplicate-update handling must be tested by replaying the same update ID through the same production handler, not by merely polling Telegram again.

**v2 implementation on isolated branch `fix/v21-stage1-listing-coverage-and-replay`:**
- Compute expected OHLCV rows from `max(global_window_start, listing_time_ms)`; retain the strict 100% completeness rule. Missing candles remain PARTIAL; no threshold is relaxed.
- Apply the same listing-aware denominator to cache validation, cache retention, and final L1 coverage.
- Remove Stage 1's hidden dependency on the legacy `shadow_candidate_registry`; V21 universe selection no longer imports pending candidates from rejected legacy strategy state.
- Extract the production duplicate-update handler and add a deterministic replay mode that passes the same processed update ID through it with a sender that fails the test if a second reply is attempted.
- Add replay status and update ID to the V21 run manifest schema.
- Allow the controlled inbound push path to perform outbound delivery first, then receive `/status`, then replay the exact update.
- Enforce two complete runs with distinct run IDs and the same `GITHUB_SHA`; at least one of those two must record `RECEIVED_PROCESSED` and replay PASS.

**v2 status:** code and tests are on the isolated branch. CI/build/test and live acceptance are NOT_YET_VERIFIED. No merge to main has been performed.

## 6. v3 — Conditional Only

Do not build unless v2 records a real FAIL.

**Alternative assumption:** direct live-provider acquisition from the GitHub runner is too unstable for a repeatable complete run, even after the V21 pipeline boundary is isolated.

**Conditional redesign:** use a second independently verified public-data source or an independently archived public snapshot for the data layer, while labeling any unavailable live field as UNAVAILABLE; do not synthesize or proxy it as REAL. Telegram remains the only delivery channel.

## 7. Escalation

If v1, v2 and v3 all fail, or the V21 Stage 1 gate fails, stop implementation and invoke the V21 Innovation Protocol in order:

1. Data Expansion
2. Timeframe Shift
3. Simplicity Audit
4. Regime Restriction
5. Alternative Market
6. Honest Stop

No fourth rewrite is permitted. No acceptance criterion may be relaxed to force PASS.

## 8. Budget

Maximum three versions total: v1, v2, v3. v2 and v3 are conditional and may only be implemented after evidence-backed failure of the preceding version. Implementation budget: v1 FAILED; v2 is built on an isolated branch and awaits CI/live validation; v3 remains unbuilt.
