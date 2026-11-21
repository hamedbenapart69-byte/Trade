# Stage 7 — Shadow Risk Basis Contract v1

Status: **CONTRACT ADDED — RISK SNAPSHOT STILL BLOCKED**

## Purpose

V18.2 §10.4 requires the system-level 5% daily and 10% weekly kill-switches to use an explicitly defined research/Shadow equity basis. The denominator must be fixed for each experiment. This contract makes that basis an explicit, versioned input instead of silently assuming a user balance or inventing a denominator from R-multiples.

## Contract rules

- The basis applies only to the system's own shadow portfolio. `user_account_data_used` must be `false`.
- `initial_nav_units` and `risk_per_trade_pct` are mandatory. There is deliberately no default value.
- `basis_status` must be `FROZEN`; changing either value requires a new `basis_version` and an explicit supersession record.
- All timestamps and reset boundaries use UTC. Daily reset is 00:00 UTC; weekly reset is Monday 00:00 UTC.
- Equity means initial normalized NAV plus realized and marked-unrealized net PnL.
- Open positions require a fresh closed-candle mark and explicit costs. Missing/stale marks or missing cost provenance make the snapshot `UNAVAILABLE`.
- Closed outcomes with `cost_status=UNAVAILABLE` cannot be silently treated as zero-cost.
- PROXY costs must retain their source and assumption labels; a snapshot based on them remains PROXY and cannot be represented as REAL.
- This contract does not change Stage 6 calibration status, signal gates, kill-switch thresholds, or manual-only execution.

## Why no default NAV or risk unit is embedded

The source defines the required measurement basis but does not prescribe a normalized starting NAV or per-trade risk percentage. Those are experiment configuration values, not universal facts. The schema therefore requires explicit values and rejects omission. A fixture may test arithmetic, but it is not a production configuration.

## Current acceptance

- L1: **PARTIAL / BLOCKED** — the latest read-only PR live run backfilled all five historical cost rows as PROXY, but the persistent `signals` ledger was not written. A legacy filled UNI candidate still lacks recoverable fill-time provenance; complete open-position marks are not implemented.
- L2: **LATEST-HEAD PASS ON `89a96ec0`** — C++ Foundation and Stage 7 contract workflows passed full build and 15/15 CTest; all five Stage 7 schemas compiled and fail-closed guards passed. The latest read-only live integration run also completed successfully; production persistence is not claimed.
- L3: unchanged — Telegram remains the only user-facing channel; no production message is sent by this change.
- Stage 7 remains **BLOCKED** until persistent cost provenance, non-overlapping entry/close history or explicit entry-NAV accounting, open-position mark-to-market, and the upstream Stage 6 calibration gate are satisfied.
- Stage 6 remains **NOT_CALIBRATED**; Stage 7 cannot promote candidates while that upstream gate is blocked.

## C++ v2 snapshot builder

The implementation is in `cpp/include/cfss/shadow_risk_snapshot.hpp`, with the CLI probe in `cpp/apps/shadow_risk_snapshot_probe/main.cpp`.

- Uses `net_R = win_R - loss_R - fee_R - slippage_R - funding_R`; funding may be negative when the simulated position receives funding.
- Applies the frozen `risk_per_trade_pct` to the pre-event NAV. Outcomes with identical close timestamps use the same pre-event NAV and are aggregated before NAV is updated.
- Daily buckets are UTC calendar days; weekly buckets begin Monday 00:00 UTC.
- Portfolio drawdown uses the running NAV high-water mark.
- `daily_loss_pct` and `weekly_loss_pct` retain the maximum loss observed from the relevant period-start NAV; a later recovery does not erase a kill-switch breach before the next UTC reset.
- The builder rejects duplicate/future/out-of-basis outcomes, non-finite values, missing cost provenance, nonpositive NAV and every filled candidate whose state is not `RESOLVED`.
- Every `RESOLVED` candidate must have exactly one matching outcome-ledger row; every ledger row must map back to a registered candidate.
- The current version deliberately does not estimate unrealized PnL. Any filled candidate that is not `RESOLVED`, including `UNVERIFIABLE` or a data-gap `REJECTED` record, therefore makes the snapshot `UNAVAILABLE` until the fill has a matching closed outcome or a fresh mark-to-market input is implemented.
- A computed snapshot is labelled `data_class=PROXY`; it is not evidence of executed trades or REAL execution costs.

The scheduled Stage 6 workflow now invokes the builder before Stage 7 and persists the resulting snapshot on the `signals` branch. If no frozen basis file exists at `signals/cpp_runtime/shadow_risk_basis.daily_swing.v1.json`, the workflow passes an empty basis and the builder emits an explicit `UNAVAILABLE` snapshot. No implicit basis is created.

## Current stage disposition

The builder and contract are implementation work, not a Stage 7 PASS. Acceptance still requires a valid frozen basis, complete costed persistent history, open-position mark-to-market coverage, independent C++/CI evidence, and an upstream Stage 6 calibration gate that is no longer `NOT_CALIBRATED`.


### Entry-time provenance

The Shadow candidate registry now records `entry_fill_time_ms` when a new proxy fill is first observed. A previously recorded `entry_fill_reference` is immutable and is never overwritten by a later candle open. Legacy filled candidates without a recorded timestamp remain non-markable; no timestamp is inferred from decision time or later candles. If such a candidate resolves, or if a filled candidate reaches expiry with a data gap, it becomes `UNVERIFIABLE` and is not inserted into the performance ledger.


### Entry-NAV reconstruction guard

Each closed Shadow outcome now carries `entry_fill_time_ms`. Cost backfill requires this explicit timestamp, verifies that it matches the first stored `resolution_bars` candle, and verifies that the first candle's `open` matches the immutable `entry_fill_reference`. The timestamp must be between decision and close times. Legacy outcomes are upgraded only when both timestamp and price are proven by their stored `resolution_bars`; no decision-time substitution is permitted.

The snapshot builder rejects any overlap between closed-position intervals with `OVERLAPPING_SHADOW_OUTCOMES_ENTRY_NAV_UNAVAILABLE`. Without a recorded NAV at each entry, applying the current NAV at close would misstate the position's risk amount whenever another position closes while it is open. Non-overlapping intervals permit sequential reconstruction; overlapping intervals remain unavailable until explicit entry-NAV/risk-unit provenance or a correct portfolio mark-to-market ledger is implemented.

## Data-integrity guard added in Stage 7 v2

- A filled candidate cannot be made to disappear from risk accounting by changing its state to `REJECTED`. Any non-`RESOLVED` candidate with a recorded fill blocks the snapshot.
- A `RESOLVED` candidate without a matching ledger row blocks the snapshot. A ledger row without a registered candidate also blocks it.
- The persistent legacy `UNI/USDT:USDT` candidate has `entry_fill_reference=4.845` but no `entry_fill_time_ms`. Its original Stage 6 run (`44693771488`) has no retained workflow artifacts, so the original L1 payload cannot be independently recovered. The timestamp is therefore not reconstructed; the candidate remains unmarkable and will be quarantined as `UNVERIFIABLE` if it closes without provenance.
- The 0.04% fee reference from V18.2 G3 is modeled as an assumed per-side proxy in this build, not as a verified exchange/account fee tier. Cost output remains `PROXY`.

### Latest-head evidence — 2026-11-21

- PR #169 head: `89a96ec0fcd37c643fbf4a822ec0758f6bb60548`.
- Stage 7 contract run `44892775998`: full build, **15/15 CTest**, schema compilation and fail-closed guards PASS.
- C++ Foundation run `44892776072`: full build and **15/15 CTest** PASS.
- Stage 6 PR live run `44892776007`: **SUCCESS**. It collected 16 public OKX instruments; required historical/pending symbols were present 6/6; 15m data was available 16/16; five historical costs were transiently backfilled as PROXY (5/5). LFS v2 was calculated for 15/16 and NSS v2 for 13/16; unavailable inputs remained explicitly UNAVAILABLE.
- The same read-only run generated Meta-Cognition with 5 outcomes, but all confidence states remained `NOT_CALIBRATED`. Stage 7 risk snapshot remained `UNAVAILABLE` because no frozen risk basis exists. The risk gate blocked all 3 candidates; actionable count was 0. No Telegram message was sent and no persistent `signals` state was written.
- The persistent `signals` branch still has 5 historical outcomes with unavailable costs until a production scheduled run persists the backfill. The legacy UNI filled candidate still has no recoverable fill timestamp. The original source run `44693771488` has no artifacts; its job log does not contain the original fill candle.
- The current builder still fails closed on filled non-resolved candidates because fresh-candle open-position mark-to-market has not been implemented.

**Disposition remains BLOCKED.** The implementation contract is passing, but a production Shadow NAV/risk basis, recoverable legacy fill provenance or an approved reconciliation policy, open-position mark-to-market, and Stage 6 calibration evidence are still absent. No defaults or account balances are substituted.
