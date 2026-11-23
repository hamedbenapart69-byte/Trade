# V21 Stage 1 — SLRP Plan

**Status:** PLAN BASELINED / EXECUTION IN PROGRESS  
**Controlling source:** MASTER SOURCE V21.0 + V21 Execution Protocol Addendum  
**Architecture:** CFSS V21 Architecture Design V1  
**Stage owner approval:** 2026-11-23  
**Active version:** v1 (only)

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
7. **L3 outbound:** Telegram API returns HTTP 200, ok=true, and a persisted positive message_id; manifest records DELIVERED and L1_L2_L3_PASS.
8. **L3 inbound:** at least one of the two runs must receive and process a controlled /status update from the authorized chat; replaying the same update does not generate a second reply; the relevant manifest records RECEIVED_PROCESSED and controlled acceptance.
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

**v1 status:** implementation committed to the isolated V21 branch; PR checks and live L1/L2 validation pending. No V21 L3 acceptance run has been claimed.

## 4. Diagnosis Protocol (D1–D6)

Only apply a diagnosis after a real v1 failure, using run IDs, logs, schema errors, HTTP responses, timestamps, or test counts.

- **D1 Data:** provider unreachable, stale/partial series, missing funding/OI, timestamp or unit failure.
- **D2 Assumption:** reuse of a legacy contract or data semantics proves insufficient for V21.
- **D3 Implementation:** C++ compile/runtime defect, schema mismatch, manifest mutation defect, Telegram delivery/inbound/replay defect.
- **D4 Threshold/Calibration:** Stage 1 has no strategy threshold tuning. Any proposal to weaken data-quality, freshness, or acceptance rules is rejected unless the owner formally changes the source.
- **D5 Regime:** not applicable to Stage 1 strategy selection; market regime is not used to manufacture a signal.
- **D6 Expectations:** distinguish a successful infrastructure/status report from a calibrated trading signal or profitable strategy.

## 5. v2 — Conditional Only

Do not build unless v1 records a real FAIL.

**Alternative assumption:** the current monolithic C++ pipeline cannot provide a stable, auditable V21 vertical slice because the L1/L2 boundary or manifest lifecycle is structurally coupled to legacy V18.2 assumptions.

**Conditional redesign:** introduce a separate V21 pipeline boundary with an immutable L1 snapshot contract, a standalone C++ L2 status process, and a separately versioned Telegram delivery envelope. No legacy strategy implementation is copied.

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

Maximum three versions total: v1, v2, v3. v2 and v3 are conditional and may only be implemented after evidence-backed failure of the preceding version. Current implementation budget consumed: v1 only.
