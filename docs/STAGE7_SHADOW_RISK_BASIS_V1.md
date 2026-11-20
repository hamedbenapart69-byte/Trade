# Stage 7 — Shadow Risk Basis Contract v1

Status: **CONTRACT ADDED — RISK SNAPSHOT STILL BLOCKED**

## Purpose

V18.2 §37.3 requires the system-level 5% daily and 10% weekly kill-switches to use an explicitly defined research/Shadow equity basis. The denominator must be fixed for each experiment. This contract makes that basis an explicit, versioned input instead of silently assuming a user balance or inventing a denominator from R-multiples.

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

- L1: **BLOCKED** — persistent ledger still contains outcomes with unavailable costs; complete open-position marks/provenance are not yet evidenced.
- L2: **IMPLEMENTED IN PR / CI PENDING** — C++ snapshot builder, CLI probe, schema and fail-closed tests are present on the unmerged PR branch; production use is not claimed.
- L3: unchanged — Telegram remains the only user-facing channel; no production message is sent by this change.
- Stage 7 remains **BLOCKED** until persistent cost provenance, non-overlapping entry/close history or explicit entry-NAV accounting, open-position mark-to-market, and the upstream Stage 6 calibration gate are satisfied.
- Stage 6 remains **NOT_CALIBRATED**; Stage 7 cannot promote candidates while that upstream gate is blocked.

## C++ v2 snapshot builder

The implementation is in `cpp/include/cfss/shadow_risk_snapshot.hpp`, with the CLI probe in `cpp/apps/shadow_risk_snapshot_probe/main.cpp`.

- Uses `net_R = win_R - loss_R - fee_R - slippage_R - funding_R`; funding may be negative when the simulated position receives funding.
- Applies the frozen `risk_per_trade_pct` to the pre-event NAV. Outcomes with identical close timestamps use the same pre-event NAV and are aggregated before NAV is updated.
- Daily buckets are UTC calendar days; weekly buckets begin Monday 00:00 UTC.
- Portfolio drawdown uses the running NAV high-water mark.
- The builder rejects duplicate/future/out-of-basis outcomes, non-finite values, missing cost provenance, nonpositive NAV and any filled PENDING candidate.
- The current version deliberately does not estimate unrealized PnL. A filled open Shadow candidate therefore makes the snapshot `UNAVAILABLE` until a fresh mark-to-market input is implemented.
- A computed snapshot is labelled `data_class=PROXY`; it is not evidence of executed trades or REAL execution costs.

The scheduled Stage 6 workflow now invokes the builder before Stage 7 and persists the resulting snapshot on the `signals` branch. If no frozen basis file exists at `signals/cpp_runtime/shadow_risk_basis.daily_swing.v1.json`, the workflow passes an empty basis and the builder emits an explicit `UNAVAILABLE` snapshot. No implicit basis is created.

## Current stage disposition

The builder and contract are implementation work, not a Stage 7 PASS. Acceptance still requires a valid frozen basis, complete costed persistent history, open-position mark-to-market coverage, independent C++/CI evidence, and an upstream Stage 6 calibration gate that is no longer `NOT_CALIBRATED`.


### Entry-time provenance

The Shadow candidate registry now records `entry_fill_time_ms` when a proxy fill is first observed. Legacy filled pending candidates without this timestamp remain non-markable and must keep the snapshot `UNAVAILABLE`; no timestamp is inferred from decision time or later candles.


### Entry-NAV reconstruction guard

Each closed Shadow outcome now carries `entry_fill_time_ms`, sourced from the first recorded resolution candle. Legacy outcomes are upgraded only when that timestamp is present in their stored `resolution_bars`; no decision-time substitution is permitted.

The snapshot builder rejects any overlap between closed-position intervals with `OVERLAPPING_SHADOW_OUTCOMES_ENTRY_NAV_UNAVAILABLE`. Without a recorded NAV at each entry, applying the current NAV at close would misstate the position's risk amount whenever another position closes while it is open. Non-overlapping intervals permit sequential reconstruction; overlapping intervals remain unavailable until explicit entry-NAV/risk-unit provenance or a correct portfolio mark-to-market ledger is implemented.
