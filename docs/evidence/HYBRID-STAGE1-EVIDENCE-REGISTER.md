# Hybrid Stage 1 Evidence Register

**Repository:** hamedbenapart69-byte/Trade  
**Branch:** feat/hybrid-stage1  
**Evidence revision:** d62ec9b3a6371bb9bf50b2e9d7ceccd46a1e3860  
**Status:** IN PROGRESS — NOT STAGE 1 PASS

## Architecture boundary
- L1 acquisition/export: Python; raw-only, versioned JSON contract.
- L2 validation/admission/artifact: C++20.
- L3 Telegram outbound/inbound: C++20.
- User-side exchange access, trading credentials and order execution: prohibited.

## Verified evidence

### L1 → L2 live integration
GitHub Actions run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/44119249492

- Result: successful real runner execution.
- L1 provider: OKX public API.
- Instruments exported: 10 perpetual contracts.
- BTC context: present.
- C++ L2 artifact: 10 instrument rows.
- Status rows: 10 NO_QUALIFIED_SETUP; 0 BUY_NOW/SELL_NOW.
- L1 export: artifacts/l1-market-data.v1.json.
- L2 export: artifacts/l2-status.v1.json.
- Run ID: 94cbbfad-791a-4150-abf5-eae073260128.
- Artifact: hybrid-stage1-l1-l2-44119249492.
- This is one successful 10-symbol L1/L2 run, not two complete three-layer runs. Two 100-symbol L1/L2 coverage runs are in progress/queued.

### CI on evidence revision
- C++20 build and unit tests: PASS — run 44125052812.
- Python L1 contract tests: PASS — run 44125052887.
- C++ L2 contract tests: PASS — run 44125052887.
- Full repository CI: run 44125052833 was still in progress when this register was updated.
- Policy guard: earlier revision 511d65967433c83582b38b06b7afda6dffb503f9 passed run 44121955460; latest revision policy check not yet independently confirmed.

### C++ L3 implementation and live evidence
- Live delivery run 44126127032 completed successfully.
- Source L1/L2 run: 44119249492; source_run_id: 94cbbfad-791a-4150-abf5-eae073260128.
- Telegram response: HTTP 200, DELIVERED, message_id 36.
- Outbox receipt persisted to signals branch commit 93e764a.
- Twelve inbound polls succeeded at transport level, but last_update_id remained 0; no controlled inbound command was received. Inbound command acceptance/deduplication remains unverified.

### C++ L3 implementation present
- SHA-256 integrity helper for immutable L2 artifacts; verification before outbound delivery.
- Telegram outbound with fsync-backed atomic outbox persistence, bounded retries, message ID capture and DELIVERY_UNKNOWN state.
- Telegram inbound polling with fsync-backed atomic state, authorized chat filter, command allowlist, update deduplication and persisted receipts.
- Crash recovery converts ambiguous SENDING / REPLY_SENDING states to DELIVERY_UNKNOWN.
- Unit tests cover outbox policy, HTTP response classification, state reconciliation, conditional reports, command allowlist, SHA-256 tamper detection and atomic-write/immutable-overwrite behavior.
- Code compilation and unit tests pass on evidence revision. This is not evidence of a real Telegram API send or inbound update.

## S1 acceptance register

| ID | Acceptance area | Current result | Evidence / remaining work |
|---|---|---|---|
| S1-01 | Clean C++20 build | PASS | C++ Foundation run 44125052812 |
| S1-02 | Actual C++ runtime | PASS (slice) | Real L1 artifact consumed by C++ in run 44119249492 |
| S1-03 | Real public market data | PASS (slice) | 10 OKX perpetual instruments + BTC context |
| S1-04 | Provider fallback | PENDING | Need a controlled runner-side fallback/recovery test with exact contract equivalence |
| S1-05 | L1 market coverage | IN PROGRESS | 100-symbol run 44123123760 running; second sequential run 44123138538 queued; no completion evidence yet |
| S1-06 | L2 validation and correctness | PASS (slice) | Python/C++ contract tests run 44125052887 and 10/10 real C++ status rows in run 44119249492 |
| S1-07 | Real Telegram outbound | PASS (10-symbol slice) | Run 44126127032; HTTP 200, message_id 36, outbox commit 93e764a |
| S1-08 | Real Telegram inbound | PENDING | 12 successful polls, but last_update_id=0; controlled /status or /help update not yet received |
| S1-09 | Two consecutive complete L1/L2/L3 runs | PENDING | One 10-symbol outbound L3 run; 100-symbol L1/L2 run 44123123760 running and second 44123138538 queued; inbound command evidence pending |
| S1-10 | Honest failure/degraded reporting | PARTIAL | Safe defaults and fail-closed tests exist; provider outage/fallback runtime evidence remains |
| S1-11 | No user-side data connectivity | PASS (architecture) | Acquisition runs on GitHub-hosted runner; no exchange account credentials or user-side fetch |
| S1-12 | Zero-cost deployment/runtime | PENDING FINAL ACCOUNTING | Uses public APIs, standard GitHub-hosted runner and open-source system packages; actual quota/billing ledger not inspected |

## SLRP — Stage 1

- v1: Python raw-only L1 exporter → versioned JSON → C++20 L2 → C++20 Telegram L3.
- v1 result: L1/L2 slice PASS; complete three-layer Stage 1 remains NOT PASS because S1-04, S1-05, S1-07, S1-08, S1-09, S1-10 and S1-12 remain pending/partial.
- Diagnosis: no v1 failure has been established for the tested L1/L2 slice. Do not build v2/v3 merely because L3 runtime evidence is pending; first finish the v1 controlled test.
- Active version: v1.
- Handoff: finish controlled L3 operational test, fallback test, and expand symbol coverage; then repeat two complete consecutive three-layer runs.

## Release control
- PR #148 remains DRAFT and unmerged.
- No production deployment or live Telegram send is claimed.
- No existing Python modules or legacy branches were deleted.
- Stage 1 must not be marked PASS until every S1 criterion is supported by retained evidence.
