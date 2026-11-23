# MASTER SOURCE V20.0
## Unified Crypto Futures Signal System — VTM Constitution

**Document ID:** CFSS-MASTER-SOURCE  
**Version:** 20.0  
**Status:** OWNER-DIRECTED CANONICAL REPLACEMENT  
**Effective event:** Commit of this document to the project repository  
**Supersedes:** V19.0 and all conflicting prior strategy, timeframe, delivery, and implementation requirements  
**Primary strategy:** VTM — Volume-Triggered Momentum  
**Research lineage:** Apex-Synergy research; the former six-factor Apex V1 is rejected and is not an active engine  
**Operating timeframe:** 1D only  
**User delivery:** Telegram only  
**Trading mode:** Manual decision support only

---

# 0. AUTHORITY, PURPOSE, AND GOVERNANCE

## 0.1. Purpose

This document is the single controlling constitution for the next version of the project. It replaces the multi-path architecture with one deliberately narrow research and production path: daily Volume-Triggered Momentum (VTM).

The objective is not to produce frequent alerts or make a backtest look attractive. The objective is to establish whether a simple, frozen, volume-led daily momentum hypothesis survives point-in-time universe construction, realistic costs, walk-forward testing, and independent statistical controls.

A strategy is not validated because it has a plausible explanation, a successful unit test, a positive in-sample result, or a completed workflow. Production release requires the gates in this document to pass on reproducible evidence.

## 0.2. Binding precedence

1. This V20.0 document controls over V19.0, V18.2, V18.3, and earlier project documents wherever they conflict.
2. Explicit later owner decisions may amend this constitution only through a recorded versioned amendment.
3. Safety and manual-only trading boundaries are absolute.
4. No acceptance threshold may be weakened to increase signal count or obtain a PASS.
5. If a required definition, source, dependency pin, or data field is unresolved, the affected test or release is BLOCKED. It must not be silently guessed.
6. Archived documents are historical evidence only. Their strategies and workflows do not remain active merely because their code is still present.
7. A repository commit proves that files were committed. It does not prove a strategy, data pipeline, Telegram delivery, or production system is operational.

## 0.3. Evidence labels

Use these labels in source manifests, test output, and internal records:

- `OWNER_DIRECTED`: explicitly required by the owner.
- `MEASURED`: calculated from identified source data and a reproducible method.
- `PASS` / `FAIL`: acceptance result with inspectable evidence.
- `PROXY`: an approximation, not the required real measurement.
- `UNAVAILABLE`: required data or capability is not available.
- `NOT_TESTED`: no test has been executed.
- `NOT_VALIDATED`: one or more validation gates failed.
- `BLOCKED`: execution must not proceed until a named prerequisite is resolved.
- `NOT_CALIBRATED`: probability/confidence has not passed calibration.

No proxy may be represented as exact historical truth.

## 0.4. Change control

Every amendment to a frozen strategy parameter, risk threshold, data definition, statistical gate, universe rule, execution assumption, or delivery contract must record: decision ID, old value, new value, reason, evidence, affected components, tests, owner approval, commit, and effective version.

---

# 1. ARCHITECTURE AND SCOPE

## 1.1. One timeframe

The only strategy, feature, regime, entry, exit, validation, and signal timeframe is **1D**.

The following are removed from the active V20 scope:

- Scalping and intraday trading.
- 1m, 5m, 15m, 30m, 1h, and 4h strategy logic.
- Multi-timeframe confirmation.
- Intraday entry optimization.
- LRT/NMT parallel engines.
- Plan A/B/C/H multi-path operation.
- Web application, dashboard, and email delivery.

No lower timeframe may be introduced as a hidden confirmation or execution dependency. Binance daily candles use UTC boundaries. A signal is evaluated only after the relevant UTC daily candle has closed.

## 1.2. Active engine

The only active strategy candidate is **VTM — Volume-Triggered Momentum**.

Apex-Synergy is retained as the research lineage that produced the abnormal-volume observation. The rejected six-factor Apex V1 composite is not part of the active VTM engine and must not be blended into VTM.

VTM status is:

- Research strategy: ACTIVE.
- Production strategy: NOT VALIDATED until all release gates pass.
- Live signal publication: prohibited before the production release gate passes.

## 1.3. Languages and computation

- **Python:** research, historical backtesting, statistical validation, data inspection, and reproducible research tooling. Use vectorbt or a demonstrably equivalent open-source engine where appropriate.
- **C++:** authoritative production implementation for signal computation, risk checks, signal state, and Telegram publication.
- Python research output must never directly become a production signal or bypass the C++ production decision path.
- Pin all dependencies. No floating Git branch, unpinned package, or silently changing dependency is permitted in a reproducible validation run.

The exact Python package versions, C++ compiler, C++ standard, and build configuration must be recorded in the run manifest after verification against the actual GitHub Actions runner.

## 1.4. Zero-cost infrastructure and data

Permitted baseline:

- GitHub Actions free-tier execution, subject to actual account and runner limits.
- Binance Vision public historical market-data archives.
- Open-source Python and C++ dependencies.
- Telegram Bot API for outbound notifications.

No paid data service, paid compute, paid database, paid charting service, or paid notification service is a production dependency.

Binance Vision is the defined V20 data source. If the required dataset or endpoint is unavailable, the system must stop or mark the field UNAVAILABLE. It must not silently substitute another provider or fabricate continuity.

The project must record actual GitHub Actions runtime, artifact retention, and free-tier constraints. “Zero-cost” is an architectural requirement, not a claim that external platforms will provide unlimited free capacity.

## 1.5. Three operational layers

Every V20 stage must satisfy all three layers:

**L1 — DATA**
- Acquire Binance Vision daily OHLCV and required public derivatives data when available.
- Construct the point-in-time instrument universe.
- Validate timestamps, symbol identity, candle completeness, duplicates, gaps, checksums, and provenance.
- Preserve raw inputs, normalized data, manifests, and source hashes.

**L2 — COMPUTE**
- Calculate the frozen VTM conditions.
- Apply the BTC daily ADX regime gate.
- Calculate ATR-based stop and stop-based position size.
- Apply volatility targeting and portfolio risk controls.
- Run walk-forward, PBO, DSR, and cost-aware performance calculations.
- Produce immutable signal and outcome records.

**L3 — DELIVERY**
- Publish eligible signals through Telegram only.
- Publish outcome updates through Telegram only.
- Maintain deduplication, message identity, retry safety, and delivery evidence.
- Keep internal diagnostics and attribution silent in the channel.

A stage cannot PASS by implementing only data acquisition or only backtesting.

## 1.6. Manual-only trading boundary

The system is read-only decision support.

It must never:
- Connect to a user's exchange account.
- Request, store, or use private trading API keys.
- Read private balances or positions.
- Place, modify, or cancel orders.
- Execute trades or copy another trader.
- Claim that a Telegram signal is an executed trade.

The user independently decides whether and how to trade.

---

# 2. REJECTED STRATEGIES — PERMANENTLY QUARANTINED

The following strategies are rejected for V20. They must not be re-enabled, blended into VTM, or quietly reintroduced under a renamed module. Reconsideration requires a new owner-approved version and new independent evidence.

## 2.1. LRT — Liquidity Reversion Trading

**Decision:** REJECTED.

Reason:
- The required historical order-book evidence was unavailable for the tested research design.
- The 1D LRT result was weak and statistically rejected.

Recorded research result from the available LRT 1D artifact:
- OOS trades: 31.
- Win rate: 32.258%.
- Profit Factor: 0.7814.
- PBO: 0.7286.
- DSR Z-score: -2.0164.
- Sharpe: 0.0336.
- Net return: 0.078% in the reported research run.
- Research status: `RESEARCH_GRADE_PROXY`.
- Validation status: `NOT_VALIDATED`.

The reported result does not establish that all possible liquidity-reversion systems are universally invalid. It establishes that the tested LRT implementation failed its stated validation requirements and is rejected from this project.

## 2.2. NMT — Narrative Momentum Trading

**Decision:** REJECTED.

Recorded NMT 1D research result:
- OOS trades: 721.
- Win rate: 42.718%.
- Profit Factor: 1.1643.
- Max Drawdown: -18.68%.
- Sharpe: 0.2766.
- PBO: 0.7143.
- DSR Z-score: -1.6896.
- Net return: 5.946% in the reported research run.
- Research status: `RESEARCH_ONLY`.
- Validation status: `NOT_VALIDATED`.

The win-rate, PBO, DSR, PF, and Sharpe results fail the V20 validation direction. NMT is quarantined.

## 2.3. Apex-Synergy six-factor composite V1

**Decision:** REJECTED as an active strategy engine.

Recorded composite research result:
- OOS trades: 388.
- Win rate: 46.392%.
- Profit Factor: 1.4202.
- Max Drawdown: -1.921%.
- Sharpe: 1.4588.
- PBO: 0.1571.
- DSR probability: 0.7281.
- DSR Z-score: 0.6069.
- Validation status: `NOT_VALIDATED`.

The composite did not pass the complete acceptance criteria. Its DSR Z-score was below 1.0 and its win rate did not meet the former gate. The Kelly diagnostic ended with a zero risk budget and zero Kelly-managed OOS trades. The composite therefore cannot be treated as a production-ready strategy.

The abnormal-volume ablation recorded:
- 471 trades.
- Win rate: 50.106%.
- Profit Factor: 1.6234.
- Sharpe: 2.1276.
- Max Drawdown: -1.763%.

This ablation is a **post-hoc diagnostic**, not independent proof that abnormal volume is profitable. It may contain selection bias. It motivates the VTM hypothesis but does not validate VTM. VTM must pass a fresh, frozen, independently registered test.

## 2.4. Evidence integrity

The metrics above are copied from the available research artifacts and are not guarantees of future performance. The artifacts used 25 symbols and their stated research periods and assumptions. Their scope and limitations must remain attached to any internal use of the numbers.

---

# 3. ACTIVE STRATEGY — VTM

## 3.1. Hypothesis

**Abnormal Volume + Candle Acceptance + Break of Structure (BOS) + a qualifying BTC trend regime may identify persistent daily momentum.**

The hypothesis is falsifiable. It is rejected if the frozen strategy fails the OOS statistical gates, becomes unprofitable after realistic costs, or fails robustness across walk-forward periods and the point-in-time universe.

## 3.2. Five frozen core parameters

These five values are immutable for the VTM V1 candidate:

| Parameter | Frozen value |
|---|---:|
| Volume Lookback | 20 completed daily candles |
| Volume Multiplier | 2.0x |
| Body Ratio | strictly greater than 0.60 |
| Breakout Lookback | 10 completed daily candles |
| ATR Stop Multiplier | 2.0x |

The ATR period is additionally fixed at **14 days**. It is a specified calculation period, not permission to tune the five core parameters.

No optimization may change these values for the VTM V1 acceptance run. Any alternative value belongs to a separately registered research candidate and must not replace V1 after inspecting its OOS results.

## 3.3. Signal definitions

All conditions use completed UTC 1D candles only. The parameter values in Section 3.2 are LOCKED; the calculation conventions below are not all owner-specified and must not be silently promoted to locked rules.

### A. Abnormal Volume

The 20-day lookback and 2.0x multiplier are locked. The exact volume field for this VTM trigger is OPEN.

- Proposed candidate: Binance Vision Quote Asset Volume, denominated in the quote asset.
- This candidate is not owner-approved merely because it is used by the separate 30-day Universe liquidity screen.
- The final backtest is blocked until the VTM trigger volume field and unit are explicitly frozen.
- Whatever field is approved, the mean must use the 20 immediately preceding completed daily observations and exclude the current signal candle.
- Missing, duplicated, invalid, or incomplete observations make the symbol ineligible for that date.

### B. Candle Acceptance

The Body Ratio threshold is locked at strictly greater than 0.60. The exact formula is OPEN.

Proposed candidate formula, pending owner approval:

`BodyRatio = abs(Close - Open) / (High - Low)`

For the documented long setup, a bullish candle (Close > Open) is required. A zero-range candle must be invalid, not assigned an artificial ratio. These calculation conventions remain proposed until explicitly approved.

### C. Break of Structure

The Breakout Lookback is locked at 10 completed daily candles. The comparison convention is OPEN.

Proposed candidate for the long setup, pending owner approval:

`Close[t] > max(High[t-10 ... t-1])`

This is a completed-close breakout, excludes the current candle from the reference range, and does not count a wick-only penetration. Whether this or an intraday high breach is the controlling BOS definition must be approved before the final backtest.

### D. BTC Trend Regime

The regime threshold and period are owner-locked:

`BTC 1D ADX(14) >= 20`

The exact ADX smoothing/implementation convention and missing-data policy must be pinned and parity-tested before the final run. The regime must use only completed daily BTC candles available at the decision timestamp. Missing or invalid BTC data means UNKNOWN and fails closed.

### E. Direction

The currently specified entry conditions are LONG. VTM V1 must not create short signals by assuming mirrored rules. Short-side logic remains disabled unless separately approved and validated.

## 3.4. Entry

A qualifying signal is identified after the UTC daily candle closes.

- Planned entry: next UTC daily candle open.
- The signal is not executable if the next daily open is missing or invalid.
- The signal record must preserve signal timestamp, planned entry timestamp, planned entry price, and the source candle identifiers.
- A gap between the signal close and next open must not be hidden or replaced with the signal close.

## 3.5. Stop Loss

The ATR period (14) and stop multiplier (2.0x) are specified by the owner. The precise ATR algorithm, reference timestamp, and stop-price formula are not fully specified and remain OPEN.

Proposed candidate implementation, pending owner approval:

- Calculate ATR(14) through the completed signal day using Wilder smoothing.
- For a long setup, set the initial stop to planned next-day entry minus 2.0 times ATR(14) from the signal day.

This is a proposed calculation convention, not an approved fact. The exact stop reference, gap-through-stop fill, and ambiguous daily-bar handling must be frozen before the final backtest. No optimistic fill convention is permitted.

## 3.6. Exit rules — VTM V1

Only two exit mechanisms are authorized:

1. Stop Loss.
2. Time-Stop after 10 daily bars.

VTM V1 has no Take Profit, partial Take Profit, trailing stop, discretionary indicator exit, or lower-timeframe exit.

The exact Time-Stop execution convention is OPEN.

- Proposed candidate: exit at the close of the tenth completed daily candle counted from the entry day.
- Proposed conservative conflict rule: if the stop is touched on the same daily bar as the Time-Stop, Stop Loss takes precedence.
- These execution conventions require explicit approval before the final backtest.

TP status: `TP_DISABLED` for VTM V1. The Telegram signal must show `TP: DISABLED (V1)`, not an invented target. An outcome update can report SL or TIME_STOP only. A TP outcome is impossible under V1 and must not be reported.

## 3.7. Signal rejection conditions

Do not publish a candidate if:
- Any required candle or feature is missing, stale, duplicated, or invalid.
- The symbol is not in the point-in-time universe for that date.
- The BTC ADX regime is below 20 or UNKNOWN.
- The volume, candle acceptance, or BOS condition fails.
- Entry or stop cannot be calculated without an assumption.
- Position size is zero, undefined, or violates risk limits.
- Costs cannot be estimated to the registered minimum standard.
- The strategy or data release gate is not PASS.

A zero-signal day is a valid outcome. No signal quota exists.

---

# 4. POINT-IN-TIME UNIVERSE AND DATA INTEGRITY

## 4.1. Point-in-Time requirement

Every historical test must use the exact eligible universe as it existed on each historical date. The universe must not be reconstructed from today's surviving symbols.

For each date `t`, a contract is eligible only when all conditions are evidenced:

1. It is a Binance USD-M perpetual contract active on date `t`.
2. It has valid daily market data for date `t`.
3. It has the required complete 30 prior daily observations.
4. Its arithmetic mean Quote Asset Volume over those 30 prior completed days is strictly greater than **10,000,000 USDT**.
5. Its instrument identity and contract type are supported by historical evidence, not only by a present-day symbol name.

The current date is excluded from the 30-day liquidity average.

## 4.2. Historical listing and contract status

A daily Kline row or a USDT suffix alone does not prove that a contract was officially listed, perpetual, or active on that historical date.

The universe builder must preserve the evidence used to establish historical contract identity and active dates. If Binance Vision archives do not provide enough historical instrument metadata to prove the exact listing/contract lifecycle, the affected membership must be labelled `PROXY`.

A proxy universe is useful for exploration but does **not** satisfy the exact Point-in-Time Universe acceptance criterion. The backtest must remain BLOCKED or explicitly be reported as a proxy research run until the exact historical contract status is evidenced.

## 4.3. Daily universe outputs

At minimum, produce versioned artifacts:

- `universe_daily.json`
- `universe_daily.csv`
- `universe_membership.csv`
- `monthly_universe_counts.csv`
- `universe_manifest.json`
- `download_failures.json` when applicable

Each membership row must include date, canonical instrument ID, symbol, contract type, quote asset, 30-day mean quote volume, active-status evidence, source archive, checksum status, and evidence classification.

A missing archive, checksum mismatch, incomplete history, or unexplained download failure must not be silently ignored. The affected run is PARTIAL or FAIL.

## 4.4. Data causality and survivorship controls

- Use UTC timestamps and UTC daily boundaries.
- Use only information available by the relevant decision timestamp.
- Exclude current-day volume from its own rolling baseline.
- Exclude current-day high from the prior-ten-day breakout reference.
- Do not use future listing, delisting, symbol rename, or contract metadata.
- Preserve delisted and expired historical instruments when they were eligible at the time.
- Do not backfill missing candles with fabricated prices or volumes.
- Detect duplicate bars and inconsistent OHLC relationships.
- Preserve raw files, SHA-256 checksums, normalized data hashes, code commit, and run manifest.
- Deduplicate overlapping walk-forward OOS trades by canonical trade identity before pooled metrics are calculated.

---

# 5. VALIDATION CONSTITUTION

## 5.1. Immutable acceptance gates

A VTM candidate cannot be released unless all required gates pass:

| Metric / Control | Acceptance |
|---|---:|
| PBO | strictly below 0.40 |
| DSR Z-score | strictly greater than 1.0 |
| Walk-Forward | train 6 months / test 2 months / step 1 month |
| Point-in-Time Universe | exact, not PROXY |
| Data integrity | no unresolved critical gaps or leakage |
| Costs | included and documented |
| Strategy parameters | frozen and hash-verified |
| Trial registry | complete and immutable |

Passing PBO or DSR alone does not establish profitability. Win rate, Profit Factor, net expectancy, drawdown, trade count, regime behavior, and baseline comparison must also be reported. The owner may impose additional release gates; none of these minimum gates may be relaxed by implementation.

## 5.2. Walk-Forward

Use:
- Training window: 6 months.
- Test window: 2 months.
- Step: 1 month.

The training period may select only from a pre-registered candidate matrix. Each test window remains unseen during that fold's selection. All fold boundaries, selected candidate IDs, data hashes, and OOS trade IDs must be recorded.

Overlapping test windows must not inflate the pooled trade count. Use one canonical OOS aggregation policy and deduplicate repeated trade identities.

## 5.3. PBO — Trial Matrix is mandatory

PBO must never be reported for a single strategy configuration as though it measured backtest overfitting.

The PBO calculation requires a pre-registered, reproducible **three-dimensional Trial Matrix**. The matrix must contain multiple valid candidate configurations and a complete record of all tested candidates, including failed and abandoned trials.

Important separation:

- The production VTM V1 candidate remains frozen at the five core values in Section 3.2.
- The three-dimensional matrix is a validation research registry. It is not permission to mutate the frozen VTM V1 candidate after OOS results are observed.
- Matrix axes, candidate values, selection objective, partitioning method, and package version must be frozen before the final validation run.
- No candidate may be removed because its result is unattractive.
- If a valid three-dimensional matrix has not been pre-registered, PBO is `UNAVAILABLE` and the acceptance gate is BLOCKED.

The exact three matrix axes and candidate values are not defined by this document. They must be registered and frozen before the final backtest. They must not be invented during execution.

## 5.4. DSR — Deflated Sharpe Ratio

- DSR must account for the full number of registered strategy trials and selection attempts.
- The reported primary statistic is the DSR Z-score.
- Acceptance requires `DSR_Z > 1.0`.
- Record the estimator, return frequency, sample size, skewness, kurtosis, trial count, and implementation version.
- Do not substitute ordinary Sharpe, DSR probability, or a p-value for DSR Z-score.
- If the trial registry is incomplete or the method cannot be reproduced, DSR is UNAVAILABLE and the gate is BLOCKED.

## 5.5. backtest-guard dependency

The validation environment must use the `backtest-guard` package at an exact, immutable Git commit.

The commit SHA was not supplied in the V20 owner instruction and is not established by the current repository evidence. Therefore:

- `BACKTEST_GUARD_COMMIT = UNRESOLVED`.
- Do not install from an unpinned branch, tag, or latest release.
- Do not invent a commit SHA.
- Verify repository identity, package API, license, dependency tree, and reproducibility before use.
- The final PBO/DSR acceptance run is BLOCKED until the exact commit is registered and verified.

If the package cannot be verified or installed within the zero-cost/open-source constraints, report the dependency as BLOCKED and request an owner-approved alternative. Do not silently replace the required tool.

## 5.6. Cost model

Every reported performance result must be net of:
- Trading fees.
- Spread.
- Slippage.
- Funding payments/receipts for the actual holding interval.

The fee rate, whether it is per side or round trip, the spread model, slippage model, funding source, funding timestamp alignment, and missing-data policy must be frozen in the run manifest before the final test.

No VTM-specific complete cost schedule has yet been approved in this constitution. A backtest that omits a required cost component must be labelled `INCOMPLETE_COST_MODEL` and cannot PASS the production validation gate. Do not reuse costs from LRT/NMT experiments without explicit approval.

## 5.7. Required performance report

For the VTM candidate and every registered comparison, report at minimum:

- OOS trade count.
- Win rate.
- Profit Factor.
- Net expectancy per trade.
- Net return.
- Maximum drawdown.
- Sharpe.
- DSR Z-score.
- PBO.
- Average win and average loss.
- Holding period.
- Stop-loss versus time-stop exit counts.
- Costs by component.
- Monthly and walk-forward fold results.
- Results split by BTC Trend/Chop/UNKNOWN diagnostic state.
- Point-in-time universe size by month.
- Data coverage and missingness.
- Baseline comparison.
- Confidence intervals where statistically appropriate.

Trend/Chop reporting is diagnostic only. VTM eligibility itself remains governed by BTC ADX14 >=20.

## 5.8. Baselines and trial integrity

Compare VTM with pre-registered simple baselines using the same point-in-time universe, dates, costs, and risk constraints. Baseline identities and calculation rules must be fixed before the final run.

Maintain an immutable trial registry. Any research experiment, parameter sweep, strategy variant, or post-hoc diagnostic that informed selection must be recorded so DSR and PBO do not undercount the search process.

---

# 6. RISK MANAGEMENT

## 6.1. Volatility Targeting

The portfolio-level annualized volatility target is **10%**.

This is a target, not a guarantee and not a statement that realized volatility will remain at 10%.

The calculation must use daily strategy equity returns and a documented annualization convention. The realized-volatility lookback window, rebalance timing, gross-exposure cap, and behavior when volatility is zero or unavailable must be frozen before the final backtest. These values are not specified here and must not be guessed.

## 6.2. Stop-based sizing

Trade quantity is determined from the distance between planned entry and initial stop, using a fixed cash risk budget:

`Quantity = FixedTradeRiskBudget / abs(EntryPrice - InitialStop)`

The final quantity must also respect:
- Available and documented notional assumptions.
- Volatility-target exposure scaling.
- Maximum gross exposure once owner-approved.
- Liquidity and market impact constraints.
- Fees, spread, slippage, and funding.
- Minimum order/contract precision only for signal calculation, never for order placement.

The fixed trade-risk budget or risk percentage has not been supplied. It must be frozen before the final test. Do not invent a risk percentage or account equity.

Portfolio volatility targeting and stop-based sizing are separate controls. The final quantity is the more conservative result after both controls are applied.

## 6.3. Kelly prohibition

Kelly Criterion is **PROHIBITED** for V20 V1.

It may not be used for sizing, exposure, risk budget, ranking, or any hidden fallback until at least **300 valid, unique, closed, genuinely out-of-sample trades** have been recorded and the owner explicitly approves a separate review.

The 300-trade requirement is a necessary condition, not automatic permission. In-sample trades, duplicated overlapping OOS trades, simulated duplicates, and trades selected after seeing their outcomes do not count.

Until then, Kelly-related code must be disabled from the VTM production path. Any historical Kelly artifacts are diagnostic only.

## 6.4. Fail-closed risk rules

If the stop, risk budget, volatility estimate, exposure cap, or cost estimate is missing or invalid, position size is zero and no signal is published.

No signal may bypass risk controls because its setup score is high.

---

# 7. TELEGRAM DELIVERY CONTRACT

## 7.1. Only two user-facing message types

The Telegram channel permits exactly two message categories:

1. **NEW_SIGNAL**
2. **SIGNAL_OUTCOME_UPDATE**

No daily report, weekly report, market recap, system-health message, progress message, or attribution message may be sent to the channel.

Internal learning, attribution, diagnostics, and operational monitoring are stored silently in repository artifacts or logs.

## 7.2. NEW_SIGNAL format

A new-signal message must contain:
- Chart image generated from validated 1D source candles.
- Symbol and direction.
- Signal date and planned entry date.
- VTM hypothesis summary.
- Falsification/invalidating condition.
- Planned Entry.
- Initial Stop Loss.
- `TP: DISABLED (V1)`.
- Planned Time-Stop: 10 completed daily candles.
- Position-risk and confidence labels only when their calculation is supported.
- Unique signal ID.

Do not display an invented target price. Do not describe an uncalibrated score as a probability.

## 7.3. SIGNAL_OUTCOME_UPDATE format

An outcome update is sent only after a signal is closed by:
- `STOP_LOSS`, or
- `TIME_STOP`.

It includes signal ID, exit reason, exit timestamp, exit price, net percentage return after registered costs, and final outcome status.

For VTM V1, `TAKE_PROFIT` is not a valid outcome reason because TP is disabled.

## 7.4. Delivery reliability

- Use stable signal IDs and idempotency keys.
- Never publish the same signal twice because of a retry.
- A delivery failure must not alter the underlying strategy result.
- Store message attempt, Telegram response, timestamp, and delivery state internally.
- Do not send a third category of message to explain delivery failures.
- Never send a signal before the strategy and data release gates pass.

---

# 8. AUTOMATION AND REPOSITORY OPERATIONS

## 8.1. Scheduling

GitHub Actions is the zero-cost automation target. The final schedule must be selected based on daily candle closure, data publication latency, runner limits, and Telegram delivery requirements.

The production signal cycle must not run on an incomplete UTC daily candle. Scheduled execution frequency is not permission to evaluate intraday signals.

## 8.2. Reproducible artifacts

Each research or production run must record:
- V20 document version and hash.
- Source-code commit.
- Workflow run ID.
- Python and C++ toolchain versions.
- Dependency lock and exact Git commit pins.
- Binance Vision source paths and checksums.
- Universe manifest and membership hash.
- Candle range and timestamp convention.
- Strategy parameter hash.
- Trial registry hash.
- Cost model.
- Risk configuration.
- Walk-forward boundaries.
- PBO and DSR implementation versions.
- Signal IDs and outcome IDs.

## 8.3. Legacy quarantine

Old LRT, NMT, multi-factor Apex, intraday, dashboard, and web-delivery code may remain in the repository for historical reproducibility. It is not active V20 production code.

Legacy workflows must be disabled, quarantined, or guarded from publishing to the active Telegram channel. A code path that can still publish an obsolete strategy's signals is a release blocker.

Do not delete historical evidence or old source files. Preserve them under `archive/` with their hashes and original provenance.

---

# 9. VTM RELEASE GATES

VTM is not production-approved until every required gate below is PASS:

1. **Universe Gate:** exact daily point-in-time perpetual universe; no PROXY membership in the acceptance run.
2. **Data Gate:** complete, checksum-verified, causally aligned daily OHLCV and required costs.
3. **Strategy Gate:** all five frozen parameters and the ATR14/regime/entry/exit definitions are hash-verified.
4. **Risk Gate:** 10% annual volatility target, stop-based sizing, fixed risk budget, lookback, and exposure cap are fully specified and tested.
5. **Validation Gate:** 6m/2m/1m walk-forward; PBO <0.40 from a valid three-dimensional trial matrix; DSR Z >1.0.
6. **Cost Gate:** fee, spread, slippage, and funding are included with no silent omissions.
7. **Safety Gate:** no account connection, private key, order endpoint, or execution capability exists in the production path.
8. **Delivery Gate:** real Telegram NEW_SIGNAL and SIGNAL_OUTCOME_UPDATE messages are tested without duplicate publication or any prohibited third message category.
9. **C++ Gate:** the production VTM decision path is implemented and tested in C++; Python remains research/backtest only.
10. **Owner Release Gate:** explicit owner approval after evidence review.

A failed gate means `NOT_VALIDATED` or `BLOCKED`, not partial production approval.

---

# 10. OPEN IMPLEMENTATION BLOCKERS BEFORE FINAL BACKTEST

The following items are intentionally not guessed:

| ID | Required item | Current status |
|---|---|---|
| B01 | Exact historical Binance perpetual listing/active-status evidence for every date | NOT VERIFIED; current Kline/name-based approximation is PROXY |
| B02 | Exact backtest-guard Git commit SHA and verified package identity | UNRESOLVED |
| B03 | Three axes and candidate values for the PBO Trial Matrix | UNRESOLVED |
| B04 | Complete VTM fee, spread, slippage, and funding model | UNRESOLVED |
| B05 | Fixed cash risk budget or risk percentage per trade | UNRESOLVED |
| B06 | Volatility-target realized-volatility lookback and rebalance rule | UNRESOLVED |
| B07 | Maximum gross exposure / leverage cap | UNRESOLVED |
| B08 | Exact handling for unavailable funding or cost observations | UNRESOLVED |
| B09 | Exact volume field and unit for the VTM 20-day trigger | OPEN; candidate Quote Asset Volume is not approved |
| B10 | Exact Body Ratio formula and zero-range handling | OPEN; formula in Section 3.3 is a proposal |
| B11 | BOS convention: completed close or intraday breach; equality/touch handling | OPEN; close-break in Section 3.3 is a proposal |
| B12 | ATR implementation, smoothing, timestamp, stop reference, and stop-fill convention | OPEN; Section 3.5 contains a proposal |
| B13 | Time-Stop execution time and same-bar stop/time-stop priority | OPEN; Section 3.6 contains proposals |
| B14 | Entry gap, validity window, and unfilled-entry treatment | OPEN |
| B15 | ADX14 smoothing/implementation convention | OPEN |


The final VTM backtest must not start until the blocking values and evidence sources are frozen in a pre-registration record. The five core strategy parameters in Section 3.2 are not open for tuning.

---

# 11. FINAL OPERATING RULES

1. One timeframe: 1D.
2. One active strategy candidate: VTM V1.
3. LRT, NMT, and six-factor Apex V1 remain rejected and quarantined.
4. Point-in-time universe is mandatory; a proxy is not a PASS.
5. The five VTM core parameters are frozen.
6. ATR14, BTC ADX14 >=20, next-day-open entry, 2x ATR stop, and 10-day time-stop are fixed V1 rules.
7. TP and trailing stop are disabled in V1.
8. PBO requires a pre-registered three-dimensional trial matrix.
9. PBO must be <0.40 and DSR Z must be >1.0.
10. Walk-forward is 6 months train / 2 months test / 1 month step.
11. Annualized volatility target is 10%; risk sizing is stop-based.
12. Kelly is prohibited until at least 300 unique valid OOS closed trades and a separate owner approval.
13. Python is research/backtest only; C++ owns production decisions.
14. Binance Vision and GitHub Actions are the defined zero-cost baseline.
15. Telegram is the only user-facing channel and permits only new signals and outcome updates.
16. Trading is manual only. No exchange account connection or order execution.
17. No fabricated data, missing-cost assumptions, false confidence, or false completion.
18. Stop at the validation/release gate. Do not begin a final backtest until the owner issues the explicit backtest instruction and all blockers are registered.

---

# 12. V20.0 CHANGE REGISTER

| ID | Change | Classification |
|---|---|---|
| V20-01 | Retire V19 multi-path architecture and adopt one VTM research/production path | OWNER_DIRECTED |
| V20-02 | Restrict all strategy logic to 1D | OWNER_DIRECTED |
| V20-03 | Quarantine LRT, NMT, and six-factor Apex V1 | OWNER_DIRECTED |
| V20-04 | Freeze VTM five core parameters and specified V1 rules | OWNER_DIRECTED |
| V20-05 | Require exact point-in-time universe | OWNER_DIRECTED |
| V20-06 | Set PBO <0.40 and DSR Z >1.0 | OWNER_DIRECTED |
| V20-07 | Require 6m/2m/1m walk-forward | OWNER_DIRECTED |
| V20-08 | Require pinned backtest-guard dependency | OWNER_DIRECTED |
| V20-09 | Set 10% annualized volatility target and stop-based sizing | OWNER_DIRECTED |
| V20-10 | Prohibit Kelly until 300 unique OOS closed trades and separate approval | OWNER_DIRECTED |
| V20-11 | Limit Telegram to NEW_SIGNAL and SIGNAL_OUTCOME_UPDATE | OWNER_DIRECTED |
| V20-12 | Resolve TP-disabled versus Telegram TP field by explicit `TP_DISABLED` representation | INTEGRATION_RULE |
| V20-13 | Preserve unresolved implementation inputs as blockers instead of guessing | INTEGRATION_RULE |

**Document end — MASTER_SOURCE_V20.0**
