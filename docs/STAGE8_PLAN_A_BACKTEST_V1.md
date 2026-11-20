# STAGE 8 — PLAN A BACKTEST V1 (C++)

**Specification:** V18.2  
**Branch:** `feat/cpp-stage8-backtest-v1`  
**Status:** ENGINEERING IMPLEMENTATION IN PROGRESS; STRATEGY GATE NOT EVALUATED  
**Release:** Not approved; no merge to `main` in this change set.

## Objective

Create a deterministic C++ engine to replay pre-registered Plan A LRT and NMT candidate events over chronological OHLC bars, report separate OOS results, and refuse to claim a strategy pass when required evidence is absent.

## L1 — Data

The engine accepts a versioned input contract with:
- Chronological OHLC bars keyed by canonical symbol.
- Independently registered LRT/NMT candidate events.
- Signal time, registration time, frozen parameter hash, entry reference, stop, target and holding horizon.
- Explicit entry/exit fee, entry/exit slippage, funding-cost assumptions and risk fraction.

The engine never upgrades PROXY input to REAL. Candidate class is retained in the report. The current input format does not itself prove OHLC source provenance; a production dataset manifest and source hashes remain required before any statistical acceptance.

### Repository evidence audit (2026-11-20)

The `signals` branch contains:
- `cpp_runtime/daily_outcome_ledger.v1.json`: two closed outcomes, both `PROXY`; fee/funding costs are `UNAVAILABLE`; execution is `NOT_EXECUTED`.
- `cpp_runtime/outcome_ledger.v1.json`: `EMPTY`.
- `cpp_runtime/performance-okx-cpp-1795052817897.json`: `NOT_CALCULATED`, trade_count 0, reason `NO_STRATEGY_ENGINE_OR_EXECUTED_TRADES_IN_STAGE_1`.
- Five recent live-run history CSV snapshots, not a six-month historical OHLCV/candidate archive.

Therefore those artifacts are useful operational evidence, but they are not valid REAL OOS evidence for Gate A.

## L2 — C++ Compute

V1 implementation:
- C++20 header-only replay core, CLI JSON input/output and CMake/CTest integration.
- Calendar-based 6-month training / 2-month test / 1-month step folds.
- Candidate registration must predate the relevant test window.
- Signal execution begins at the next available bar after signal time.
- LRT and NMT metrics remain separate.
- Same-bar stop/target collision resolves conservatively as stop-first.
- Fees, slippage and conservative funding costs are deducted before net R.
- Win-rate Wilson 95% interval, net PF, net expectancy, drawdown and daily Sharpe are emitted where calculable.
- No execution permission or actionable trade output.

## L3 — Delivery

The report contract is designed for a Telegram-only status summary after real input and report validation. No Stage 8 Telegram delivery is claimed by this v1 engineering slice. CI output is engineering evidence, not user delivery.

## Numeric acceptance criteria

### Engineering acceptance
1. C++20 Release build succeeds on the actual GitHub Actions runner.
2. Full CTest suite passes with nonzero test collection.
3. Input schema compiles and rejects malformed inputs.
4. Deterministic tests cover path separation, chronological fold creation, registration-time guard, next-bar entry, fee/slippage/funding deduction, stop-first ambiguity, and non-actionable output.
5. Two consecutive Stage 8 workflow runs pass after the final code change.

### Strategy acceptance — Gate A (separate for LRT and NMT)
- LRT OOS win rate ≥55%.
- NMT OOS win rate ≥45%.
- Net PF ≥1.4.
- Max drawdown ≤20%.
- PBO <0.4.
- OOS results only; confidence intervals and sample counts required.
- Compare EMA Cross, RSI and Buy & Hold on identical data, costs and OOS windows.
- DSR, PBO and Brier/calibration diagnostics must be supplied or explicitly remain UNAVAILABLE; missing metrics cannot be treated as passing.

No strategy acceptance can be issued from synthetic fixtures, PROXY outcomes, missing costs, or an empty/short candidate archive.

## SLRP

### V1
- Assumption: historical pre-registered candidate events and their matching chronological OHLC bars can be supplied as a reproducible dataset.
- Current code: replay engine and contract added; actual Actions result pending.
- Strategy evidence: not evaluated.

### Diagnosis register
- D1 Data: current repository ledger has only two closed PROXY outcomes; fee/funding fields are unavailable; the REAL outcome ledger is empty; no six-month OHLCV/candidate archive was found on the inspected `signals` branch.
- D2 Assumption: the current live candidate stream cannot be assumed to represent historical candidate generation.
- D3 Implementation: pending actual C++ workflow result.
- D4 Calibration: DSR/PBO/Brier and baselines are not implemented by this v1.
- D5 Regime: not evaluated without a valid chronological dataset.
- D6 Expectations: a passing unit test is not a passing strategy gate.

### V2 / V3
NOT BUILT. V2/V3 require a measured V1 failure and a materially different assumption, not parameter tuning. No threshold relaxation is permitted.

### Escalation
If the final V1 workflow fails, fix only the evidenced implementation defect within the V1 budget. If engineering passes but real OOS evidence remains unavailable, record the D1 failure and design a separately reviewed data-reconstruction assumption before any V2 implementation.

### Budget
Maximum three versions under V18.2; no more than three rewrite cycles. No Gate A threshold changes.

## Five-question self-critique

1. Future data used? Candidate registration and next-bar rules are enforced; complete point-in-time source replay still needs validation.
2. Parameters tuned on test? No fitting is performed by this engine; the frozen parameter hash is recorded.
3. Costs included? Explicit inputs are deducted; actual costs remain UNAVAILABLE unless supplied by the dataset.
4. No-signal case reported? Yes, empty metrics remain null/zero and no actionable output is emitted.
5. Weakest assumption? Historical candidate events are available and truly pre-registered. The current repository evidence does not establish this.

## Current decision

`ENGINEERING_REPORT_ONLY`. Stage 8 is not PASS. Gate A is not evaluated. No performance or profitability claim is made.
