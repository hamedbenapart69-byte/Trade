# STAGE 7 — CONSENSUS, RISK, MANUAL EXECUTION GATE (V18.2)

**v1 policy core:** ENGINEERING PASS  
**Overall stage:** BLOCKED — internal shadow-risk L1 is incomplete  
**Operational status:** FAIL-CLOSED / NO SIGNAL PROMOTION  
**Execution:** permanently forbidden; the user reviews signals and places any trade manually.

## Acceptance criteria

- Golden Rule precedence and independent LRT/NMT consensus.
- Candidate existence, REAL/PROXY data classification, liquidity, calibration and positive net EV checks.
- Daily loss limit 5%, weekly loss limit 10%, portfolio drawdown limit 20%.
- G5 counts at most three same-direction correlated exposures above 0.70, including already-open internal shadow positions.
- Risk snapshot must describe only the system's own shadow portfolio.
- Every output remains `actionable=false` and `trade_execution_allowed=false`.
- Telegram is the only delivery channel.

## Three layers

- **L1 DATA — INCOMPLETE:** no internal shadow-risk snapshot builder is connected yet. This is not a request for user balances or exchange account data. The snapshot must be derived from the system's own costed shadow outcome ledger and pending/open shadow positions.
- **L2 COMPUTE — v1 PASS:** deterministic C++ risk gate, Golden Rule precedence, independent LRT/NMT consensus, 90-day same-direction candidate correlation and fail-closed fallback.
- **L3 DELIVERY — integration PASS:** Stage 6 + Stage 7 workflow run `44726308730` generated and schema-validated the Stage 7 artifact and delivered Telegram message `75` with HTTP 200.

## v1 — PARTIAL PASS / OVERALL FAIL

Engineering evidence:
- Stage 7 C++ workflow: full build and 14/14 CTest passed.
- Both Stage 7 JSON Schemas compiled.
- Fail-closed guards passed.
- Integrated Stage 6 + Stage 7 Telegram delivery succeeded.

Earlier live evidence from run `44726308730` (baseline):
- `risk_snapshot_status=UNAVAILABLE`.
- `candidate_count=0`; `actionable_count=0`.
- `trade_execution_allowed=false`.
- No live candidate was available to exercise the gate end-to-end.

### Diagnosis

- **D1 — Data:** the internal shadow-risk snapshot is not produced.
- **D3 — Implementation:** current G5 counts correlated candidates in the current scan but does not yet include already-open shadow positions from the persistent registry.
- **D1/D3 — Dependency:** Stage 6 has only 5 outcomes and costs are unavailable; a reliable shadow equity curve cannot yet be calculated.

No user account data may be substituted for these missing internal records.
Latest cross-check from Stage 6 PR live-validation run `44754721823` on head `3c6cbb46a1f51d4dd4d7622d0d6970afd7ed598e`:
- The current run produced 2 strategy candidates and the Stage 7 gate blocked both.
- `risk_snapshot_status=UNAVAILABLE`, `actionable=0`, `trade_execution_allowed=false`.
- The persistent shadow ledger supplied 5 outcomes; all 5 received provenance-backed `PROXY` costs during this run. This does not establish a sufficiently long or complete shadow equity curve.
- Telegram report preparation was validated without sending a message from this PR workflow.
- No user account data was requested or used.

## v2 — planned after Stage 6 v2 costed ledger

Core assumption: risk is measured from the system's own shadow portfolio, not from a user's real exchange account.

Planned implementation:
1. Build a provenance-bound internal shadow-risk snapshot from costed closed outcomes and open/pending shadow positions.
2. Record daily and weekly net loss, rolling portfolio drawdown, open exposure count, and source ledger/registry hashes.
3. Include already-open same-direction exposures in the G5 correlation count.
4. Keep the gate blocked if cost coverage, risk-unit definition, portfolio history or position state is incomplete.
5. Preserve all kill-switch thresholds; no relaxation.

**v2 status:** not yet built. Stage 6 v2 now demonstrated cost-proxy backfill for 5 historical outcomes, but the Stage 6 cohort remains `NOT_CALIBRATED` and the available ledger is not sufficient to establish a reliable shadow equity curve. Build v2 only when the costed ledger, risk-unit definition, portfolio history and open-position state are adequate; otherwise preserve `UNAVAILABLE`.

## v3

Not built. R11 prohibits v3 unless v2 records a real FAIL with specific evidence.

## Handoff

- v1 policy core remains active and fail-closed.
- Overall Stage 7 remains BLOCKED until L1 shadow-risk snapshot and open-exposure coverage pass.
- No BUY/SELL promotion, no user account connection, no trading keys and no order execution.
