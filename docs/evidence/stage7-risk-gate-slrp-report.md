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
Earlier cross-check from Stage 6 PR live-validation run `44759484737` on head `38c3dff7781fc888c5c3a1078091de5a099f19ea`:
- The PR validation workspace produced 2 strategy candidates and the Stage 7 gate blocked both.
- `risk_snapshot_status=UNAVAILABLE`, `actionable=0`, `trade_execution_allowed=false`.
- The PR workspace transiently backfilled 5 historical outcomes with cost status `PROXY`; it did not persist these costs to the production `signals` branch.
- A direct read of the persistent `signals` branch shows 5 ledger outcomes, all `cost_status=UNAVAILABLE`, all `execution_status=NOT_EXECUTED`, all `outcome_kind=HYPOTHESIS_PROXY`; 1 TARGET and 4 STOP. The 10-row candidate registry has 5 RESOLVED, 4 REJECTED and 1 PENDING.
- These are hypothetical shadow resolutions, not executed trades or a validated shadow NAV series.
- Telegram report preparation was validated without sending a message from this PR workflow.
- No user account data was requested or used.

## Additional acceptance blocker — risk denominator

V18.2 §10.4 requires precise definitions for the measurement basis, start/end timestamps, realized versus simulated equity, fees/funding, open versus closed trade treatment, and reset rules. The current implementation has no registered shadow-NAV/risk-unit configuration. The outcome ledger's R-multiples are normalized by each candidate's entry-to-stop distance; that alone does not define portfolio equity or convert aggregate R into daily/weekly/drawdown percentages. No percentage risk snapshot may be inferred from these R values without a declared portfolio sizing model.

This is a D2 design gap in addition to the D1/D3 evidence gaps above. A Stage 7 v2 snapshot builder must accept a versioned, immutable risk-basis configuration and fail closed when it is absent or mismatched. A fixture-only configuration may test arithmetic but must never be treated as the production risk basis.

## v2 — planned after Stage 6 v2 costed ledger

Core assumption: risk is measured from the system's own shadow portfolio, not from a user's real exchange account.

Planned implementation:
1. Build a provenance-bound internal shadow-risk snapshot from costed closed outcomes and open/pending shadow positions.
2. Record daily and weekly net loss, rolling portfolio drawdown, open exposure count, and source ledger/registry hashes.
3. Include already-open same-direction exposures in the G5 correlation count.
4. Keep the gate blocked if cost coverage, risk-unit definition, portfolio history or position state is incomplete.
5. Preserve all kill-switch thresholds; no relaxation.

**v2 status:** not yet built. The PR-only cost-proxy backfill is transient and the persistent ledger still has 5 `UNAVAILABLE` cost rows. The cohort remains `NOT_CALIBRATED`; no validated shadow NAV exists; and V18.2's loss denominator/risk unit is not configured. V2 may be built only around an explicit versioned risk-basis input, with no default capital or sizing assumption. Until then the production snapshot remains `UNAVAILABLE`.

## v3

Not built. R11 prohibits v3 unless v2 records a real FAIL with specific evidence.

## Handoff

- v1 policy core remains active and fail-closed.
- Overall Stage 7 remains BLOCKED until L1 shadow-risk snapshot and open-exposure coverage pass.
- No BUY/SELL promotion, no user account connection, no trading keys and no order execution.


## Latest-head evidence — 2026-11-20

Stage 6 PR live-validation run `44773010525` completed successfully on head `ad0e855754c13dea159e61dbed484f0b1daa1740`.
- 61 instruments were selected for 15m resolution data; this remains below the approximate 100-symbol target.
- The PR-only shadow tracker transiently backfilled costs for 5 historical outcomes as `PROXY`; no persistent ledger write occurred.
- Stage 7 generated 27 candidate rows and blocked all 27.
- `risk_snapshot_status=UNAVAILABLE`, `actionable=0`, `trade_execution_allowed=false`.
- Telegram preparation was validated, but the workflow explicitly sent no Telegram message.
- Direct persistent-ledger inspection after the run still shows 5 outcomes, all `cost_status=UNAVAILABLE`, `execution_status=NOT_EXECUTED`, `outcome_kind=HYPOTHESIS_PROXY`; 1 TARGET and 4 STOP.

### Source-clause correction

The risk-basis acceptance blocker is grounded in **V18.2 §10.4 — Risk Circuit Breakers**, not §37.3. Section 10.4 lists the required measurement-basis, timestamp, equity, cost, open/closed-position and reset definitions. The versioned immutable risk-basis configuration is an implementation control derived from those requirements; it is not quoted as a literal V18.2 clause.

### Current v2 readiness

The live PR run proves that the current pipeline can generate the Stage 7 artifact and block candidates, but it does not provide persistent costed shadow history or a registered sizing/denominator model. Therefore the planned v2 snapshot builder still lacks valid production inputs. No arbitrary NAV, 1R percentage or reset convention is being inserted. A test fixture may exercise arithmetic only and must remain explicitly non-production. The v2 implementation and any production risk basis remain unapproved/unavailable until their inputs are properly specified and evidenced.
