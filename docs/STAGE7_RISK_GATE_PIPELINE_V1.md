# STAGE 7 — CONSENSUS, RISK AND SIGNAL GATE (V1)

**Specification:** V18.2 + explicitly accepted project amendments  
**Branch:** `integration/stage7-risk-gate-pipeline-v1`  
**Implementation status:** CI VALIDATION PENDING  
**Operational status:** FAIL-CLOSED / NOT RELEASE-ELIGIBLE  
**Production:** No merge or scheduled deployment performed by this change set.

## Objective

Connect the Stage 6 meta-cognition output to a deterministic C++ risk gate, preserve hard-veto precedence, and publish explicit reason codes through the existing Telegram-only report. The gate must not infer or request the user's account balance, leverage, positions, or actual account drawdown.

## Three layers

### L1 — Data
- Consume the exact versioned L1 market-data artifact used by Stage 4/5/6.
- Consume the matching liquidity-phase artifact and Stage 6 meta-cognition artifact.
- Verify run ID, scan ID, decision timestamp and SHA-256 provenance.
- The system does not know the user's actual account or portfolio. It does not invent these values.
- The shadow portfolio risk snapshot is currently UNAVAILABLE. No user-account data is used.

### L2 — Compute
- New C++20 `risk_gate_probe` consumes L1, liquidity and meta-cognition artifacts.
- Uses the existing fail-closed policy core.
- Rejects proxy data, unavailable liquidity, uncalibrated confidence, missing/non-positive EV, incomplete costs and missing internal shadow-risk snapshot.
- Preserves Golden Rule veto.
- Computes same-direction candidate correlation from aligned, closed 1h returns over a rolling 90-day window; requires at least 50 paired observations and blocks when correlation evidence is unavailable.
- Counts only other same-direction candidate symbols with Pearson correlation >0.70; blocks a candidate when three or more such peers already exist.
- Emits per-symbol and per-engine reason codes.
- `actionable=false` and `trade_execution_allowed=false` are invariant in every output.

### L3 — Delivery
- The Stage 7 artifact is persisted to the `signals` branch before notification.
- The existing C++ Telegram report now includes Stage 7 gate counts and shadow-risk snapshot status.
- If Stage 7 inputs fail validation while the Stage 6 artifact is available, the probe emits a schema-valid DEGRADED artifact with explicit block reasons so the daily report is not silently suppressed.
- Telegram outbox identity includes both Stage 6 and Stage 7 artifacts.
- Actual Telegram delivery for this new combined report is NOT VERIFIED until the updated workflow completes with a real Telegram message ID.

## Numeric engineering acceptance

1. C++20 Release build succeeds on GitHub Actions.
2. Full CTest passes with nonzero test collection.
3. Both Stage 7 JSON schemas compile and the produced artifact validates.
4. Provenance mismatch is rejected.
5. Tests cover no-candidate, PROXY block, missing risk snapshot, eligible manual-review-only state, prohibition on user-account data, immutable no-execution output, aligned correlation, and the four-exposure G5 boundary.
6. The production Stage 6 workflow produces and persists the Stage 7 artifact before Telegram delivery.
7. A Stage 7 input failure must still produce a DEGRADED, non-actionable report artifact; it must not silently suppress the Stage 6 daily report.
8. The combined Telegram report must return a real successful Telegram response and message ID; mock delivery is insufficient.

## Strategy / release acceptance

- A risk-policy engineering PASS is not a strategy PASS.
- Stage 6 calibration must be genuinely valid before any candidate can pass the calibration gate.
- The system-level shadow risk snapshot must be valid before a candidate can reach manual review.
- The user's real account state remains unknown and outside system scope.
- No output from this stage authorizes order execution.

## SLRP

### V1
- Assumption: Stage 6 artifacts contain enough provenance and per-engine fields for a deterministic final gate.
- Implementation: integrated C++ pipeline adapter, output contract, CMake target, tests, Stage 6 workflow step and Telegram report integration.
- CI and live delivery evidence: pending.

### Diagnosis
- D1 Data: current Stage 6 ledger/calibration is insufficient for calibrated confidence and net EV; shadow portfolio risk snapshot is UNAVAILABLE.
- D2 Assumption: no user account data can be inferred; the risk snapshot must describe only the system's own shadow portfolio.
- D3 Implementation: pending actual workflow outcome.
- D4 Calibration: current engine outputs remain NOT_CALIBRATED; no threshold changes are permitted.
- D5 Regime: no strategy release decision can be made from current proxy-only candidate scores.
- D6 Expectations: C++ unit tests and CI do not prove profitability or live Telegram delivery.

### V2 / V3
NOT BUILT. R11 prohibits alternatives until V1 has a measured failure and a specific diagnosis.

### Escalation
- CI failure: diagnose the exact compiler/test/schema failure under D3 and only then consider a materially different v2 assumption.
- Engineering PASS but no Telegram receipt: diagnose L3 delivery without changing signal logic.
- Calibration or shadow-risk data unavailable: remain fail-closed; do not manufacture a PASS or weaken thresholds.

### Budget
V1 only. Maximum three versions under the governing SLRP. No threshold relaxation.

## Self-critique

1. Future data used? Provenance and Stage 6 decision-time matching are enforced; only closed candles available by decision time enter the 90-day correlation window.
2. Parameters tuned on test? No strategy parameter fitting is performed here.
3. Costs included? The gate requires fee, slippage and funding fields before EV can pass.
4. No-signal case reported? Yes; each engine receives a deterministic reason code.
5. Weakest assumption? The internal shadow-risk snapshot is not yet generated from a sufficiently valid shadow portfolio history.

## Current decision

`ENGINEERING_PENDING`; `STRATEGY_RELEASE_BLOCKED`; `TELEGRAM_LIVE_DELIVERY_NOT_VERIFIED`. No BUY/SELL authorization and no execution.
