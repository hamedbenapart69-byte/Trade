UNIFIED CRYPTO FUTURES SIGNAL SYSTEM

MASTER SOURCE V19.0

سند مرجع یکپارچه معماری، مهندسی، داده، موتورهای تحلیلی، اعتبارسنجی آماری، اتوماسیون و تحویل سیگنال

Document ID: "CFSS-MASTER-SOURCE"
Document Version: "V19.0"
Document Type: Canonical Master Source Replacement Candidate
Language: English identifiers and technical schemas; Persian-first operational output
Status: "OWNER-ACCEPTED — CANONICAL ACTIVE SOURCE"
Supersedes: V18.2 and V18.3. V18.2 is retained as an archived historical source.

---

0. DOCUMENT AUTHORITY AND GOVERNANCE

0.1. Purpose

This document defines the complete target architecture and execution constitution of the Unified Crypto Futures Signal System.

It is intended to become the single authoritative project specification. It consolidates the compatible requirements of the previous master source, design audits, operational decisions, and later owner-directed amendments.

The system must discover, evaluate, validate, rank, and deliver independently qualified cryptocurrency futures opportunities.

The objective is not to maximize the number of alerts. The objective is to maximize the quality, reliability, timeliness, and independently validated value of opportunities while preserving strict statistical, operational, financial, and security controls.

0.2. Binding operating principles

The following principles are mandatory:

1. Zero-cost operation using genuinely free services and public data.
2. Backend-owned data acquisition. The user is not part of the data pipeline.
3. C++ is the authoritative production language for computation, signal decisions, risk, artifacts, and delivery logic.
4. Python is the official L1 acquisition implementation language under the strict boundary defined in Section 2. It must not become an alternative decision engine. C++ remains authoritative for L2 and L3.
5. Telegram is the only user-facing delivery channel.
6. Autonomous scheduled execution is required.
7. Exchange-independent data acquisition and fallback are required.
8. No trading-account connection, private trading API key, order execution, order modification, cancellation, or copy trading.
9. Every stage must satisfy L1 Data, L2 Compute, and L3 Delivery requirements.
10. Statistical claims must be supported by independently reproducible evidence.
11. Missing or unreliable data must never be silently replaced with fabricated or assumed values.
12. Every stage stops at its acceptance gate. The next stage requires explicit owner approval.
13. No document, code commit, test fixture, mock API, or successful local run may be misrepresented as proof of live production operation.
14. No acceptance criterion may be relaxed merely to create more signals or finish a stage.

0.3. Authority and precedence

The following precedence applies:

1. The latest explicit owner decisions control where they clearly amend previous requirements.
2. The safety boundary and manual-only trading rule are absolute.
3. This document becomes the single normative source only after explicit owner approval.
4. An approved amendment must be recorded in the Decision Register.
5. No implementation detail may silently weaken a hard gate, statistical threshold, safety control, or stage acceptance criterion.
6. An unresolved conflict must be recorded as "OPEN" and must block the affected implementation.
7. Previous documents must remain archived until the replacement is verified and accepted.

0.4. Requirement and evidence classification

Every important requirement, component, test, and operational claim must use one of these classifications:

Classification| Meaning
"SOURCE_REQUIREMENT"| Directly supported by an inspected source
"OWNER_DIRECTED"| Explicitly requested or amended by the owner
"INTEGRATION_RULE"| Required to make existing requirements operate consistently
"DESIGN_DECISION"| Proposed technical implementation decision
"NOT_IMPLEMENTED"| No implementation evidence
"NOT_TESTED"| No test evidence
"NOT_VERIFIED"| Insufficient direct evidence
"PASS"| Acceptance criteria passed with inspectable evidence
"FAIL"| Acceptance criteria failed with inspectable evidence
"PROXY"| Approximation rather than the required real measurement
"UNAVAILABLE"| Required information cannot currently be obtained
"STALE"| Data exceeds its registered freshness limit
"PARTIAL"| Required data is incomplete
"CONFLICTED"| Sources disagree beyond the accepted tolerance
"UNCALIBRATED"| Probability/confidence has not been statistically calibrated

A requirement is not an implementation. An implementation is not a test. A passing test is not proof of profitability.

0.5. Source integrity

The following limitations must remain visible until resolved:

- The original V10.0 source was not available for direct clause-by-clause inspection in the reviewed source set.
- The complete original V18.1 source bytes were not available for an exact line-by-line comparison.
- The V18.3 repair document is a design artifact, not proof that repairs were applied to a live repository.
- Repository code, branches, workflows, secrets, CI logs, API connectivity, and Telegram delivery must be inspected directly before any claim about their current state.

No missing source may be reconstructed and represented as an exact historical requirement.

0.6. Change control

Every material change must record:

- "decision_id"
- Previous requirement
- New requirement
- Reason
- Classification
- Technical impact
- Risk impact
- Affected stages
- Tests required
- Owner approval
- Implementation commit
- Effective version

Changes to hard gates, statistical acceptance thresholds, data semantics, C10 states, risk controls, or the manual-only boundary require explicit owner approval.

---

1. SYSTEM MISSION AND SCOPE

1.1. Mission

Build an autonomous, exchange-independent cryptocurrency futures signal intelligence system that:

1. Acquires public market data.
2. Validates instrument identity and data quality.
3. Discovers opportunities across an eligible perpetual-futures universe.
4. Runs independent analytical paths.
5. Produces transparent hypotheses and falsification conditions.
6. Evaluates risk, costs, liquidity, and data reliability.
7. Publishes only qualified information.
8. Maintains immutable signal and outcome records.
9. Measures real out-of-sample performance.
10. Delivers the final result to the owner through Telegram.

1.2. Explicit exclusions

The system must never:

- Connect to the user's exchange account.
- Request or store private trading API keys.
- Execute, modify, or cancel orders.
- Manage a trading account.
- Copy another trader's orders.
- Claim guaranteed profit.
- Fabricate historical candles, funding, open interest, order-book data, or trade outcomes.
- Treat a simulated signal as a live signal.
- Present uncalibrated scores as probabilities.
- Force a signal to satisfy a daily numerical quota.
- Treat missing data as zero.
- Treat an unavailable data field as a valid negative signal.
- Claim a strategy is profitable based only on in-sample performance.

1.3. Primary objective and optimization hierarchy

Optimization priorities, in descending order:

1. Data integrity and causality.
2. Risk containment.
3. Independent validation.
4. Signal quality.
5. Reliability and availability.
6. Market coverage.
7. Operational efficiency.
8. Notification volume.

A system that reports zero qualified trades after a complete and valid scan has behaved correctly.

A system that creates many signals by weakening filters has failed.

---

2. THREE-LAYER PRODUCTION ARCHITECTURE

2.1. Architecture overview

The production system has three mandatory layers:

SCHEDULED EXECUTION
        |
        v
L1 — DATA ACQUISITION
        |
        | Versioned, timestamped, provenance-preserving data
        v
L2 — C++ AUTHORITATIVE COMPUTE
        |
        | Validated decisions and immutable artifacts
        v
L3 — TELEGRAM OUTBOUND DELIVERY
        |
        v
OWNER RECEIVES SIGNALS

A stage cannot pass by implementing only one or two layers.

2.2. L1 — Data acquisition

Responsibilities:

- Public market-data acquisition.
- Provider selection and fallback.
- Exact perpetual-contract mapping.
- Instrument metadata collection.
- OHLCV collection.
- Funding-rate collection.
- Open-interest collection.
- Market-wide reference data.
- Source timestamps and acquisition timestamps.
- Basic schema validation.
- Raw response preservation where permitted.
- Versioned export to the C++ compute layer.
- Provider health and coverage metadata.

L1 must not:

- Generate BUY or SELL decisions.
- Calculate production signal scores.
- Perform strategy ranking.
- Apply production risk gates.
- Determine signal confidence.
- Decide whether a candidate is publishable.
- Write final trading recommendations.

2.2.1. Official Python L1 boundary

Python is the approved production language for L1 data acquisition. C++ is the authoritative production language for L2 computation and L3 Telegram delivery. This is an explicit owner-approved layer boundary, not a temporary migration exception.

Python L1 is limited to:

- Fetching public data.
- Mapping provider responses to canonical instruments.
- Timestamp normalization.
- Basic schema serialization.
- Acquisition provenance.
- Bounded retries.
- Provider health reporting.

Python must not own:

- Strategy execution.
- Feature decisions that determine signals.
- LFS/NSS scoring.
- Regime decisions used for signal eligibility.
- Entry, stop-loss, or take-profit decisions.
- Confidence or probability calculation.
- Risk approval.
- Signal-state assignment.
- Candidate ranking.
- Telegram publication decisions.

All L1 output is untrusted input. C++ must independently validate it before use.

The approved Python L1 boundary is recorded as ADR-001 with:

- Current purpose.
- Exact permitted functions.
- Prohibited functions.
- Input/output contract.
- Migration or retirement condition.
- Tests proving that decision logic remains in C++.

A Python component must not silently expand its responsibility.

2.3. L2 — C++ authoritative compute

C++ owns all authoritative production decisions:

- Data admission and rejection.
- Instrument validation.
- Timestamp and candle validation.
- Feature calculations used by production strategies.
- Regime and market-state decisions.
- Strategy execution.
- Candidate generation.
- LFS and NSS calculations.
- Plan A/B/C/H logic.
- Signal states.
- Entry, SL, TP, and expiry.
- Risk checks.
- Cost calculations.
- Conflict resolution.
- Ranking within an approved path.
- Signal identity and deduplication.
- Artifact generation.
- Run manifests.
- Outcome attribution.
- Calibration and performance calculations.
- Final publication eligibility.

The selected C++ standard, compiler, build system, and dependencies must be verified against the actual GitHub Actions runner. Do not invent a toolchain version before runner compatibility is tested.

2.4. L3 — Telegram-only delivery

Telegram is the only user-facing delivery channel.

L3 is responsible for:

- Approved signal messages.
- Daily status messages.
- Degraded-data notifications.
- Signal expiry notifications where required.
- Outcome summaries.
- Operational failure notifications.
- Delivery receipts.
- Duplicate prevention.
- Retry management.
- Message identity and traceability.

No dashboard, browser interface, user-side exchange connection, or external charting account is required for normal operation.

Telegram is a delivery mechanism, not a source of trading decisions.

A delivery failure must not modify the underlying signal decision. It changes only the delivery status.

2.5. Layer ownership

Responsibility| L1| L2| L3
Public data acquisition| Primary| No| No
Instrument normalization| Initial| Authoritative validation| No
Data quality admission| Preliminary| Authoritative| No
Feature calculation| No production decision features| Authoritative| No
Strategy execution| No| Authoritative| No
Risk decisions| No| Authoritative| No
Signal state| No| Authoritative| No
Artifact creation| Raw export| Authoritative artifacts| Delivery receipts
Telegram send| No| Publication authorization| Actual outbound delivery
Performance measurement| No| Authoritative| Presentation only

---

3. DATA PROVIDERS, UNIVERSE AND DATA QUALITY

3.1. Provider independence

The system must not be hard-locked to one exchange or provider.

Provider selection is performed independently for each data field.

A provider may be suitable for OHLCV but unsuitable for funding, open interest, or instrument metadata.

A fallback is valid only when the alternative source provides semantically equivalent data for the exact required instrument and field.

Spot data must never replace perpetual-futures data.

An instrument from one exchange must not be silently treated as an identical contract on another exchange.

3.2. Provider priority

Initial provider evaluation order:

1. OKX public market data.
2. Bybit public market data.
3. Binance public market data, subject to actual endpoint accessibility.
4. KuCoin.
5. MEXC.
6. Bitget.
7. CoinGecko for supported reference fields only.
8. Binance Vision or another verified historical archive for eligible historical data.

This is a discovery priority, not a guarantee of availability.

Each provider must be evaluated for:

- Endpoint availability.
- Exact instrument coverage.
- Historical depth.
- Request limits.
- Data freshness.
- Timestamp semantics.
- Funding coverage.
- Open-interest coverage.
- Contract metadata.
- Rate-limit behavior.
- Reliability.
- Free-tier restrictions.
- Actual runtime cost.

No provider is declared operational until a real request and response have been verified.

3.3. Universe target

The initial target universe is:

- 27 eligible perpetual-futures contracts.
- BTC reference market data.
- Additional contracts only after explicit eligibility and capacity checks.

The number 27 is a target, not a reason to include unsuitable instruments.

The system must distinguish:

- "UNIVERSE_DEFINED"
- "UNIVERSE_DISCOVERED"
- "CONTRACTS_ELIGIBLE"
- "CONTRACTS_SCANNED"
- "CONTRACTS_DATA_VALID"
- "CONTRACTS_QUALIFIED"
- "SIGNALS_PUBLISHED"

Every run must report these counts.

If only 19 contracts pass eligibility, the system must report 19. It must not fabricate eight additional eligible instruments.

3.4. Contract eligibility

A contract is eligible only after verifying:

- Exact instrument identity.
- Perpetual contract status.
- Settlement and quote currency.
- Trading status.
- Sufficient historical data.
- Minimum liquidity evidence.
- Data-source consistency.
- Required timeframe availability.
- Acceptable spread or liquidity proxy.
- No unresolved mapping conflict.

The liquidity requirement inherited from the project design is greater than USD 10 million, but its measurement window, field definition, and provider source must be registered before it is used as a production gate.

Do not equate 24-hour reported volume with executable order-book liquidity.

3.5. Required data domains

OHLCV

Required fields:

- Open time.
- Close time.
- Open.
- High.
- Low.
- Close.
- Volume.
- Quote volume where available.
- Trade count where available.
- Instrument ID.
- Provider ID.
- Acquisition timestamp.
- Source timestamp.
- Candle completion status.

Historical target: up to two years where genuinely available.

Missing history must be labelled "PARTIAL" or "UNAVAILABLE".

Funding

Required fields:

- Instrument.
- Funding rate.
- Funding timestamp.
- Funding interval.
- Provider.
- Acquisition timestamp.

Funding values from different interval conventions must not be compared without normalization.

Open Interest

Required fields:

- Instrument.
- Open-interest value.
- Unit.
- Timestamp.
- Provider.
- Acquisition timestamp.

The system must distinguish base-asset open interest from quote-currency notional.

Historical target: 30 days where genuinely available.

Market reference data

May include:

- BTC market regime inputs.
- Market breadth.
- Total market reference metrics.
- Fear and Greed Index.
- Liquidation data.
- Order-book depth.
- CVD and volume delta.

Every field must carry its own availability and quality label.

3.6. Data quality classifications

Each required field must receive one of:

- "REAL"
- "PROXY"
- "UNAVAILABLE"
- "STALE"
- "PARTIAL"
- "CONFLICTED"
- "INVALID"

These states must not be collapsed into a single Boolean.

Examples:

- A real OHLCV feed with missing funding is not a fully complete derivatives dataset.
- A delayed open-interest feed must not be described as current.
- A CoinGecko reference price is not a substitute for an exchange perpetual contract's executable price.
- A synthetic order-book proxy is not real order-book depth.

3.7. Point-in-time integrity

Every observation must preserve:

- Event time.
- Provider timestamp.
- Acquisition time.
- Processing time.
- Publication time.

The system must not use future information.

A feature is valid only if all its inputs were available at or before the decision timestamp.

Completed-candle rules are mandatory.

Unfinished candles may be retained for monitoring but cannot be treated as completed evidence.

Revised or corrected provider candles must be versioned and must not silently overwrite the historical data used in a previously published signal.

3.8. OHLCV validation

Reject or quarantine data containing:

- Negative prices.
- Negative volume.
- High below low.
- Open or close outside the high-low range.
- Duplicate candle timestamps.
- Unexpected gaps.
- Invalid interval alignment.
- Impossible timestamps.
- Incorrect instrument mapping.
- Incomplete candle data where a completed candle is required.

Missing candles must not be automatically interpolated for production signal generation.

Any permitted interpolation for research must be labelled "PROXY" and isolated from production evidence.

3.9. Provider failover

Provider failover must be field-specific.

A fallback candidate must pass:

1. Instrument identity check.
2. Field semantic equivalence.
3. Timestamp compatibility.
4. Unit compatibility.
5. Freshness check.
6. Data-quality validation.

If sources disagree beyond the registered tolerance:

"DATA_STATUS = CONFLICTED"

The system must not average conflicting values simply to continue execution.

Provider retry policy must include:

- Bounded retry count.
- Exponential backoff where appropriate.
- Jitter.
- Per-provider request budget.
- Whole-run deadline.
- Circuit breaker.
- Failure classification.

An unavailable provider must not cause an unbounded retry loop.

3.10. Data contracts and schema versioning

Every L1 export must include:

{
  "schema_version": "1.0",
  "run_id": "unique-run-id",
  "instrument_id": "canonical-instrument-id",
  "contract_type": "PERPETUAL",
  "provider": "provider-id",
  "data_status": "REAL",
  "event_timestamp": "UTC timestamp",
  "acquired_at": "UTC timestamp",
  "timeframe": "15m",
  "candle_complete": true,
  "ohlcv": [],
  "funding": null,
  "open_interest": null,
  "provenance": {
    "source_endpoint": "registered-endpoint-id",
    "response_hash": "sha256",
    "provider_timestamp": "UTC timestamp"
  }
}

The example is a contract illustration, not evidence of a live response.

The schema must be versioned. Breaking changes require a migration plan and compatibility tests.

3.11. Storage and retention

GitHub repository storage must not be treated as a permanent raw-market-data lake.

The system may store:

- Current scan artifacts.
- Compact signal history.
- Run manifests.
- Small validation summaries.
- Required reproducibility metadata.

Long historical datasets require an independently verified storage option with known free-tier limits.

If durable free storage cannot be demonstrated:

"LONG_TERM_RAW_DATA_STORAGE = UNAVAILABLE"

Do not promise permanent retention based only on the existence of a Git repository.

---

4. OPERATING PROFILES AND TIMEFRAMES

4.1. Daily / Swing

The Daily/Swing profile is the initial primary profile.

Reference timeframe structure:

Purpose| Timeframe
Broad market context| 1D
Market bias| 4H
Setup identification| 1H
Entry structure| 15m
Optional confirmation| 5m

A higher-timeframe bias is context, not an entry trigger.

A lower-timeframe signal cannot override a failed data, causality, risk, or strategy gate.

4.2. Scalp activation sequence

Scalp must be developed in stages:

1. LRT 15m.
2. LRT 5m.
3. LRT 1m research/shadow only.

The first Scalp implementation must use completed candles.

A nominal cron frequency does not prove the system can process, validate, and publish data at that frequency.

4.3. Scalp 15m

The 15m Scalp stage must establish:

- Data completeness.
- Completed-candle enforcement.
- Latency measurements.
- Signal expiry.
- Entry validity.
- Stop and target calculation.
- Realistic spread and slippage assumptions.
- Independent outcome ledger.
- Shadow evidence.

It must not inherit Daily/Swing performance statistics.

4.4. Scalp 5m

5m activation requires:

- Successful 15m stage.
- Verified scheduler capacity.
- Verified provider request limits.
- Measured execution time.
- Measured publication delay.
- Independent 5m data-quality checks.
- Separate cost and outcome accounting.
- Shadow-first validation.

If the free-tier infrastructure cannot reliably support the required frequency, the profile must remain disabled or shadow-only.

4.5. Scalp 1m

The 1m profile is research/shadow only until a separate approval gate is passed.

No real-time execution or tick-level accuracy claim may be made without direct latency and data-quality evidence.

---

5. FOUR INDEPENDENT ANALYTICAL PATHS

The system contains four separate paths:

- Plan A — Dual Engine.
- Plan B — Cross-Sectional Factor Model.
- Plan C — Robust Ensemble.
- Plan H — Daily Signal Factory.

Each path owns its:

- Hypothesis.
- Data requirements.
- Features.
- Parameters.
- Signal generation.
- Risk checks.
- Performance ledger.
- Trial history.
- Calibration.
- Validation report.
- Release decision.

A shared infrastructure layer is allowed. Shared performance evidence is not.

---

6. PLAN A — DUAL ENGINE LRT / NMT

6.1. Core model

Every relevant market move is evaluated through two separate hypotheses:

- Liquidity Reversion Trading (LRT).
- Narrative Momentum Trading (NMT).

They represent different market behaviors and must not be blended into one score.

6.2. LRT

Research horizon: 30 minutes to 4 hours.

Core hypothesis:

A validated liquidity sweep, failed breakout, liquidity rejection, or structural reclaim may create a measurable reversion opportunity.

Potential evidence:

- Liquidity Sweep.
- Equal High / Equal Low.
- Order Blocks.
- Fair Value Gaps.
- BOS / CHoCH.
- CVD.
- Volume Delta.
- Order Book Imbalance.
- Liquidation Clusters.
- VWAP.
- Volume Profile.
- ATR.
- Market Structure.
- Ichimoku.

A feature may enter production only after its mathematical definition, data dependency, availability timestamp, missing-data policy, and falsification test are registered.

6.3. LFS formula

Reference formula:

LFS =
    0.25 * LFS1
  + 0.20 * LFS2
  + 0.20 * LFS3
  + 0.20 * LFS4
  + 0.15 * LFS5

Components:

Component| Definition
LFS1| Book Thinness
LFS2| Funding Extreme
LFS3| Long/Short Positioning
LFS4| Volatility Compression
LFS5| Open Interest Change

Each component must:

- Have a deterministic formula.
- Be normalized to [0,1].
- Have documented score orientation.
- Use point-in-time data.
- Carry a source-quality label.
- Have a defined missing-data policy.
- Be independently testable.

A component score is not a probability.

If a required component is unavailable, the system must use an approved resilience version or mark the score invalid.

6.4. NMT

Research horizon: 1 to 7 days.

Core hypothesis:

Directional continuation may occur when market participation, derivatives positioning, relative strength, volume expansion, and market regime align.

Potential evidence:

- Open Interest Growth.
- Funding Rate.
- Basis Expansion.
- Volume Expansion.
- Relative Strength.
- ADX.
- Momentum.
- Breakout Structure.
- Market Breadth.
- BTC Market Regime.
- Liquidation Dynamics.

6.5. NSS formula

Reference formula:

NSS =
    0.30 * NSS1
  + 0.20 * NSS2
  + 0.20 * NSS3
  + 0.15 * NSS4
  + 0.15 * NSS5

The five components must be fully specified before production use.

Every component requires:

- Formula.
- Normalization.
- Direction.
- Lookback.
- Source.
- Timestamp.
- Missing-data behavior.
- Version.
- Test.

NSS is not a probability unless a separate calibration process establishes that interpretation.

6.6. Golden Rule

At the same decision timestamp:

IF LFS > 0.70 AND NSS > 0.70:
    DECISION = NO TRADE

This is a mandatory hard veto.

It cannot be overridden by:

- Consensus.
- Ranking.
- Confidence.
- Machine learning.
- Another path.
- Desired signal volume.
- User-interface preferences.

The veto is evaluated only when both scores are valid, comparable, and timestamp-aligned.

If either score is invalid, no score-based conclusion may be drawn.

6.7. LFS/NSS resilience versions

Each score must have no more than three registered versions:

Version| Method
V1| Original formula
V2| Approved proxy-based formulation
V3| Percentile-based formulation

Rules:

- V2 is built only after V1 fails.
- V3 is built only after V2 fails.
- Each version must differ in a substantive assumption, not merely a parameter.
- A version cannot be created to conceal a failed result.
- Every version and failure remains in the registry.
- No version may relax an acceptance threshold.

Auto-threshold reference:

"Rolling 90-day 80th percentile"

This is a research reference until its data requirements and stability are validated.

Auto-switch reference:

"50 signals / 30 days"

This is not permission to switch without an explicit registered rule and sufficient independent evidence.

---

7. PLAN B — CROSS-SECTIONAL FACTOR MODEL

7.1. Objective

Discover relative opportunities across the eligible perpetual-futures universe using a six-factor cross-sectional model.

7.2. Model

The model must define six factors:

- "B1"
- "B2"
- "B3"
- "B4"
- "B5"
- "B6"

Each factor requires:

- Economic or market hypothesis.
- Formula.
- Source.
- Timeframe.
- Normalization.
- Direction.
- Missing-data policy.
- Parameter budget impact.
- Independent falsification condition.

The factor definitions must be frozen before the test period.

7.3. Ranking

The reference approach is:

- Top decile.
- Bottom decile.
- Long/short portfolio.
- Beta-hedged exposure.

The model must not use future universe membership.

Cross-sectional normalization must use only information available at the decision timestamp.

7.4. Beta hedging

Beta hedging is an exposure-management step, not an extra signal factor.

It requires:

- Explicit benchmark.
- Estimation window.
- Return frequency.
- Hedge formula.
- Rebalancing rule.
- Cost model.
- Exposure constraints.

The system must not double-count a factor as both a signal reward and a hedge penalty without an independently registered rationale.

7.5. Independent validation

Plan B requires its own:

- Trial registry.
- Walk-Forward process.
- Cost model.
- OOS ledger.
- Baselines.
- Risk report.
- Gate_B decision.

Plan B performance cannot be combined with Plan A or C to conceal weak results.

---

8. PLAN C — ROBUST ENSEMBLE

8.1. Components

Plan C contains:

1. Donchian.
2. EMA 50/200.
3. Funding Extreme.

Each component must first be tested independently.

8.2. Ensemble admission

A component may enter the ensemble only if it demonstrates measurable incremental value under out-of-sample validation.

The ensemble must not:

- Hide a losing component.
- Override component-specific hard gates.
- Reuse another path's performance evidence.
- Increase signal volume by weakening risk filters.
- Present correlated components as independent confirmation.

8.3. Required reporting

Report:

- Individual component performance.
- Combined performance.
- Incremental contribution.
- Correlation.
- Turnover.
- Costs.
- Drawdown.
- Stability across regimes.

If the ensemble does not outperform a justified baseline after costs, it must not be promoted.

---

9. PLAN H — DAILY SIGNAL FACTORY

9.1. Objective

Plan H is a daily opportunity-discovery factory containing seven independent generators:

- H1
- H2
- H3
- H4
- H5
- H6
- H7

Each generator must have its own:

- Hypothesis.
- Falsification.
- Data requirements.
- Timeframe.
- Entry logic.
- Risk logic.
- Expiry.
- Trial ID.
- Performance ledger.
- Validation status.

9.2. Tier classification

Generators use:

- Tier A.
- Tier B.
- Tier C.

Tier classification must reflect evidence maturity and gate results, not the number of signals produced.

A Tier C observation must not be presented as an actionable Tier A signal.

9.3. Sample maturity

Each generator must be evaluated independently.

The reference maturity requirement is 150–200 trades per generator.

Fifty observations may be used as an early warning checkpoint only.

A sample count alone does not establish statistical power, profitability, or reliability.

9.4. Duplicate hypothesis control

Generators with substantially overlapping features or hypotheses must be identified in a relatedness matrix.

Feature reuse does not establish independent confirmation.

The same market setup must not be counted as multiple independent trades merely because multiple generators detected it.

---

10. SIGNAL STATES AND META-COGNITION

10.1. Mandatory daily state contract

For every symbol and enabled profile, the system must produce exactly one final state when the scan has completed.

Allowed states:

BUY_NOW
SELL_NOW
CONDITIONAL_BUY
CONDITIONAL_SELL
WATCHLIST
NO_QUALIFIED_SETUP
MARKET_DATA_DEGRADED

10.2. State definitions

BUY_NOW / SELL_NOW

Allowed only when:

- Data gates pass.
- Causality gates pass.
- Strategy is approved.
- Required evidence is mature.
- Risk checks pass.
- Entry is valid at publication time.
- Signal has not expired.
- All required release conditions pass.

CONDITIONAL_BUY / CONDITIONAL_SELL

A setup exists, but an explicit trigger has not yet occurred.

The message must state:

- Trigger condition.
- Trigger timeframe.
- Expiry.
- Invalidation.
- Data status.
- Evidence limitations.

It must not be represented as an immediately executable instruction.

WATCHLIST

A research candidate or incomplete setup that does not qualify for a conditional or actionable state.

NO_QUALIFIED_SETUP

Use only when the symbol was successfully evaluated with sufficient valid data and no candidate passed the required gates.

MARKET_DATA_DEGRADED

Use when required data is missing, stale, conflicted, invalid, or insufficient for safe evaluation.

Silence must never be interpreted as "NO_QUALIFIED_SETUP".

A failed scan is not a completed no-signal scan.

10.3. Signal object

Every candidate must include:

- "signal_id"
- "run_id"
- "instrument_id"
- "profile"
- "path"
- "generator_id"
- "strategy_version"
- "direction"
- "state"
- "tier"
- "hypothesis"
- "falsification"
- "entry"
- "stop_loss"
- "take_profit_1"
- "take_profit_2"
- "expiry"
- "decision_timestamp"
- "data_status"
- "confidence_status"
- "calibration_status"
- "cost_status"
- "risk_status"
- "source_provenance"
- "parameter_version"

Unavailable fields must be explicitly null or marked unavailable according to the schema. They must not be fabricated.

10.4. Hypothesis and falsification

Every signal must have a measurable hypothesis.

Example structure:

HYPOTHESIS:
If condition A and condition B occur,
then outcome C is expected within horizon T.

FALSIFICATION:
The hypothesis is invalid if condition X occurs,
or if outcome C does not occur within horizon T.

The conditions must be measurable and registered before the outcome.

10.5. Confidence

Allowed labels:

- "CALIBRATED"
- "UNCALIBRATED"
- "INSUFFICIENT_SAMPLE"
- "INVALID_CALIBRATION"

An uncalibrated score must not be presented as a statistically established probability.

10.6. Expected value

When calibrated inputs are available:

EV =
    P(W) * AverageWin
  - P(L) * AverageLoss
  - TradingCosts

If calibration is unavailable:

"EV_STATUS = NOT_CALIBRATED"

If calibrated net EV is less than or equal to zero:

"DECISION = NO TRADE"

Costs must include the applicable fee, spread, slippage, and funding assumptions.

---

11. RISK AND EXECUTION GUARDS

11.1. G1 — Look-ahead prevention

No future information may enter a feature, score, signal, or outcome calculation.

Every feature must preserve availability time.

11.2. G2 — Leakage prevention

Training, validation, and test data must be isolated.

Labels, normalization, feature selection, and thresholds must not leak information from future periods.

11.3. G3 — Realistic costs

The cost model must include:

- Trading fees.
- Spread.
- Slippage.
- Funding.
- Applicable execution assumptions.

Reference fee:

"0.04%"

Its one-way or round-trip interpretation must be explicitly established before use.

Unknown costs must not be described as net performance.

11.4. G4 — Liquidity

Reference threshold:

"Greater than USD 10M"

The exact volume or liquidity definition, measurement window, source, and unit must be registered.

A volume threshold is not a guarantee of executable liquidity.

11.5. G5 — Correlation

Reference rule:

Maximum three simultaneously held exposures with correlation greater than 0.7.

Correlation methodology must specify:

- Return frequency.
- Estimation window.
- Missing-data policy.
- Pairwise versus portfolio exposure.
- Update frequency.

11.6. G6 — Overfitting

Required controls:

- Maximum five tunable parameters per registered strategy.
- Walk-Forward validation.
- Deflated Sharpe Ratio.
- Probability of Backtest Overfitting.
- Trial registry.
- Holdout discipline.
- Parameter provenance.

Weights, thresholds, lookbacks, feature switches, model coefficients, and selection rules count as tunable parameters when selected based on performance.

Hard-coded parameters are not automatically exempt.

11.7. G7 — Kill switch

Reference limits:

- Daily loss: 5%.
- Weekly loss: 10%.

These limits must be calculated using a precisely defined reference equity or risk budget.

The system must not imply it can enforce account-level loss limits because it has no trading-account connection.

It may disable signal publication when its registered risk proxy or research risk limit is breached.

11.8. G8 — Self-critique

Every stage and every major release must answer:

1. Was future data used?
2. Were parameters tuned on test data?
3. Were costs included?
4. Does the system report correctly when there is no signal?
5. What is the weakest assumption?

Any "NO" or "UNKNOWN" requires remediation before acceptance.

11.9. Risk precedence

Risk gates are hard vetoes.

No ranking, confidence score, consensus, or signal quota can override a failed risk gate.

---

12. RESEARCH AND STATISTICAL VALIDATION

12.1. General rule

All performance claims must be based on out-of-sample evidence.

In-sample performance is research evidence only.

A strategy may not be promoted because its backtest chart looks attractive.

12.2. Walk-Forward schedule

Reference schedule:

- Training: 6 months.
- Testing: 2 months.
- Step: 1 month.

This schedule creates overlapping test windows.

Overlapping test folds must not be pooled naively.

12.3. Overlap-safe aggregation

Required controls:

1. Report each fold independently.
2. Preserve each trade's unique identity.
3. Deduplicate repeated OOS observations.
4. Do not count the same trade more than once in the primary pooled denominator.
5. Record the test-window identity.
6. Apply purge and embargo based on label horizon and holding period.
7. Retire contaminated holdout data from final proof.
8. Report both fold-level and valid pooled results.

A strategy must not inflate its sample size by counting the same trade in several overlapping test windows.

12.4. Required metrics

For each path, profile, strategy, and generator, report:

- DSR.
- PBO.
- Brier Score.
- Win Rate.
- Profit Factor.
- Maximum Drawdown.
- Sharpe Ratio.
- Net EV.
- Trade count.
- Effective independent sample size.
- Turnover.
- Cost contribution.
- Coverage.
- Stability across regimes.
- Confidence intervals.

All final performance claims must be based on OOS evidence.

12.5. Brier Score

Brier Score must be calculated only when the underlying probability forecasts have a valid definition.

A Brier Score below 0.25 is not sufficient by itself to establish Tier A quality.

Report:

- Sample count.
- Base rate.
- Forecast distribution.
- Calibration curve.
- Reliability.
- Confidence interval.
- Comparison with a baseline forecast.

Do not use Brier Score as a substitute for profitability.

12.6. Win-rate uncertainty

Report a confidence interval for win rate.

Use an appropriate method, such as Wilson intervals, where applicable.

A small sample with a high win rate must not be presented as a stable edge.

12.7. Baselines

Every strategy must be compared against three baselines:

1. EMA Cross.
2. RSI.
3. Buy & Hold.

Baseline definitions and costs must be frozen before the test.

12.8. Red flags

The following results trigger an overfitting and leakage investigation:

- OOS Win Rate greater than 80%.
- OOS Sharpe greater than 3.

These values are not automatically proof of fraud or failure. They are mandatory investigation triggers.

12.9. Gate_A

Plan A acceptance:

- LRT OOS Win Rate ≥ 55%.
- NMT OOS Win Rate ≥ 45%.
- Profit Factor ≥ 1.4.
- Maximum Drawdown ≤ 20%.
- PBO < 0.4.

All criteria must be measured on valid OOS evidence.

12.10. Gate_B

Plan B acceptance:

- OOS Sharpe ≥ 1.2.
- Maximum Drawdown ≤ 20%.
- PBO < 0.4.
- Alpha > 0.

Alpha must be defined relative to an appropriate benchmark and after applicable costs.

12.11. Gate_C

Plan C acceptance:

- Profit Factor ≥ 1.2.
- Maximum Drawdown ≤ 25%.
- PBO < 0.5.

12.12. Gate_H

Each H generator requires:

- 150–200 trades as the reference maturity range.
- Independent OOS results.
- Independent cost accounting.
- Independent calibration evidence.
- Independent risk report.

Fifty trades are an early-warning checkpoint only.

12.13. Sample-size honesty

A numerical trade count does not automatically establish statistical power.

The system must consider:

- Independence.
- Serial correlation.
- Regime diversity.
- Effective sample size.
- Confidence intervals.
- Multiple testing.
- Selection bias.

12.14. Trial registry

Every tested version must remain recorded, including failures.

Required fields:

- "trial_id"
- "strategy_id"
- "version"
- "hypothesis"
- "parameter_set"
- "training_period"
- "test_period"
- "data_version"
- "code_commit"
- "metrics"
- "cost_model"
- "result"
- "failure_reason"
- "promotion_status"

Failed trials must never be deleted to improve reported performance.

---

13. PARAMETER AND THRESHOLD REGISTRY

Every numeric threshold must be registered.

Required fields:

- "parameter_id"
- "parameter_name"
- "value"
- "unit"
- "parameter_type"
- "source"
- "rationale"
- "owner"
- "strategy_version"
- "data_dependency"
- "test_reference"
- "approval_status"

Parameter types:

- "HARD_LIMIT"
- "RESEARCH_REFERENCE"
- "TUNABLE_PARAMETER"
- "OPERATIONAL_SLO"
- "DATA_QUALITY_LIMIT"

Examples requiring explicit registration include:

- 0.70 LFS/NSS threshold.
- 90-day percentile window.
- 80th percentile.
- 0.70 correlation threshold.
- USD 10M liquidity threshold.
- 5% daily risk reference.
- 10% weekly risk reference.
- 0.04% fee reference.
- 150–200 trade maturity reference.
- 20% backtest-shadow divergence reference.
- ATR and FVG thresholds.
- Volume expansion thresholds.
- Candle-reclaim definitions.

A research reference is not automatically a production gate.

A parameter cannot be excluded from the five-parameter budget merely because it is stored as a constant.

No threshold may be modified retroactively to improve a result.

---

14. SLRP — SELF-LEARNING AND RESILIENCE PROTOCOL

14.1. Mandatory versions

Every stage must define:

- V1.
- V2.
- V3.

A version is built only when the previous version has genuinely failed.

Maximum:

"3 versions per stage"

14.2. Required SLRP structure

Every stage must contain:

1. Objective.
2. Numeric acceptance criteria.
3. V1 implementation.
4. Diagnosis.
5. V2 implementation if V1 fails.
6. Diagnosis.
7. V3 implementation if V2 fails.
8. Final report and escalation.

14.3. Diagnosis codes

Code| Meaning
D1| Data failure
D2| Assumption failure
D3| Implementation failure
D4| Threshold or calibration failure
D5| Regime mismatch
D6| Expectation or objective mismatch

Every diagnosis must include actual evidence.

Examples:

- D1: 18% of required candles missing.
- D2: assumed relationship absent in the registered sample.
- D3: reproducible calculation mismatch.
- D4: calibration error above registered tolerance.
- D5: strategy fails in the specified market regime.
- D6: acceptance objective was not supported by the original evidence.

Generic diagnoses such as "market conditions were difficult" are not acceptable.

14.4. Version rules

- R1: Three versions must be defined.
- R2: Versions must differ in a substantive assumption.
- R3: V2 must be based on V1 diagnosis.
- R4: Maximum three versions.
- R5: All versions and failures must be logged.
- R6: No V2 without evidence explaining why V1 failed.
- R7: V3 failure triggers Innovation Protocol.
- R8: Next stage requires PASS.
- R9: Acceptance criteria must not be relaxed.
- R10: Criteria may change only with explicit owner approval.
- R11: V2/V3 are built only after a real failure.

14.5. SLRP report format

STAGE [N] — [NAME]

Acceptance:
[Numeric criteria]

V1:
PASS / FAIL
Diagnosis:
Evidence:

V2:
PASS / FAIL / NOT BUILT
Diagnosis:
Evidence:

V3:
PASS / FAIL / NOT BUILT
Diagnosis:
Evidence:

Active:
V1 / V2 / V3 / NONE

Handoff:
NEXT STAGE / ESCALATION

If V1 passes, V2 and V3 must not be built.

---

15. INNOVATION PROTOCOL

The Innovation Protocol is mandatory and must never be removed.

It activates when:

- V1, V2, and V3 fail; or
- Gate_C fails; or
- A critical assumption is invalidated.

Required sequence:

1. Data Expansion.
2. Timeframe Shift.
3. Simplicity Audit.
4. Regime Restriction.
5. Alternative Market.
6. Honest Stop.

Each experiment is limited to two weeks.

The total protocol must not become an endless optimization loop.

After the protocol:

- Build an explicitly approved MVP; or
- Stop the approach honestly.

A failed strategy must not remain active through cosmetic parameter changes.

---

16. AUTONOMOUS EXECUTION AND ZERO-COST INFRASTRUCTURE

16.1. Execution platform

The initial target is:

- GitHub repository.
- GitHub Actions.
- Public provider APIs.
- Telegram Bot API.
- Verified free storage where required.

No paid service may become a hidden dependency.

16.2. Scheduler

Reference schedule:

0 */4 * * *

This is the initial broad-scan target, not a guarantee that the selected free tier will support unlimited execution.

Actual runtime, request counts, monthly usage, storage, and quota must be measured.

Scalp scheduling requires a separate feasibility benchmark.

16.3. Free-tier validation

For every service, record:

- Free-tier limit.
- Monthly quota.
- Execution limit.
- Storage limit.
- Request limit.
- Runtime.
- Actual consumption.
- Failure behavior.
- Upgrade or payment requirement.

If a required function cannot be performed within the genuinely free allowance:

"FREE_TIER_FEASIBILITY = FAIL"

Do not silently switch to a paid plan.

Do not use a paid trial as proof of zero-cost feasibility.

16.4. Pipeline stages

Every scheduled run must follow:

RUN INITIALIZATION
    |
    v
DATA ACQUISITION
    |
    v
DATA VALIDATION
    |
    v
FEATURE AND STRATEGY COMPUTATION
    |
    v
RISK AND RELEASE GATES
    |
    v
ARTIFACT GENERATION
    |
    v
TELEGRAM DELIVERY
    |
    v
RUN FINALIZATION

Each stage must produce an explicit result.

16.5. Run manifest

Every run must record:

- "run_id"
- Commit SHA.
- Workflow run ID.
- Start time.
- End time.
- Schema version.
- Provider status.
- Data coverage.
- Data freshness.
- Instrument counts.
- Strategy versions.
- Parameter versions.
- Test status.
- Artifact hashes.
- Telegram delivery status.
- Resource consumption.
- Failure codes.

16.6. Artifact publication

Artifacts must be published atomically.

A partial run must not overwrite a valid previous complete result.

Use temporary output, validation, checksum, and atomic replacement.

The final artifact must be traceable to a unique run and code commit.

16.7. Retry and recovery

Retries must be:

- Bounded.
- Idempotent.
- Logged.
- Deadline-aware.

A retry must not create duplicate signals or duplicate Telegram messages.

A failed run must remain visible as failed.

---

17. TELEGRAM DELIVERY CONTRACT

17.1. Delivery boundary

Telegram is the only user-facing channel.

The bot sends outbound messages only.

Inbound polling and command processing are not part of the initial delivery scope unless a new owner-approved requirement explicitly introduces them.

17.2. Required signal message

Every actionable signal must contain:

1. Symbol and exact contract identity.
2. Direction.
3. Profile and timeframe.
4. Entry price or entry range.
5. Stop Loss.
6. Take Profit 1.
7. Take Profit 2.
8. Expiry.
9. Confidence/calibration status.
10. Hypothesis.
11. Falsification condition.
12. Data-quality status.
13. Risk summary.
14. Signal ID.
15. Unique run reference where appropriate.

If a required field is unavailable, the signal must be downgraded or rejected according to the registered rule.

17.3. Chart requirement

A chart may be attached only when its underlying data and timestamps are consistent with the signal.

The chart must not:

- Use future candles.
- Display a different instrument.
- Display a different timeframe.
- Hide invalidation.
- Contradict the numeric entry/SL/TP values.

If a valid chart cannot be generated, the message may use a clearly identified text-only fallback.

17.4. Delivery receipt

A Telegram send is successful only when the API returns a positive response and a message identifier.

Required fields:

- "telegram_status"
- "telegram_message_id"
- "telegram_chat_reference"
- "sent_at"
- "signal_id"
- "run_id"

A request attempt is not proof of delivery.

17.5. Duplicate prevention

Use a deterministic idempotency key derived from the signal identity and publication event.

A retry must not send a duplicate message.

If the system cannot establish whether a previous send succeeded, it must reconcile delivery status before retrying where possible.

17.6. Failure handling

If Telegram delivery fails:

- Preserve the signal artifact.
- Mark delivery as failed.
- Record the API error.
- Retry within a bounded policy.
- Avoid duplicate sends.
- Do not report delivery success without a positive receipt.

17.7. Daily status message

A daily status message must report:

- Scan completion.
- Universe count.
- Eligible contracts.
- Successfully scanned contracts.
- Data-degraded contracts.
- Qualified signals.
- No-setup count.
- Provider health.
- Telegram delivery health.

A day with zero signals must still have an honest status outcome when the scan completed.

---

18. DAILY OUTPUT AND SIGNAL VOLUME

18.1. Daily report guarantee

The system must produce a daily status result.

This is a reporting guarantee, not a trading-signal guarantee.

Every eligible symbol/profile must end in one of the seven C10 states when the scan has completed.

18.2. Daily signal target

The operational target is approximately 5–10 useful signals per day when market conditions and evidence support them.

This is a KPI only.

It is not:

- A minimum.
- A hard acceptance criterion.
- A reason to weaken thresholds.
- A reason to publish Tier C as Tier A.
- A reason to manufacture trades.

If only two signals qualify, publish two.

If none qualifies, publish none and report the completed scan accurately.

18.3. Signal diversity

The system should maximize distinct opportunities, not repeated alerts about the same setup.

Signals must be grouped by:

- Instrument.
- Direction.
- Setup family.
- Time window.
- Strategy/generator identity.

Duplicate or highly overlapping candidates must not inflate daily output or statistical sample size.

---

19. SECURITY AND MANUAL-ONLY OPERATION

19.1. Credentials

Permitted credentials are limited to the minimum required for:

- Telegram outbound delivery.
- Approved infrastructure operations.

No private trading credentials are allowed.

19.2. Secret handling

Secrets must:

- Be stored in the approved secret manager.
- Never be committed to source control.
- Never appear in logs.
- Never be included in artifacts.
- Be masked in CI output.
- Have documented rotation procedures.

19.3. Manual-only boundary

The system provides research and signal information.

The owner independently decides whether to act.

No code path may:

- Place orders.
- Modify orders.
- Cancel orders.
- Transfer assets.
- Access account balances through private trading APIs.
- Manage leverage or positions.

This boundary applies to all current and future stages.

---

20. OBSERVABILITY AND REPRODUCIBILITY

20.1. Required observability

Every run must expose:

- Data-source health.
- Data freshness.
- Data coverage.
- Instrument eligibility.
- Feature status.
- Strategy status.
- Gate failures.
- Signal counts.
- Delivery status.
- Resource consumption.
- Runtime.
- Failure reason.

20.2. Reproducibility

A result must be reproducible from:

- Code commit.
- Data version.
- Parameter version.
- Strategy version.
- Schema version.
- Run manifest.

If the exact source data is unavailable, the result must be marked as not fully reproducible.

20.3. Immutable evidence

Never overwrite:

- Failed trial records.
- Published signal identity.
- Original signal parameters.
- Original entry/SL/TP.
- Original decision timestamp.
- Original delivery receipt.

Corrections must be recorded as new events.

---

21. TESTING AND FAILURE INJECTION

21.1. Unit tests

Test:

- Instrument mapping.
- Timestamp conversion.
- Candle validation.
- Data-quality classifications.
- Feature calculations.
- Score calculations.
- Signal states.
- Risk calculations.
- Signal identity.
- Deduplication.
- Expiry.
- Artifact serialization.

21.2. Integration tests

Test:

- L1 export to C++.
- C++ schema validation.
- C++ data admission.
- C++ state generation.
- Artifact publication.
- Telegram outbound delivery.
- Delivery receipt storage.

21.3. Failure injection

Required scenarios:

- Provider timeout.
- HTTP 429.
- HTTP 5xx.
- Invalid schema.
- Missing fields.
- Stale data.
- Duplicate candles.
- Conflicting sources.
- Incorrect instrument mapping.
- Incomplete candle.
- Interrupted process.
- Artifact write failure.
- Telegram send failure.
- Telegram timeout with uncertain receipt.
- Duplicate retry.
- Scheduler overlap.
- Missing secret.
- Resource quota exhaustion.

The expected behavior must be documented for each scenario.

21.4. Mock versus live evidence

Tests must be classified:

- "UNIT"
- "FIXTURE"
- "MOCK"
- "INTEGRATION"
- "LIVE_PROVIDER"
- "LIVE_TELEGRAM"
- "END_TO_END"

Mock tests cannot prove live provider access.

Fixture tests cannot prove real Telegram delivery.

A successful local build cannot prove a clean GitHub Actions build.

21.5. Two consecutive end-to-end runs

Stage 1 requires two consecutive complete end-to-end PASS runs.

Each must demonstrate:

- Real public data acquisition.
- C++ validation.
- Deterministic state output.
- Valid artifact publication.
- Real Telegram outbound receipt.
- Correct failure behavior.
- Resource usage within verified free-tier limits.

These runs establish engineering reliability only.

They do not establish strategy profitability.

---

22. STAGE ROADMAP

Each stage has a defined objective, acceptance criteria, three-layer requirements, SLRP, tests, evidence, and explicit approval gate.

No stage may be skipped.

STAGE 0 — CANONICAL DESIGN AND SOURCE RECONCILIATION

Objective:

Establish one internally consistent master specification and reconcile the actual repository state before implementation.

Required work:

1. Inspect the current repository directly.
2. Identify active branches and current commit.
3. Inspect build configuration and source tree.
4. Inspect CI workflows.
5. Inspect existing data-fetching components.
6. Inspect existing C++ components.
7. Inspect Telegram implementation.
8. Inspect existing tests.
9. Identify incomplete files and duplicate implementations.
10. Compare actual code against this specification.
11. Record architecture gaps.
12. Record unresolved source conflicts.
13. Establish the Stage 1 vertical-slice implementation plan.

Acceptance:

- Master specification has one authority status.
- Source conflicts are recorded.
- Repository baseline is verified.
- No invented implementation claims.
- Stage 1 scope is frozen.
- No destructive cleanup without approval.

L1: Provider and data contract design.
L2: C++ architecture and build design.
L3: Telegram outbound design and message contract.

Stage 0 must not be reported as a code implementation PASS.

STAGE 1 — END-TO-END DATA, COMPUTE AND TELEGRAM VERTICAL SLICE

Objective:

Prove one complete production pipeline using one exact perpetual contract.

Scope:

- One symbol, initially BTC perpetual.
- One real public data source.
- L1 acquisition.
- Versioned schema.
- C++ validation.
- Deterministic status generation.
- Artifact publication.
- Telegram outbound.
- Failure injection.

No strategy engine is required in this stage.

Acceptance:

1. Real public data obtained for the exact perpetual instrument.
2. Provenance and timestamps preserved.
3. L1 schema validated.
4. C++ clean build from a fresh checkout on the actual GitHub Actions runner.
5. C++ independently revalidates L1 output.
6. Invalid or stale data is rejected.
7. Deterministic status artifact generated.
8. Run manifest contains commit, run ID, schema, timestamps, source status, and checksums.
9. Real Telegram outbound message receives a positive API response and message ID.
10. Retry and duplicate prevention tested.
11. Failure injection completed.
12. Actual runtime, memory, request count, and free-tier usage recorded.
13. Two consecutive complete end-to-end runs PASS.

L1: Real data acquisition and export.
L2: C++ validation and deterministic state.
L3: Real Telegram outbound and receipt.

Prohibited Stage 1 scope:

- Scalp.
- 27-contract full-universe production scan.
- LFS/NSS.
- Plan A/B/C/H strategy engines.
- Statistical calibration.
- Backtesting.
- Machine learning.
- Meta-allocator.
- Dashboard.
- Telegram inbound commands.

The one-symbol vertical slice must pass before expansion.

STAGE 2 — LRT 15M AND LFS RESILIENCE

Objective:

Implement and validate the initial LRT 15m engine and its LFS resilience.

Scope:

- Eligible perpetual universe, target 27.
- BTC reference.
- LRT 15m.
- LFS V1.
- LFS V2 and V3 only after real failure.
- Feature definitions.
- Data-quality gates.
- Hypothesis and falsification.
- Signal-state mapping.
- Shadow outcomes.

Potential features:

- Liquidity sweep.
- Equal highs/lows.
- Order Blocks.
- Fair Value Gaps.
- BOS/CHoCH.
- CVD and volume delta where available.
- Funding.
- Open Interest.
- ATR.
- Market structure.
- Ichimoku only when its role is justified and independently tested.

Acceptance:

- Every production feature has a deterministic definition.
- No future information.
- Completed candles only.
- Missing inputs handled explicitly.
- LFS formula is reproducible.
- Golden Rule is implemented as a hard veto.
- Every eligible symbol receives an honest state.
- Shadow outcomes are recorded.
- L1/L2/L3 all pass.

STAGE 3 — TELEGRAM SIGNAL DELIVERY V1

Objective:

Deliver complete, auditable 15m LRT signal messages.

Acceptance:

- Required message fields present.
- Entry/SL/TP/expiry consistent with the artifact.
- Hypothesis and falsification included.
- Data and calibration status visible.
- Chart matches the exact instrument and timeframe when included.
- Telegram receipt recorded.
- Duplicate prevention works.
- Delivery failure does not alter the underlying decision.
- Daily status message is produced.

A minimum number of signals is not required for acceptance.

STAGE 4 — LRT 5M SCALP

Objective:

Develop and test the 5m Scalp profile.

Requirements:

- Completed 5m candles.
- Independent 5m data-quality rules.
- Exact entry and expiry definitions.
- Cost model.
- Latency benchmark.
- Scheduler feasibility.
- Provider quota measurement.
- Shadow-first operation.
- Independent outcome ledger.

The 5m profile remains disabled if free-tier feasibility or data freshness cannot be demonstrated.

STAGE 5 — LRT 1M RESEARCH

Objective:

Evaluate 1m LRT as a research/shadow profile.

Requirements:

- Real data availability.
- Timestamp integrity.
- Measured latency.
- Cost assumptions.
- Independent signal identity.
- Shadow outcomes.
- No production activation without a separate approval gate.

STAGE 6 — CALIBRATION AND META-COGNITION

Objective:

Calibrate signal probabilities and confidence claims.

Requirements:

- Sufficient independent samples.
- Brier Score.
- Reliability curves.
- Base-rate comparison.
- Confidence intervals.
- Calibration drift monitoring.
- Separate calibration by path/profile/generator.
- "UNCALIBRATED" when evidence is insufficient.

STAGE 7 — NMT ENGINE AND NSS RESILIENCE

Objective:

Implement the independent NMT engine.

Requirements:

- NSS V1.
- V2/V3 only after failure.
- 1–7 day horizon.
- Independent features.
- Separate outcome ledger.
- Golden Rule integration.
- Independent validation.
- L1/L2/L3 completion.

STAGE 8 — LIQUIDITY ZONES AND MARKET PHASE

Objective:

Build a deterministic liquidity-zone and phase-classification layer.

Requirements:

- Explicit zone definitions.
- Point-in-time construction.
- Invalidation rules.
- Regime labels.
- Independent tests.
- No future swing-point leakage.
- No unverified order-book claims.

STAGE 9 — PLAN A VALIDATION

Objective:

Validate the complete LRT/NMT dual-engine path.

Acceptance:

Gate_A:

- LRT OOS Win Rate ≥ 55%.
- NMT OOS Win Rate ≥ 45%.
- PF ≥ 1.4.
- MaxDD ≤ 20%.
- PBO < 0.4.

All results must be OOS and cost-adjusted.

STAGE 10 — PLAN B CROSS-SECTIONAL MODEL

Objective:

Implement and validate the six-factor model.

Acceptance:

Gate_B:

- OOS Sharpe ≥ 1.2.
- MaxDD ≤ 20%.
- PBO < 0.4.
- Alpha > 0.

STAGE 11 — PLAN C ROBUST ENSEMBLE

Objective:

Test Donchian, EMA 50/200, and Funding Extreme independently, then test justified ensemble value.

Acceptance:

Gate_C:

- PF ≥ 1.2.
- MaxDD ≤ 25%.
- PBO < 0.5.

Failure activates the Innovation Protocol.

STAGE 12 — PLAN H SIGNAL FACTORY

Objective:

Implement H1–H7 as independent generators.

Acceptance:

- Each generator has its own hypothesis.
- Each generator has its own falsification.
- Each generator has an independent ledger.
- Each generator has independent OOS evidence.
- Each generator meets the 150–200 trade maturity reference.
- Duplicate setup counting is prevented.
- Tier mapping is evidence-based.

STAGE 13 — PAPER TRADING AND SHADOW

Objective:

Evaluate live signal behavior without executing orders.

Reference duration:

30–60 days.

Requirements:

- Immutable signal snapshots.
- Entry validity.
- Expiry.
- Realistic costs.
- Outcome attribution.
- Missed-entry handling.
- Shadow/backtest divergence.
- Regime analysis.
- Independent path reports.

No exchange account or trading execution is permitted.

STAGE 14 — META-ALLOCATOR

Objective:

Evaluate whether independent paths can be allocated across market conditions.

This stage is prohibited until:

- At least 180 days of evidence.
- At least 100 unique trades per path.
- Independent path validation.
- Reliable calibration.
- Stable data quality.
- No unresolved major risk issue.

These are eligibility floors, not proof of statistical sufficiency.

The allocator must never hide an underperforming path.

STAGE 15 — INNOVATION AND FINAL DECISION

Objective:

Perform the final independent review.

Possible outcomes:

- "APPROVED_FOR_CONTINUED_SHADOW"
- "APPROVED_FOR_SIGNAL_PUBLICATION"
- "RESEARCH_ONLY"
- "RESTRICTED_REGIME"
- "REJECTED"
- "HONEST_STOP"

The system must not claim profitability unless the evidence supports that claim.

---

23. STAGE DELIVERY FORMAT

Every stage must produce the following:

1. Short objective summary.
2. V1 implementation.
3. V1 tests.
4. Evidence-based diagnosis if V1 fails.
5. V2 only if V1 fails.
6. V2 tests and diagnosis.
7. V3 only if V2 fails.
8. SLRP report.
9. Real sample output.
10. Five-question self-critique.
11. L1/L2/L3 acceptance result.
12. Explicit handoff decision.

The required self-critique:

1. Was future data used?
2. Were parameters tuned on test data?
3. Were costs included?
4. Does the system report correctly when there is no signal?
5. What is the weakest assumption?

Any unknown answer must be resolved before PASS.

A stage must not advance without owner approval.

---

24. ACCEPTANCE, RELEASE AND ROLLBACK

24.1. Acceptance evidence

A PASS requires:

- Exact commit SHA.
- Test command or workflow reference.
- Actual test output.
- Relevant artifact.
- Failure evidence where applicable.
- Runtime/resource evidence for operational stages.
- L1/L2/L3 result.
- Acceptance checklist.

24.2. Release eligibility

A stage can be released only if:

- Its acceptance criteria pass.
- Its required tests pass.
- No critical unresolved issue remains.
- Its free-tier requirements are verified.
- Its security boundary is preserved.
- Its Telegram behavior is correct.
- Its rollback procedure exists.

24.3. Rollback

Every production change must define:

- Previous known-good version.
- Rollback trigger.
- Artifact restoration.
- Signal-publication disable procedure.
- Data compatibility.
- Telegram status communication.

A rollback must not erase historical signals or trial records.

24.4. No false completion

The following statements are prohibited without direct evidence:

- "The system is live."
- "Telegram is working."
- "The provider fallback is operational."
- "The strategy passed."
- "The project is complete."
- "The system is profitable."
- "The scheduled automation is reliable."

The exact evidence must be supplied.

---

25. PROJECT CONSTITUTION C1–C18

The following constitutional rules are mandatory.

C1 — Statistical Honesty
No performance claim without valid evidence.

C2 — Fail Cheap and Early
Detect invalid assumptions and data failures before expensive computation.

C3 — No Distortion of Limits
Never weaken thresholds or acceptance criteria to force a PASS.

C4 — One Module, One Path
Strategy logic remains isolated by path and generator.

C5 — Hypothesis and Falsification
No signal without a measurable hypothesis and a specific falsification condition.

C6 — Parameter Budget
Maximum five tunable parameters per registered strategy.

C7 — Learning with Gates
Learning and adaptation require validation and promotion gates.

C8 — Maximum Three Rewrite Cycles
No unlimited version rewriting.

C9 — No Secrecy as Value
The project must remain transparent and auditable.

C10 — Daily Report Guarantee
A daily status result is mandatory, not a guaranteed trade.

The seven states are:

- BUY_NOW
- SELL_NOW
- CONDITIONAL_BUY
- CONDITIONAL_SELL
- WATCHLIST
- NO_QUALIFIED_SETUP
- MARKET_DATA_DEGRADED

Relaxing filters to upgrade WATCHLIST into BUY_NOW is a violation.

C11 — SLRP
Every stage defines V1, V2, and V3.

C12 — PROXY/UNAVAILABLE
Missing real data must be labelled. Proxy-based decisions require stricter controls.

C13 — Repository Transparency
No repository access means no claims about repository state.

C14 — Three-Layer Completeness
Every stage must include L1 Data, L2 Compute, and L3 Delivery.

C15 — Zero Cost
Only genuinely free services are permitted.

C16 — Telegram-Only User Delivery
Telegram is the only routine user-facing delivery channel.

C17 — Autonomous Execution
Scheduled backend execution is mandatory, subject to verified infrastructure capacity.

C18 — Manual Trading Only
No trading-account connection or order execution.

---

26. DECISION REGISTER

Every unresolved or amended technical decision must be recorded here.

Initial required entries:

ID| Decision| Status
ADR-001| Official Python L1 acquisition; C++ authoritative L2/L3| OWNER-APPROVED; implementation verification required
ADR-002| Telegram-only user delivery| Owner-directed
ADR-003| No exchange-account connection or order execution| Mandatory
ADR-004| Initial one-symbol Stage 1 vertical slice| Required
ADR-005| Target universe of 27 eligible perpetual contracts| Owner-directed target
ADR-006| Scalp activation in 15m → 5m → 1m research sequence| Owner-directed sequence
ADR-007| Free-tier feasibility must be measured, not assumed| Mandatory
ADR-008| Overlap-safe OOS aggregation| Mandatory
ADR-009| Telegram outbound only in initial delivery| Required
ADR-010| Daily 5–10 signals is a KPI, not a minimum| Owner-directed interpretation

An ADR marked "APPROVED" does not prove implementation.

---

27. OPEN ITEMS — MUST NOT BE FABRICATED

The following items remain open until direct evidence is available:

1. Actual GitHub repository URL and current commit.
2. Actual branch structure.
3. Existing source-tree state.
4. Existing C++ implementation status.
5. Actual C++ compiler and standard compatibility.
6. Existing Python acquisition code and its permitted scope.
7. Actual provider endpoint availability.
8. Actual 27-contract eligibility.
9. Actual historical data coverage.
10. Actual funding and OI coverage.
11. Actual free-tier quota consumption.
12. Actual scheduled-run reliability.
13. Actual Telegram bot configuration.
14. Actual Telegram chat delivery receipt.
15. Actual CI test results.
16. Actual artifact storage and retention.
17. Actual strategy performance.
18. Actual calibration quality.
19. Actual Scalp latency feasibility.
20. Actual independent OOS results.

Every item must remain "NOT_VERIFIED" until evidence is produced.

---

28. FINAL OPERATING DIRECTIVE

The system must be built as a real, testable, autonomous, zero-cost, exchange-independent signal pipeline.

The order of responsibility is:

PUBLIC DATA
    |
    v
L1 ACQUISITION
    |
    v
C++ DATA VALIDATION
    |
    v
INDEPENDENT STRATEGY PATHS
    |
    v
HYPOTHESIS + FALSIFICATION
    |
    v
DATA / CAUSALITY / RISK GATES
    |
    v
SIGNAL STATE
    |
    v
IMMUTABLE ARTIFACT
    |
    v
TELEGRAM OUTBOUND
    |
    v
OUTCOME TRACKING
    |
    v
INDEPENDENT OOS VALIDATION

The project must prioritize implementation and evidence over repeated documentation.

No stage may be declared complete based on a plan, mock, local-only test, or written report.

No stage may be skipped.

No threshold may be relaxed.

No trading execution may be introduced.

No cost may be hidden.

No failed experiment may be erased.

No signal may be fabricated.

No profitability claim may be made without valid evidence.

---

29. OWNER ACCEPTANCE AND ACTIVATION

This document becomes the canonical project source only after explicit owner acceptance.

Upon acceptance:

1. Record the exact accepted document version.
2. Preserve the previous master source as an archive.
3. Verify that the new source opens correctly in the project.
4. Update the active project instructions to point to V19.0.
5. Remove contradictory duplicate instructions only after verifying the replacement.
6. Record the migration date and source fingerprint.
7. Begin Stage 0 repository reconciliation.
8. Stop at the Stage 0 acceptance gate.
9. Obtain owner approval before Stage 1.

Acceptance of this document does not authorize deployment, destructive repository changes, paid services, exchange-account access, or order execution.

DOCUMENT_ID = CFSS-MASTER-SOURCE
DOCUMENT_VERSION = V19.0
DOCUMENT_STATUS = OWNER_ACCEPTED
CANONICAL_ACTIVATION = ACTIVE_BY_EXPLICIT_OWNER_DECISION
OWNER_ACCEPTANCE_DATE = 2026-11-22
PREVIOUS_MASTER = V18.2_ARCHIVED
SOURCE_SHA256_PRE_ACTIVATION = a3a6685a548c07a9f732a5c745412b3d14a01e391d2cf5feaaa8d20a3a33e153

REPOSITORY_STATE = NOT_VERIFIED
CPP_BUILD = NOT_VERIFIED
L1_PROVIDER_ACCESS = NOT_VERIFIED
L2_RUNTIME = NOT_VERIFIED
L3_TELEGRAM_DELIVERY = NOT_VERIFIED
FREE_TIER_FEASIBILITY = NOT_VERIFIED
STRATEGY_PERFORMANCE = NOT_ESTABLISHED
OOS_VALIDATION = NOT_ESTABLISHED
PROFITABILITY = NOT_ESTABLISHED

TRADING_ACCOUNT_ACCESS = PROHIBITED
ORDER_EXECUTION = PROHIBITED
USER_DELIVERY = TELEGRAM_ONLY

END OF MASTER SOURCE V19.0