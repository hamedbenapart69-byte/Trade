# Hybrid Stage 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and prove one reproducible Hybrid L1/L2/L3 pipeline with Python acquisition/export, authoritative C++ compute, immutable artifacts, and Telegram-only delivery.

**Architecture:** Reuse the inspected Python historical collector as a temporary L1 acquisition component, but restrict it to public data fetching and versioned raw-data export. C++ independently validates and admits the contract, produces complete C10 states and immutable run artifacts, and owns Telegram outbound/inbound delivery, idempotency, receipts, and recovery. No strategy may emit an actionable trade unless its registered hard gates, calibration, and net EV requirements are satisfied.

**Tech Stack:** Python 3.11 for L1 acquisition/export only; C++20, CMake, CTest, libcurl, and a reviewed JSON library for L2/L3; JSON Schema; Parquet retained as an internal historical storage format; GitHub Actions free tier; Telegram Bot API.

**Spec:** V18.2 §§43–47 plus the owner-approved Hybrid amendment (Python L1 temporary; C++ L2/L3 authoritative). The amendment must explicitly supersede only the conflicting L1 ownership clauses; it does not weaken any acceptance criterion.

## Global Constraints

- C++ owns authoritative validation/admission, normalization, compute, C10 states, hard gates, risk, artifacts, and Telegram.
- Python may only fetch public data, perform provider acquisition fallback, and export raw observations plus provenance in the versioned contract.
- No exchange account credentials, private endpoints, order placement, modification, cancellation, or execution.
- Telegram is the only user-facing delivery channel.
- Zero-cost dependencies and GitHub Actions free-tier-compatible runtime only.
- Preserve existing Python modules and branches until migration PASS and explicit retirement approval.
- Missing values remain null/UNAVAILABLE; never coerce missing funding, OI, or prices to zero.
- No actionable signal with NOT_CALIBRATED confidence or absent/non-positive net EV.
- No PROXY may be relabelled REAL.
- No merge to main or external deployment is implied by branch implementation.
- Stage 1 PASS requires all S1-01 through S1-12 and two consecutive complete three-layer runs.

## Review Focus

1. Incomplete or still-open candles must never enter the C++ admitted set as completed observations.
2. A provider fallback with a different contract multiplier, settlement, market type, or timeframe must be rejected rather than silently mixed.
3. Missing funding/OI must remain missing, not become numeric zero.
4. Duplicate, out-of-order, stale, future-dated, NaN, and infinite observations must fail admission with explicit reason codes.
5. Telegram timeout after request transmission must become DELIVERY_UNKNOWN until reconciled; it must not trigger an unbounded duplicate send.

---

### Task 1: Freeze the Hybrid amendment and contract ownership

**Files:**
- Create: `docs/architecture/ADR-001-hybrid-l1-ownership.md`
- Create: `docs/architecture/ADR-002-versioned-l1-contract.md`
- Create: `docs/superpowers/plans/2026-11-17-hybrid-stage1.md` (this plan)

**Interfaces:**
- ADR-001: Python L1 acquisition/export only; C++ L2/L3 authoritative.
- ADR-002: versioned JSON contract with explicit null, timestamps, contract identity, source provenance, coverage, errors, and quality labels.

- [ ] Record the approved Hybrid decision and the exact V18.2 clauses it amends.
- [ ] Keep ADR-002 through ADR-005 status explicitly aligned with the owner's actual approval; do not label proposals approved without evidence.
- [ ] Add a conflict register explaining that V18.2 §§43.1–43.2 otherwise assign L1 to C++.
- [ ] Test/document that Python cannot calculate signal states, gates, risk, or release eligibility.

### Task 2: Quarantine the unsafe C++ prototype delivery path

**Files:**
- Modify: `cpp/apps/market_pipeline/main.cpp`
- Modify: `.github/workflows/cpp-foundation.yml`
- Test: `cpp/tests/test_main.cpp`

**Interfaces:**
- `market_pipeline` becomes an L2 contract consumer and artifact producer; it must not fetch exchange APIs directly or send Telegram messages.
- Telegram delivery is isolated in the dedicated L3 executable.

- [ ] Add a failing test proving NOT_CALIBRATED or missing EV cannot produce BUY_NOW/SELL_NOW.
- [ ] Add a failing test proving the L2 executable cannot perform outbound Telegram HTTP.
- [ ] Remove direct provider acquisition and direct Telegram side effects from the L2 executable.
- [ ] Keep the build/test workflow side-effect-free; live delivery occurs only in the dedicated controlled L3 workflow step.

### Task 3: Implement the versioned Python L1 exporter

**Files:**
- Create: `contracts/l1-market-data.v1.schema.json`
- Create: `signal_autopilot/scripts/export_l1_contract.py`
- Modify only if required: `signal_autopilot/app/data_layer/collector.py`
- Test: `signal_autopilot/tests/test_l1_contract_export.py`

**Interfaces:**
- CLI: `python signal_autopilot/scripts/export_l1_contract.py --provider okx --symbols 100 --years 2 --output <path>`
- Output: one versioned JSON run envelope containing run identity, producer identity, acquisition time, declared universe, per-instrument exact contract identity, timeframe, candle completion flags, OHLCV, funding, OI, provider provenance, coverage, quality status, and errors.
- Exporter may call the existing collector and serialize its acquired results; it must not create trade decisions or C10 states.

- [ ] Write tests for missing/null values, duplicate timestamps, provider provenance, exact contract identity, and incomplete candles.
- [ ] Run tests and confirm expected failures before implementation.
- [ ] Implement export with deterministic field ordering/canonical serialization where practical.
- [ ] Fix the existing funding-history zero-coercion defect at the acquisition boundary so absent funding is null/UNAVAILABLE.
- [ ] Validate the produced JSON against the committed JSON Schema.
- [ ] Preserve the underlying Parquet files and existing collector behavior outside the narrowly tested correction.

### Task 4: Implement authoritative C++ L2 admission and C10 artifacts

**Files:**
- Create: `cpp/include/cfss/contracts/l1_market_data.hpp`
- Create: `cpp/src/contracts/l1_market_data.cpp`
- Create: `cpp/include/cfss/signals/run_artifact.hpp`
- Create: `cpp/src/signals/run_artifact.cpp`
- Modify: `cpp/CMakeLists.txt`
- Modify: `cpp/apps/market_pipeline/main.cpp`
- Test: `cpp/tests/contract/`, `cpp/tests/unit/`

**Interfaces:**
- Input: validated path to `l1-market-data.v1.json`.
- Output: immutable `signals.json`, `coverage.json`, `provider_health.json`, `system_status.json`, and `run_manifest.json`.
- Each instrument in the frozen universe receives exactly one allowed C10 state and an explicit reason code.
- With no validated strategy candidate, the correct state is NO_QUALIFIED_SETUP; invalid or critical data becomes MARKET_DATA_DEGRADED.

- [ ] Test schema-version rejection, null semantics, numeric finiteness, candle chronology, completion, OHLC relationships, duplicates, staleness, and contract mismatch.
- [ ] Test all seven C10 states and exactly-one-state-per-instrument completeness.
- [ ] Test canonical artifact hashing and atomic publication.
- [ ] Ensure NOT_CALIBRATED, missing EV, or EV <= 0 cannot become actionable.
- [ ] Ensure L2 has no provider HTTP adapter and no Telegram delivery dependency.

### Task 5: Implement C++ L3 Telegram outbox, outbound, and inbound

**Files:**
- Create: `cpp/include/cfss/delivery/outbox.hpp`
- Create: `cpp/src/delivery/outbox.cpp`
- Create: `cpp/apps/telegram_inbound/main.cpp`
- Modify: `cpp/apps/telegram_delivery/main.cpp`
- Modify: `cpp/CMakeLists.txt`
- Test: `cpp/tests/reliability/`, `cpp/tests/integration/`

**Interfaces:**
- L3 consumes only a finalized, hash-verified artifact.
- Outbound states: PENDING, SENDING, DELIVERED, RETRYABLE_FAILURE, PERMANENT_FAILURE, DELIVERY_UNKNOWN.
- Successful Telegram API responses persist message_id and delivery metadata.
- Inbound polling persists update_id/offset and deduplicates updates.
- Permitted commands initially: /start, /help, /status, /last. No order or account commands.

- [ ] Test idempotency across retries and restarts.
- [ ] Test ambiguous timeout becomes DELIVERY_UNKNOWN.
- [ ] Test token redaction and bounded retry behavior.
- [ ] Test inbound update deduplication and safe command allowlist.
- [ ] Run a controlled real outbound test and retain positive Telegram response plus message_id.
- [ ] Receive a real user-originated Telegram update and retain update_id evidence; do not treat a mock as inbound PASS.

### Task 6: Integrate GitHub Actions orchestration

**Files:**
- Create: `.github/workflows/hybrid-stage1.yml`
- Modify: `.github/workflows/cpp-foundation.yml`
- Create: `docs/runbooks/hybrid-stage1.md`

**Interfaces:**
- Schedule target: `0 */4 * * *`, subject to verified free-tier runtime and concurrency limits.
- Workflow order: Python L1 fetch/export → C++ L2 admission/compute/artifacts → C++ L3 Telegram outbound/inbound checks → manifest/evidence upload.
- Secrets: Telegram delivery only; never exchange trading credentials.

- [ ] Add manual dispatch for controlled testing and scheduled execution only after the branch workflow is verified.
- [ ] Enforce non-overlapping runs and bounded job time.
- [ ] Separate acquisition, compute, artifact, outbound, and inbound failure statuses.
- [ ] Ensure a partial run cannot publish a complete-success manifest.
- [ ] Ensure a missing Telegram token is SKIPPED/FAIL according to the acceptance context, never PASS.

### Task 7: Stage 1 verification and SLRP v1 report

**Files:**
- Create: `docs/evidence/stage-1-report.md`
- Create: `docs/evidence/stage-1-run-ledger.json`

- [ ] Verify S1-01 clean C++ build with compiler/toolchain and binary hash.
- [ ] Verify S1-02 actual C++ runtime execution.
- [ ] Verify S1-03 real backend provider access with timestamps and provenance.
- [ ] Verify S1-04 equivalent provider fallback or explicit UNAVAILABLE.
- [ ] Verify S1-05 frozen universe and per-symbol coverage.
- [ ] Verify S1-06 schema-valid C10 artifacts, deterministic tests, and hashes.
- [ ] Verify S1-07 real Telegram outbound response and message_id.
- [ ] Verify S1-08 real inbound update and deduplication.
- [ ] Verify S1-09 two consecutive complete L1/L2/L3 runs.
- [ ] Verify S1-10 distinct failure honesty for provider, compute, artifact, and Telegram.
- [ ] Verify S1-11 no user-side exchange/provider/tool connectivity.
- [ ] Verify S1-12 zero-cost dependency and runner budget.
- [ ] Answer all five required self-critique questions with evidence.
- [ ] Record v1 PASS/FAIL and D1–D6 diagnosis. Do not build v2/v3 unless v1 actually FAILS and the diagnosis justifies it.

---

## Stage 1 acceptance gate

Stage 1 remains **NOT PASS** until every S1-01 through S1-12 item is proven and two consecutive complete three-layer runs pass. A successful C++ build, CI run, one Telegram message, or a mock inbound test is insufficient. No later stage begins before explicit owner approval.
