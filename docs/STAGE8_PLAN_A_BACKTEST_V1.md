# STAGE 8 — PLAN A BACKTEST V1 (C++)

**Specification:** V18.2  
**Branch:** `feat/stage8-gap-fill-audit-v1`  
**Status:** ENGINEERING CONTRACT PASSED ON COMMIT b6f0a15; LATEST PROVENANCE TEST CORRECTION AWAITS CI; STRATEGY GATE NOT EVALUATED  
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

The `signals` branch evidence inspected for this revision contains:
- `cpp_runtime/daily_outcome_ledger.v1.json`: 5 closed outcomes, all `PROXY`; fee/funding/slippage costs are `UNAVAILABLE`; execution is `NOT_EXECUTED`.
- `cpp_runtime/outcome_ledger.v1.json`: `EMPTY`.
- `cpp_runtime/shadow_candidate_registry.v1.json`: 10 candidates, all `PROXY`; 5 resolved, 4 rejected, and 1 pending.
- `cpp_runtime/performance-okx-cpp-1795257048838.json`: `NOT_CALCULATED`, trade_count 0, reason `NO_STRATEGY_ENGINE_OR_EXECUTED_TRADES_IN_STAGE_1`.
- Recent history CSV snapshots exist, but they are not a six-month historical OHLCV archive or a point-in-time reconstruction of all LRT/NMT candidate events.

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
- Win-rate Wilson 95% interval, net PF and net expectancy are emitted where calculable. Portfolio drawdown and Sharpe remain null/UNAVAILABLE until a portfolio-level event ledger exists.
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
- Current code: replay engine and contract added; latest Stage 8 contract workflow for commit `b6f0a150fbcd824b5ec7818306417f13743bc0e3` passed all steps. A subsequent test-only provenance correction is committed separately and must receive its own CI confirmation.
- Strategy evidence: not evaluated.

### Diagnosis register
- D1 Data: the inspected daily ledger has 5 closed PROXY outcomes; fee/funding/slippage fields are unavailable; the REAL outcome ledger is empty; no six-month OHLCV/candidate archive was found on the inspected `signals` branch.
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

## V1 Audit Fix — Stop-gap execution and input validation

- Stop-loss gaps are now filled at the bar open (worse price) and labeled `STOP_GAP`, not optimistically at the stop level.
- Parameter hashes must be 64 lowercase hexadecimal characters, not just 64 arbitrary characters.
- Slippage rates of 100% or more are rejected because they can produce non-positive fills.
- Funding remains a duration-based approximation; exact funding timestamp/event data is not supplied by this contract and must remain explicitly PROXY/unavailable.
- Regression tests cover gap-stop fill math, invalid hashes, and invalid slippage.

## Runtime contract hardening

The CLI rejects unsupported `schema_version` values before consuming any input fields. The test workflow asserts fail-closed behavior for an unsupported version. The rolling 6-month window is a warm-up/context window only; v1 does not train or fit parameters, and the 6-month data is not used by a model. DSR, PBO, Brier and baselines remain UNAVAILABLE.


## V1 Audit Fix — Portfolio metric integrity

A code audit found that the original v1 implementation compounded completed trades in exit-time order and grouped their returns by exit date. That is not a valid portfolio equity curve when positions overlap: it omits concurrent exposure, capital allocation, mark-to-market losses during open positions, and portfolio-level constraints. Consequently, the reported drawdown and Sharpe could be materially misleading.

The implementation now deliberately withholds both metrics (null) for LRT and NMT, and the report states the missing event-driven ledger explicitly. This is a fail-closed correction, not a strategy improvement or a Gate A pass. Win rate, Wilson interval, per-trade net PF and expectancy remain trade-level descriptive statistics and must not be interpreted as portfolio performance.

Funding remains a duration-based proxy (ceil(holding_hours / 8)) rather than exchange funding-event replay. It is not sufficient for Gate A without timestamp-aligned funding history. The engine also has no portfolio capital allocator, concurrency cap, cross-symbol correlation control, or mark-to-market equity accounting. The `risk_fraction` input is validated but not applied to portfolio sizing or equity; the report limitation makes this explicit. Those are explicit blockers for a future separately approved portfolio-validation implementation.


## V1 Audit Fix — Synthetic fixture provenance

A review found that synthetic unit-test bars had been paired with candidate records labeled `REAL`. Although the dataset ID identified the fixture as synthetic and the report warned that bar provenance was unverified, the fixture labels were internally inconsistent. All synthetic test candidates are now labeled `PROXY`, and the test asserts that the resulting report remains `PROXY_CANDIDATES`. This prevents tests from accidentally presenting fabricated market data as real evidence.
