# MASTER SOURCE V21.0
## Adaptive Auction-State Research & Signal System

**Document ID:** CFSS-MASTER-SOURCE  
**Version:** 21.0  
**Status:** OWNER-DIRECTED ARCHITECTURE PROPOSAL — PENDING EXPLICIT ACCEPTANCE  
**Created:** 2026-11-23  
**Proposed canonical path:** `docs/constitution/MASTER_SOURCE_V21.0.md`  
**Historical predecessor:** V20.0, preserved byte-for-byte under `archive/constitution/V20.0/`  
**Research status:** DESIGN ONLY — NO STRATEGY VALIDATED  
**Trading mode:** Manual decision support only  
**User delivery:** Telegram only, retained from V20 unless explicitly amended  
**Production implementation:** C++ decision/runtime layer; Python research and validation only, retained from V20 unless explicitly amended

---

# 0. AUTHORITY, SCOPE AND HONESTY

## 0.1 Purpose

V21.0 replaces the VTM-centred design philosophy with an open, hypothesis-driven research architecture. Its purpose is to discover and validate a robust market edge across materially different market states, rather than to preserve a preferred indicator, strategy label, timeframe, or legacy implementation.

V21 is not a claim that a profitable strategy has already been found. No strategy is active for production until it passes every hard gate in this document using reproducible out-of-sample evidence.

## 0.2 Authority and transition

1. V20.0 is preserved as historical research and governance evidence. It is not to be silently edited or deleted.
2. V21.0 becomes the controlling source only after explicit owner acceptance.
3. Until acceptance, the repository must label V21.0 as a proposal and must not treat its candidate architecture as production-authorized.
4. No implementation, deployment, strategy activation, or signal publication is authorized merely by committing this document.
5. A commit proves document persistence, not strategy validity, operational readiness, or profitability.
6. The rejected strategies in Section 2 remain quarantined. A new name does not make an old hypothesis new.

## 0.3 Evidence vocabulary

Use only these status labels where applicable:

- `OWNER_DIRECTED`: explicitly requested by the owner.
- `MEASURED`: calculated from identified, reproducible data.
- `HYPOTHESIS`: a falsifiable research proposition, not a result.
- `PROXY`: an approximation that is not the required direct measurement.
- `UNAVAILABLE`: required data or capability is not available.
- `NOT_TESTED`: no test has been executed.
- `NOT_CALIBRATED`: probability estimates are not calibrated.
- `NOT_VALIDATED`: one or more required validation gates failed.
- `BLOCKED`: a named prerequisite prevents valid execution.
- `PASS` / `FAIL`: acceptance outcome supported by inspectable evidence.

No proxy, simulation, fixture, paper result, or historical backtest may be represented as a live fill or guaranteed future performance.

## 0.4 Mission statement

Build a personal, exchange-independent, zero-cost research and signal system that:
- discovers candidate edges without loyalty to a strategy family;
- distinguishes trend, range, transition, and disorderly markets;
- uses separate hypotheses for distinct market states;
- refuses to trade when state or data quality is ambiguous;
- accounts for asymmetric short-side liquidation and squeeze risk;
- measures the true end-to-end latency before enabling any scalp profile;
- reports only signals that pass evidence, risk, and operational gates.

The target is the highest defensible signal quality, not the highest signal count.

---

# 1. THE DOCTRINE — CREATIVE FREEDOM WITH SCIENTIFIC CONTROL

## 1.1 Research freedom

Research may investigate, combine, or reject any analytical family when it has a clear mechanism and testable hypothesis, including:
- trend and volatility expansion;
- pullback continuation and market structure;
- range rotation and statistical mean reversion;
- auction acceptance/rejection and volume-at-price;
- market profile and anchored VWAP;
- Ichimoku and other trend-state representations;
- candle/price action and classical structures;
- order-flow features when real, timestamped data exists;
- funding, open interest, basis, liquidations and derivatives positioning;
- cross-sectional relative strength and market breadth;
- machine learning, only with strict leakage controls and a simple baseline;
- multi-timeframe features, only when every feature is available at the decision timestamp;
- 1m/5m scalp, intraday, daily and swing research profiles.

No method is accepted because it is fashionable, visually persuasive, or associated with a well-known trading style. Every candidate must identify its information source, causal mechanism, falsification condition, and incremental value over a simple baseline.

## 1.2 Research freedom is not production freedom

A research notebook may explore broadly. Production eligibility remains constrained by:
- reproducibility;
- point-in-time data;
- immutable trial registry;
- the hard gates in Section 3;
- zero-cost feasibility;
- measured data freshness and latency;
- manual-only trading;
- no private exchange-account connection;
- Telegram-only user delivery unless explicitly amended.

## 1.3 Core invariants retained from V20

Unless the owner explicitly amends them:
- no paid service may be a required production dependency;
- public market data only;
- no exchange account connection, private trading key, balance access, or order execution;
- C++ is the production decision/runtime language;
- Python is research, data analysis, and validation support only;
- Telegram is the sole routine user delivery channel;
- no signal publication before its strategy and operational release gates pass;
- failed experiments and trial records are immutable and retained.

---

# 2. STRATEGY GRAVEYARD — QUARANTINED HYPOTHESES

These implementations are rejected and must not be reintroduced by renaming, cosmetic feature changes, or parameter retuning. Reconsideration requires a materially different mechanism, a written distinction from the failed hypothesis, and a new pre-registered experiment.

## 2.1 LRT — Liquidity Reversion

**Status:** REJECTED / QUARANTINED.  
**Owner-stated failure rationale:** false breakouts in range conditions and lack of reliable historical order-book access for the tested design.

The tested LRT logic must not be copied into V21 as a sweep-and-reversal engine. A future auction-rejection hypothesis is permissible only if it is materially distinct, does not assume unavailable order-book truth, and proves incremental OOS value.

## 2.2 NMT — Narrative Momentum

**Status:** REJECTED / QUARANTINED.  
**Owner-stated failure rationale:** excessive Probability of Backtest Overfitting (PBO).

No renamed narrative score or loosely defined catalyst basket may bypass this rejection. Any future event-driven research requires timestamped, point-in-time event data, a frozen event taxonomy, and a complete trial registry.

## 2.3 VTM — Volume-Triggered Momentum

**Status:** REJECTED / QUARANTINED.  
**Owner-stated failure evidence:** 36% win rate in the PIT 2023 test, as reported by the owner.

A volume multiplier followed by candle acceptance and breakout must not be reused as the primary signal. Volume may remain a contextual feature in a materially different hypothesis, but it cannot be the trigger renamed as a new engine.

## 2.4 Graveyard integrity

- Preserve the original V20 source and all associated artifacts.
- Do not erase negative trials or failed folds.
- Do not use the graveyard results as proof that every strategy in the same broad family is universally invalid.
- Do not claim a new candidate is independent until its feature overlap, entry logic, exit logic, and causal mechanism have been compared with the rejected implementations.
- A candidate that is substantially the same hypothesis is a repeat and is prohibited.

---

# 3. HARD VALIDATION GATES — NON-NEGOTIABLE

Every strategy/profile must independently satisfy all gates. Results must be net of the registered cost model and computed on strictly out-of-sample trades.

| Gate | Required result |
|---|---:|
| OOS Win Rate | **> 50%** |
| OOS Profit Factor | **> 1.40** |
| PBO | **< 0.40** |
| DSR Z-score | **> 1.00** |
| Look-ahead | **Zero tolerance** |
| Entry timing | Signal after completed bar; fill at next bar Open |
| Fee assumption | **0.04%** |
| Slippage assumption | **0.02%** |

All inequalities are strict. Equality does not pass.

## 3.1 Cost interpretation

The owner supplied fee 0.04% and slippage 0.02%, but did not specify whether these are one-way or round-trip rates. Until explicitly frozen in a run manifest, this ambiguity is a **BLOCKER**.

Conservative research convention proposed for review: apply each rate on every executed side (entry and exit), with additional spread and funding costs where applicable. Do not silently switch between per-side and round-trip interpretations. The final convention must be recorded before any acceptance run.

## 3.2 OOS protocol

- Use chronological, leakage-safe walk-forward evaluation.
- Keep a final untouched holdout that is not used for feature selection, threshold selection, or model choice.
- Purge overlapping labels and apply an embargo where holding periods overlap.
- Use point-in-time universe membership, including delisted/expired instruments when evidence permits.
- Record all candidate trials, including discarded experiments.
- Calculate PBO only from a complete, pre-registered trial matrix and documented partition method.
- Calculate DSR Z with the number of trials and selection process accounted for.
- Report fold-level results and confidence intervals; never report only a pooled headline metric.
- Include realistic funding, spread, slippage, fees, gaps, stop execution and data outages.
- No parameter may be tuned against the final holdout.

## 3.3 Additional release controls

Passing the four performance gates is necessary, not sufficient. A candidate is still blocked by:
- inadequate trade count or confidence interval;
- poor performance concentration in one symbol or one regime;
- unstable fold-to-fold results;
- data coverage or PIT defects;
- missing costs;
- operational latency/freshness failure for its intended timeframe;
- unacceptable drawdown or tail loss;
- uncalibrated confidence presented as probability;
- unresolved implementation parity between research and production.

A strategy must not be promoted because it narrowly passes a pooled metric while failing materially in individual folds or market states.

---

# 4. PROPOSED ARCHITECTURE — ADAPTIVE AUCTION-STATE SYSTEM (AASS)

**Status:** HYPOTHESIS / DESIGN CANDIDATE — NOT TESTED.

V21 proposes a regime-routed architecture rather than a single indicator stack. A market-state classifier decides which independent hypothesis, if any, is eligible. The router does not generate a trade by itself.

## 4.1 State router

The initial state taxonomy is:

1. `TREND_UP`
2. `TREND_DOWN`
3. `BALANCED_RANGE`
4. `VOLATILITY_TRANSITION`
5. `DISORDERLY`
6. `UNKNOWN_DATA`

The router must use causal, completed-bar features. Candidate inputs:
- directional efficiency / path efficiency;
- rolling return slope and persistence;
- realized volatility and volatility percentile;
- range compression/expansion;
- overlap and close-location statistics;
- cross-sectional breadth;
- BTC market state as a contextual variable, not an absolute veto unless independently justified.

Initial classifier families may include transparent threshold rules and a regularized probabilistic classifier. The simpler classifier is the baseline. A complex model must demonstrate statistically significant incremental OOS value.

No regime label is allowed to use future swing confirmation, future volatility, revised historical membership, or a feature calculated with data that was not available at the decision timestamp.

## 4.2 Independent engine families

### Engine T — Trend Acceptance and Pullback Continuation

**Hypothesis:** In a persistent directional state, a controlled pullback that preserves directional structure and then re-establishes acceptance may offer better continuation expectancy than buying the initial breakout.

Candidate inputs:
- trend persistence and directional efficiency;
- slope stability;
- pullback depth relative to ATR;
- close location and acceptance after pullback;
- volatility expansion relative to the preceding compression;
- relative strength versus BTC and the eligible universe.

This engine is not VTM: abnormal volume is not its primary trigger, and a simple volume-spike-plus-breakout rule is prohibited.

### Engine R — Balanced Auction Rotation

**Hypothesis:** In a genuinely balanced range, price excursions away from a stable value estimate may revert toward value when the auction fails to establish acceptance outside the range.

Candidate inputs:
- robust rolling value estimate;
- range stability and overlap;
- normalized distance from value;
- rejection/acceptance measured only from completed OHLCV bars;
- volatility and spread suitability.

This engine is not LRT: it must not depend on unverified liquidity sweeps, equal-high/low stop hunts, or historical order-book depth. Candle-derived volume-at-price is labelled `PROXY`, never presented as exchange-native volume profile.

### Engine X — Transition / No-Trade Detector

**Hypothesis:** The most damaging losses often occur when a market changes state and neither trend continuation nor range rotation has a stable edge.

This engine primarily blocks entries. It may issue a conditional watch state when a transition resolves, but it must not force a directional signal. `DISORDERLY` and `UNKNOWN_DATA` are no-trade states.

## 4.3 Strategy isolation

Each engine must have:
- its own hypothesis and falsification;
- independent feature contract;
- independent parameters (maximum five tunable parameters per registered strategy);
- independent trial registry;
- independent signal/outcome ledger;
- independent OOS report;
- independent cost and risk attribution.

The state router may select an engine but may not blend its score with engine scores to conceal a failed path. Meta-allocation is prohibited until each engine independently passes.

---

# 5. SHORT-SQUEEZE AND CROWDING DEFENCE

Short risk is asymmetric. A short may be directionally correct and still be liquidated by a fast upward squeeze. V21 therefore treats short eligibility as a separate risk decision, not a mirror image of long eligibility.

## 5.1 Crowding and squeeze-risk inputs

Use only public, timestamped data where available:
- perpetual funding rate and its rolling percentile;
- open-interest level and change;
- price change aligned with OI change;
- mark/index basis and premium;
- public liquidation events, where the provider exposes them;
- spread, depth and top-of-book imbalance from live public streams;
- realized volatility and gap risk;
- BTC and broad-market impulse.

Interpretation must be explicit. For example, persistently negative funding can indicate crowded short positioning; rising price with falling OI may be consistent with short covering. Neither condition alone proves a squeeze.

## 5.2 Squeeze-risk gate

A short candidate must be blocked or reduced when:
- crowding measures exceed pre-registered rolling thresholds;
- funding is strongly negative and positioning is crowded;
- price rises while OI falls sharply, consistent with short-covering pressure;
- upward volatility expansion or a liquidation impulse is detected;
- spread/depth quality is inadequate;
- funding, OI, or critical timestamp data is stale or unavailable.

Thresholds must be estimated on training data only, frozen before OOS, and evaluated for false blocks and missed squeezes. Missing critical inputs produce `SHORT_DISABLED`, not an optimistic neutral score.

## 5.3 Execution and portfolio protections

- No averaging up into a losing short.
- No martingale or unbounded add-on.
- Hard invalidation stop and maximum loss budget per trade.
- Position size reduced as squeeze risk rises.
- Maximum portfolio short exposure and correlated short exposure.
- Gap-through-stop stress test; a stop is not guaranteed to fill at its trigger.
- Emergency no-new-short state during data degradation or abnormal market dislocation.

A squeeze-risk model is a defence layer, not a guarantee against liquidation or gaps.

---

# 6. DATA DOCTRINE AND PROVIDER DESIGN

## 6.1 Public-data-only rule

The system uses public market data. It must never request or store private exchange API keys, connect to private account streams, read balances/positions, or place orders.

## 6.2 Data hierarchy

- **Historical baseline:** Binance Vision archives where the required product, interval, symbol and date are present and verifiable.
- **Live market stream:** official public WebSocket market streams where accessible and stable.
- **REST repair/reference:** public market-data endpoints, used with documented request budgets.
- **Independent cross-check:** another public provider/exchange only when the field semantics and timestamps can be reconciled.
- **Fallback:** never silently splice incompatible feeds. Every source switch creates a provenance event and a quality state.

A source is not accepted merely because it returns HTTP 200. Validate symbol identity, contract type, timestamps, units, duplicate events, sequence gaps, missing intervals, checksum/archive integrity and revisions.

## 6.3 Field-level quality

Every feature must declare:
- source and endpoint;
- field name and unit;
- event time and receive time;
- update cadence;
- availability start date;
- known revisions or limitations;
- missing-data policy;
- whether it is direct, derived, or PROXY.

Order-book imbalance cannot be backfilled from OHLCV. Liquidation flow cannot be inferred from candle volume. Historical OI/funding cannot be assumed complete without evidence.

## 6.4 Point-in-time universe

Universe membership must be reconstructed for each historical decision date. Current survivors are not a valid historical universe. Delisted, renamed and expired contracts must be retained when historical evidence exists. Unknown contract lifecycle is labelled `PROXY` and blocks claims of exact PIT validity.

---

# 7. SCALP PROFILE — LATENCY IS A MEASURED GATE

## 7.1 Feasibility statement

Public WebSocket feeds can deliver market events faster than periodic REST polling, but a public feed does not guarantee low end-to-end signal latency. Exchange matching-engine latency, network route, host location, scheduling, processing, Telegram delivery, and regional reachability are separate components.

GitHub Actions cron is suitable for periodic research/reporting, not a continuous 1m/5m market-data collector. A scalp profile cannot be declared operational on the basis of a successful cron run or a WebSocket connection test.

## 7.2 Required latency measurements

Record, per event and per symbol:
- exchange event timestamp;
- local receive timestamp;
- feature-computation start/end;
- decision timestamp;
- signal-publication request timestamp;
- Telegram acknowledgement timestamp;
- reconnect and sequence-gap intervals.

Report p50, p95 and p99 latency, stale-event ratio, missing-event ratio, reconnect frequency, uptime and resource consumption. Synchronize clocks and document clock error.

## 7.3 Proposed scalp activation gates

These are engineering targets for evaluation, not claims of current capability:
- p95 event-to-decision latency <= 1 second;
- p99 event-to-decision latency <= 2 seconds;
- stale/missing event ratio < 0.1% during the measured test window;
- >= 99.5% feed availability over a 30-day shadow test;
- successful reconnect and sequence-gap recovery tests;
- full cost-adjusted OOS gates in Section 3;
- measured Telegram delivery latency reported separately and not confused with market-data latency.

If the free hosting/runtime cannot maintain a continuous collector within verified free-tier limits, the scalp profile remains `RESEARCH_ONLY` or `DISABLED`. No paid dependency may be introduced to force a PASS.

## 7.4 Timeframe priority

Research may compare 1m, 5m, 15m, 1h, 4h and 1D. Production timeframe is selected only after evidence. Lower timeframe does not automatically mean more opportunity; it increases noise, turnover, cost sensitivity and operational burden.

---

# 8. RISK, SIGNAL AND DELIVERY CONTRACT

## 8.1 Risk

- Position sizing must be based on stop distance, portfolio exposure, volatility and liquidity.
- Per-trade, daily, weekly and portfolio drawdown limits must be explicit before validation.
- Correlated positions must be aggregated by common risk factor.
- Stress tests must include gaps, funding spikes, spread widening, partial fills and stop slippage.
- A risk veto cannot be overridden by a high strategy score.
- No Kelly sizing until calibrated, statistically adequate evidence and explicit owner approval.

## 8.2 Signal states

Every symbol must receive an honest state, including no-trade and degraded-data cases. Proposed V21 state vocabulary:
- `LONG_CANDIDATE`
- `SHORT_CANDIDATE`
- `CONDITIONAL_LONG`
- `CONDITIONAL_SHORT`
- `WATCH`
- `NO_QUALIFIED_SETUP`
- `REGIME_TRANSITION`
- `SHORT_DISABLED`
- `MARKET_DATA_DEGRADED`

A candidate is not a trade instruction. Every signal must include hypothesis, falsification, entry timestamp/price convention, invalidation, risk, expiry, costs, data quality, regime, calibration state and evidence version.

## 8.3 Delivery

Telegram remains the sole routine user-facing channel unless explicitly amended. The user manually decides whether to trade. No exchange order execution or account connection is permitted.

Delivery failure must not change the underlying signal decision. Messages require deduplication, immutable identity, retry safety and delivery receipts. Do not publish a signal if its underlying strategy has not passed the release gates.

---

# 9. IMPLEMENTATION AND THREE-LAYER REQUIREMENT

Every implementation stage must include all layers.

**L1 — DATA**
- public archive/live ingestion;
- point-in-time universe;
- schema and provenance;
- freshness, completeness and quality checks;
- raw immutable snapshots and checksums.

**L2 — COMPUTE**
- state router;
- independent strategy engines;
- squeeze-risk gate;
- portfolio risk;
- deterministic signal state;
- walk-forward/PBO/DSR/cost validation;
- C++ production parity with research definitions.

**L3 — DELIVERY**
- Telegram-only publication;
- immutable signal artifact;
- deduplication and delivery receipt;
- outcome tracking and no-signal daily status;
- clear degraded-data and disabled-strategy notices.

No stage passes with only a notebook, a data dump, a dashboard, a mock message, or unit tests.

---

# 10. VALIDATION, BASELINES AND ANTI-OVERFITTING

## 10.1 Required baselines

At minimum, compare each candidate against:
- Buy & Hold on the same point-in-time universe;
- simple moving-average trend baseline;
- simple range/mean-reversion baseline;
- no-trade/cash baseline.

Baselines must use the same dates, universe, execution timing, costs and risk constraints.

## 10.2 Statistical reporting

For every engine/profile, report OOS only:
- Win Rate, Profit Factor, expectancy and average win/loss;
- Sharpe and DSR Z-score;
- PBO with complete trial registry;
- max drawdown and tail loss;
- turnover, holding period and cost decomposition;
- fold-level and regime-level performance;
- symbol concentration and correlation;
- Brier score and reliability curve if probabilities are emitted;
- trade count and confidence intervals.

Do not report a probability/confidence value as calibrated until the calibration test passes.

## 10.3 Falsification

Every candidate must state before testing:
- measurable hypothesis;
- exact feature definitions and timestamps;
- specific falsification condition;
- expected mechanism;
- failure regimes;
- comparison baseline;
- primary metric and statistical test;
- all parameter/feature trials.

If the candidate fails, record the failure and diagnosis. Do not tune on the failed OOS set and rerun it as if it were untouched.

---

# 11. STAGED ROADMAP — NO IMPLEMENTATION IN THIS DOCUMENT COMMIT

**Stage 0 — Architecture and source acceptance**
- Review and accept V21.
- Freeze the proposed AASS definitions and unresolved assumptions.
- Confirm data contracts, runtime constraints, and security invariants.

**Stage 1 — Data truth and observability**
- PIT universe, OHLCV, funding, OI and public stream coverage.
- Data lineage, freshness, completeness, timestamp and symbol identity.
- No strategy implementation until data acceptance.

**Stage 2 — State-router research**
- Transparent baseline classifier.
- Trend/range/transition/disorderly classification.
- Regime-label stability, lag and confusion matrix.
- No trading signals.

**Stage 3 — Independent engine research**
- Engine T and Engine R separately.
- Engine X as no-trade/transition control.
- One hypothesis at a time; immutable trial registry.

**Stage 4 — Short-risk defence**
- Crowding and squeeze-risk feature validation.
- False-block/missed-squeeze analysis.
- Short-disabled behavior when data is unavailable.

**Stage 5 — Risk, cost and calibration**
- Portfolio exposure, stops, sizing, stress tests.
- Fee/slippage interpretation frozen.
- Probability calibration only if sample sufficiency exists.

**Stage 6 — OOS and robustness**
- Walk-forward, untouched holdout, PBO, DSR and cost gates.
- Each engine independently PASS/FAIL.
- No engine blending to hide failure.

**Stage 7 — Shadow operation**
- Immutable signals and outcome ledger.
- Live data freshness and drift monitoring.
- No orders, no exchange-account connection.

**Stage 8 — Scalp feasibility**
- Continuous public WebSocket collector only if free-tier hosting is verified.
- 30-day latency/availability shadow measurement.
- Separate approval before any scalp production profile.

**Stage 9 — Production eligibility review**
- C++ parity, CI, security, operational evidence and Telegram delivery.
- Explicit owner approval required.

Every stage must define v1/v2/v3, numeric acceptance criteria, diagnosis, escalation, and a maximum of three versions. A later version is built only after an evidenced failure of the previous version. No stage advances without explicit owner approval.

---

# 12. SECURITY, COST AND OPERATING CONSTRAINTS

- Zero-cost services only; free-tier limits must be measured and documented.
- No paid trial may be treated as a free production dependency.
- No private exchange API keys or account connections.
- No order execution, copy trading, or automated position management.
- Public data only.
- No hidden paid fallback.
- No claim of guaranteed profit or guaranteed signal accuracy.
- No strategy publication before all gates pass.
- If a free-tier limitation makes the required service unreliable, disable that profile instead of concealing the limitation.

---

# 13. OPEN DECISIONS — MUST BE FROZEN BEFORE ACCEPTANCE TESTS

1. Exact fee/slippage interpretation: per side or round trip.
2. Exact eligible exchange products and historical contract lifecycle evidence.
3. State-router features, lookbacks, thresholds and calibration method.
4. Engine T and Engine R exact mathematical definitions.
5. Exact funding/OI/liquidation provider fields, update cadence and historical coverage.
6. Short squeeze thresholds and risk response.
7. Risk budget, portfolio caps and drawdown kill switches.
8. Exact walk-forward windows, purge and embargo rules.
9. Trial-matrix design for PBO and trial-count handling for DSR.
10. Runtime capable of continuous WebSocket ingestion within zero-cost constraints.
11. Telegram latency expectations and delivery service-level target.
12. C++/Python feature parity and schema version.

No item may be guessed. Unresolved items block the corresponding test or release.

---

# 14. ACCEPTANCE AND FINAL OPERATING DIRECTIVE

V21.0 is a design constitution, not a validated strategy.

The acceptance sequence is:
1. Owner reviews the complete V21.0 document.
2. Owner explicitly accepts or requests amendments.
3. The accepted SHA and effective date are recorded.
4. Only then may Stage 0 implementation planning begin.
5. No strategy code, backtest, deployment, or signal publication is authorized by the document-creation commit alone.

The system's duty is to find and preserve a real edge if one exists, and to report honestly if none survives the gates.

**DOCUMENT_ID:** CFSS-MASTER-SOURCE  
**DOCUMENT_VERSION:** V21.0  
**DOCUMENT_STATUS:** OWNER_DIRECTED_ARCHITECTURE_PROPOSAL_PENDING_ACCEPTANCE  
**PREVIOUS_SOURCE:** V20.0_ARCHIVED_BYTE_FOR_BYTE  
**STRATEGY_VALIDATION:** NOT_TESTED  
**PRODUCTION_AUTHORIZATION:** NOT_GRANTED  
**PROFITABILITY:** NOT_ESTABLISHED  
**TRADING_ACCOUNT_ACCESS:** PROHIBITED  
**ORDER_EXECUTION:** PROHIBITED  
**USER_DELIVERY:** TELEGRAM_ONLY_PENDING_OWNER_AMENDMENT

**Official technical references reviewed for the design (verify again before implementation):**
- Binance USDⓈ-M Futures market streams: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
- Binance public market-data stream overview: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
- Bybit V5 public WebSocket connection: https://bybit-exchange.github.io/docs/v5/ws/connect
- Bybit V5 rate limits: https://bybit-exchange.github.io/docs/v5/rate-limit

**END OF MASTER SOURCE V21.0**
