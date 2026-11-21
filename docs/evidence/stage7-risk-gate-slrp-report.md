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

## v2 — original planning baseline (superseded by the implementation section below)

Core assumption: risk is measured from the system's own shadow portfolio, not from a user's real exchange account.

Planned implementation:
1. Build a provenance-bound internal shadow-risk snapshot from costed closed outcomes and open/pending shadow positions.
2. Record daily and weekly net loss, rolling portfolio drawdown, open exposure count, and source ledger/registry hashes.
3. Include already-open same-direction exposures in the G5 correlation count.
4. Keep the gate blocked if cost coverage, risk-unit definition, portfolio history or position state is incomplete.
5. Preserve all kill-switch thresholds; no relaxation.

**Historical status at this report point:** v2 had not yet been built. The subsequent implementation and evidence are recorded in the later v2 section below. The persistent risk-basis and calibration blockers remain active.

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


## v2 — Shadow risk snapshot implementation (PR #169; overall stage remains BLOCKED)

**Implementation branch:** `feat/stage7-shadow-risk-snapshot-v2-20261120`  
**Latest inspected head:** `ef9759187b14cec8005150b9337f43a6e77fd687`  
**PR:** [#169](https://github.com/hamedbenapart69-byte/Trade/pull/169), open and not merged.

### Implemented L1/L2 contract

- Added a versioned frozen Shadow risk-basis schema. `initial_nav_units` and `risk_per_trade_pct` are mandatory; no default is embedded.
- Added a C++ snapshot builder and CLI probe. It binds the snapshot to the L1, ledger, candidate-registry and Meta-Cognition hashes.
- Computes normalized Shadow NAV from non-overlapping, costed closed outcomes using `net_R = win_R - loss_R - fee_R - slippage_R - funding_R`.
- Uses UTC day and Monday-start ISO-week buckets; daily and weekly loss remain at the maximum loss observed from period-start NAV until the relevant reset.
- Rejects missing/unfrozen basis, unavailable cost provenance, future/duplicate/out-of-basis outcomes, nonpositive NAV, overlapping intervals without entry-NAV provenance and filled open positions without mark-to-market evidence.
- Keeps every result system-Shadow-only and PROXY; `trade_execution_allowed=false` remains invariant.
- Extended read-only live PR validation to build the risk snapshot from fresh public L1 plus the persistent `signals` state, validate its schema, pass it into the Stage 7 risk gate, and prepare (but never send) the Telegram report.

### C++ and contract evidence

GitHub Actions run `44884181447` — **C++ Stage 7 Risk Gate Contract**:
- Full C++ build: PASS.
- CTest: **15/15 PASS**, including the new loss-then-recovery test for sticky daily/weekly kill-switch measurements.
- Stage 7 schema/contract and fail-closed guards: PASS.

On the same latest PR head:
- C++ Foundation: PASS (`44884181474`).
- Stage 6 Calibration Contract: PASS (`44884181463`).
- Stage 2 LFS, Stage 3 NSS, Stage 5 dual-engine and Stage 1 contract workflows: PASS.
- The expanded Stage 6 PR live-validation run `44884181454` is still running as of this report update; its fresh L1 collection has not yet completed. No live snapshot PASS is claimed.

### Current live-data blockers (persistent `signals` branch)

- Five closed outcomes remain in the persistent ledger; all five still have `cost_status=UNAVAILABLE` and null fee/slippage/funding values.
- One PENDING candidate has a recorded entry reference but lacks `entry_fill_time_ms`; no timestamp is inferred.
- No frozen `shadow_risk_basis.daily_swing.v1.json` exists on `signals`.
- Stage 6 remains `NOT_CALIBRATED`; five hypothetical outcomes do not establish a calibrated probability, EV or OOS performance.
- The v2 builder deliberately does not estimate unrealized PnL for open positions. Without a fresh mark and explicit cost treatment, it returns `UNAVAILABLE`.

### v2 disposition

**L2 engineering / contract:** PASS on the recorded C++ test run.  
**L1 persistent Shadow data:** BLOCKED.  
**L3 live Stage 7 integration:** pending the expanded read-only PR live-validation run; no Telegram send is performed by that test.  
**Overall Stage 7:** **BLOCKED / FAIL-CLOSED / NO SIGNAL PROMOTION**.

No risk basis or per-trade risk percentage was invented. V18.2 §10.4 requires the measurement basis, timestamps, simulated equity, fees/funding, open/closed treatment and reset rules to be defined; the owner has not approved the missing Shadow NAV and risk-per-trade values. The system must not substitute the separate historical $200/$4 playbook figures or any user-account balance for this internal Shadow configuration.

### Handoff

Do not start Stage 8 or promote candidates until all of the following have evidence:
1. An owner-approved frozen Shadow risk basis.
2. Persistent cost-provenance-backed outcomes.
3. Valid open-position mark-to-market or an explicit accepted closed-only treatment.
4. Stage 6 calibration gate no longer `NOT_CALIBRATED`.
5. Expanded live snapshot + risk-gate validation passes with the production-equivalent data contracts.

## Latest v2 hardening — immutable fills and unaccounted-outcome guard (2026-11-21)

### Diagnosis (D1 / D3)

- Persistent candidate `UNI/USDT:USDT` (`signal_id=ff20bd7719014075f4e3a94f73dcdc62874f7b3672b723d98236228bed02e82a`) is `PENDING` with `entry_fill_reference=4.845`, but `entry_fill_time_ms` is absent and the registry contains no stored resolution bars.
- The candidate's `source_run_id=okx-cpp-1795159176445` maps to Stage 6 run `44693771488`; that run has no retained Actions artifacts. The original L1 payload cannot be independently recovered. Reconstructing the timestamp from the current candle would be an unsupported inference.
- Before this hardening, the replay loop replaced a previously recorded fill with the current first-bar open and set the timestamp again. A filled candidate with a data gap at expiry could also be labeled `REJECTED`, while the risk builder only blocked filled `PENDING` candidates. That could silently alter a fill or remove an unaccounted fill from risk accounting.

### v2 correction

- A recorded `entry_fill_reference` and `entry_fill_time_ms` are immutable during replay.
- A legacy filled candidate without a recorded timestamp is never upgraded from `decision_time_ms` or a later candle. If it resolves without timestamp provenance, it becomes `UNVERIFIABLE`; no outcome-ledger row is fabricated.
- A filled candidate with a resolution data gap becomes `UNVERIFIABLE` after expiry, not `REJECTED`. The registry schema and run summary expose this state.
- Cost backfill requires an explicit positive `entry_fill_time_ms` that is not earlier than decision time and matches the first stored resolution-bar timestamp. Legacy closed outcomes are backfilled only from their stored `resolution_bars`.
- The risk snapshot rejects every filled candidate not in `RESOLVED`, every resolved candidate without a matching ledger row, and every ledger row without a registered candidate.
- The fee reference no longer claims an owner engineering decision. The V18.2 G3 0.04% reference is explicitly modeled as an assumed per-side proxy; it is not an exchange/account-specific fee tier and the resulting costs remain `PROXY`.

### Evidence

- The five persistent closed outcomes each have stored `resolution_bars`; in all five, the first stored bar timestamp equals `decision_time_ms` and its open exactly matches the recorded `entry_fill_reference`. This is sufficient evidence for the legacy timestamp migration from stored bars.
- The single pending UNI candidate has no such stored bar evidence and remains non-markable. The new code preserves its fill reference and blocks risk until it is resolved with verifiable provenance or otherwise reconciled.
- C++ Foundation run `44885939384` on head `f40a356d`: build and CTest **15/15 PASS**.
- Stage 7 Risk Gate Contract run `44885939352` on head `f40a356d`: workflow YAML validation, C++ build/CTest **15/15 PASS**, schema compilation and fail-closed guards PASS.
- Policy Guard run `44885939345`: PASS.
- Final timestamp-order guard commit `c1e795ba` is being revalidated; no result is claimed until its checks complete.
- Stage 6 read-only live validation run `44885939288` on `f40a356d` reached fresh L1 collection after C++ build/tests passed. The final-head live validation rerun is pending. PR live validation uses a bounded 10-symbol target, 1y sample plus required BTC/pending symbols; this is not the production 100-symbol/2y coverage gate.

### Current disposition

**L2 implementation/contract:** PASS on `f40a356d`; final `c1e795ba` rerun pending.  
**L1 persistent risk inputs:** BLOCKED — no frozen risk basis; one filled pending candidate lacks recoverable timestamp; persistent cost backfill has not yet been committed by a successful production run.  
**L3 live integration:** pending the final bounded read-only PR run; it sends no Telegram message.  
**Overall Stage 7:** **BLOCKED / FAIL-CLOSED / NO SIGNAL PROMOTION**.
