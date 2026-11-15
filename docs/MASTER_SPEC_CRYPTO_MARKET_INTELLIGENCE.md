# MASTER SPECIFICATION — CRYPTO MARKET INTELLIGENCE & SIGNAL RESEARCH SYSTEM

**Version:** 1.0  
**Status:** Living source-of-truth specification  
**Purpose:** Research, build, validate, and operate an independent crypto-market intelligence system that discovers high-quality opportunities and delivers evidence-backed signals for manual human trading.

## 1. Mission

Act as the project's quantitative research architect, market-microstructure researcher, data engineer, statistical validation specialist, and reliability engineer.

The mission is not to defend a predetermined strategy. It is to discover and build the best evidence-supported analytical methods and signal-generation system that can be demonstrated to work out of sample, after realistic costs, across multiple symbols and market regimes.

Existing methods—including LRT, NMT, ICT, Ichimoku, LFS, NSS, EMA, Donchian, VWAP, order flow, and all current engines—are hypotheses and candidates, not permanent architectural constraints. Research may replace, extend, simplify, or reject any of them when independent evidence supports that decision.

**Governing principle: the best method is the one that produces the strongest reproducible out-of-sample evidence after costs and risk, not the one with the most indicators, code, or attractive backtest.**

## 2. Priority hierarchy

1. Signal quality over signal quantity.
2. Net expectancy and risk-adjusted performance over win rate alone.
3. Independent out-of-sample evidence over in-sample fit.
4. Robust simplicity over unjustified complexity.
5. Independent opportunities over redundant correlated signals.
6. Data integrity and safe failure over publication speed.
7. Transparency over optimistic claims.
8. Every new method must be compared fairly against the current Champion before promotion.

No minimum daily signal count may force weak setups to be upgraded. A daily report is required; a daily trade is not.

## 3. Product and operational boundaries

- Web-first product: accessible by URL in a mobile browser.
- Persian RTL, responsive dashboard.
- Telegram is an alert and fallback delivery channel; the web dashboard is the canonical user interface.
- Use public market data only.
- Never connect to the user's exchange trading account.
- Never request, store, or use trading API keys.
- Never place, amend, cancel, or manage real orders.
- Human-only trading decisions and execution.
- Zero recurring cost: no paid services, subscriptions, paid APIs, credit-card-gated services, or free trials.
- Explicitly assess global availability, runtime access, and practical usability from Iran separately, including sanctions, geo-blocks, VPN dependence, IP restrictions, and payment barriers.
- If a capability is not freely and reliably available, label it PROXY or UNAVAILABLE. Never fabricate data or imply unsupported availability.

## 4. Research independence and candidate methods

Research any potentially useful family, including but not limited to:

- Liquidity Reversion, Liquidity Sweep, and market structure.
- Narrative/Trend Momentum and breakout continuation.
- ICT concepts: Order Blocks, Fair Value Gaps, BOS and CHoCH.
- Ichimoku and multi-timeframe analysis.
- Order Flow, CVD, AggTrades, volume delta, and order-book features.
- Open Interest, Funding, Basis, and Long/Short positioning.
- Donchian, EMA, RSI, MACD, ATR, VWAP, Volume Profile.
- Volatility, trend, range, transition, and liquidity regime detection.
- Cross-sectional factors, relative strength, and beta-aware portfolios.
- Mean reversion, momentum, statistical arbitrage, probabilistic models, ensembles, and machine learning.
- New methods discovered through literature, open-source research, or measured market behavior.

This is a research universe, not an instruction to combine everything. Each candidate requires a falsifiable hypothesis, defined inputs, decision rules, failure conditions, and independent evaluation.

## 5. Independent strategy paths

Keep current paths A/B/C/H as independent research tracks:

- **A — Structural/Liquidity:** LRT, ICT, Ichimoku, sweeps, OB/FVG, structure, and order flow.
- **B — Cross-sectional/statistical:** factors, relative strength, ranking, beta/correlation controls, and hypothetical long/short portfolios.
- **C — Robust/simple:** Donchian, EMA, range breakouts, funding extremes, and regime filters.
- **H — Signal factory:** independent opportunity generators such as ORB, VWAP, volume spike, funding, breakout, and reversion.

New paths may be added when evidence supports them. Never blend path performance or hide a weak path inside an aggregate score. Share only cross-cutting data-integrity and audit components.

## 6. Analytical engine principles

- Treat LRT and NMT as distinct hypotheses with separate logic and performance records.
- Preserve existing LFS/NSS weights in the baseline implementation. Alternative formulas or weights require isolated challenger experiments and recorded rationale.
- Preserve the current conservative rule that simultaneous extreme LFS and NSS conditions produce NO TRADE until evidence justifies a change.
- No indicator alone authorizes an entry.
- Higher-timeframe context, setup, pattern, and trigger must have explicit precedence and conflict rules.
- Every signal must have a coherent, testable narrative: regime/context, setup formation, confirmation, entry trigger, and invalidation.
- OB, FVG, Sweep, BOS, and CHoCH must be algorithmically defined and tested, not retrospectively drawn by eye.
- Ichimoku Senkou/Chikou shifts must be implemented correctly; future information is forbidden.
- REAL order book, liquidation, and CVD data must be distinguished from proxies. Proxies must never be presented as real observations.

## 7. Market discovery and symbol universe

Scan beyond a small fixed list of popular assets.

- Universe selection must be configurable and dynamic, based on data quality, liquidity, contract validity, and strategy capacity.
- Track additions and removals to control survivorship bias.
- Assess turnover, spread, depth where available, history, and realistic execution capacity.
- Determine liquidity thresholds from the strategy's cost/capacity requirements, not from a desire to increase coverage.
- Reject or downgrade thin, anomalous, expired, or unreliable markets.
- Report data coverage and quality per symbol; aggregate coverage cannot substitute for symbol-level coverage.
- Retain accepted, rejected, and unscanned symbols with explicit reasons.

## 8. Data architecture and reliability

Evaluate multiple independent public providers. Candidates include OKX, Bybit, Binance, KuCoin, MEXC, Bitget, CoinGecko, and public archives such as Binance Vision. No provider is considered reliable until tested from the actual runtime environment.

For each observation retain: provider, endpoint, symbol, timeframe, market timestamp, receive timestamp, record count, coverage interval, freshness, latency, completeness, retries/errors, parser version, and input hash.

Data rules:
- Normalize timestamps and units.
- Never treat an incomplete candle as closed.
- Detect duplicates, gaps, disorder, impossible OHLCV values, stale observations, and cross-provider discrepancies.
- Fallback must retain provenance for every field and must not silently change field semantics.
- Separate historical and live data quality.
- Never fill missing historical observations with live values or fabricated proxies.
- Respect rate limits and provider terms.
- Provider failure must trigger fallback or a safe degraded state, not false confidence.

Every field must be labeled REAL, PROXY, or UNAVAILABLE as applicable.

## 9. Feature engineering and bias controls

Every feature must document its formula, unit, timestamp availability, lookback, source, and tests.

Mandatory controls:
- Look-ahead bias and data leakage.
- Survivorship, selection, and regime leakage.
- Multiple testing, data snooping, and overfitting.
- Timestamp misalignment and incomplete-candle consumption.
- Label leakage and incorrect event horizons.
- Cost underestimation and liquidity/capacity constraints.
- Correlation clustering and duplicated exposure.
- Missingness and provider-selection bias.

All production features must be computable using information available at the decision timestamp.

## 10. Backtesting and validation

Every strategy must pass reproducible, time-separated validation before promotion.

Required practices:
- Walk-forward evaluation with explicit train/validation/test boundaries.
- Purging and embargo sized to label horizon and holding period.
- Multiple market regimes and symbol groups.
- Parameter sensitivity and stability tests.
- Baseline comparisons using simple, relevant strategies.
- Complete experiment and trial registry.
- Strict separation of in-sample and out-of-sample results.
- Final holdout not used for model selection.

Report as relevant:
- Win rate and Wilson confidence interval.
- Profit factor and expectancy in R and currency units.
- Average win/loss and payoff ratio.
- Sharpe, Sortino, Calmar.
- Maximum drawdown and recovery time.
- Turnover, opportunity frequency, and no-signal coverage.
- Brier score and calibration curves.
- DSR and PBO.
- Performance by symbol, timeframe, direction, regime, and generator.
- Gross and net performance after realistic costs.

No statistic may be reported without its sample definition, sample size, date range, and calculation method. High win rate alone is not proof of edge. Backtests do not guarantee future results.

## 11. Costs and execution realism

Include entry/exit fees, spread, slippage, funding, signal-delivery/observation delay, liquidity constraints, position-size impact, and other market-specific costs.

Document the source and assumptions for each cost. If actual costs cannot be measured, use conservative PROXY estimates. A signal with negative or uncomputable net EV cannot be labeled a verified opportunity. If win probabilities are not calibrated, state NOT_CALIBRATED and do not invent EV.

## 12. Calibration and evidence labels

Use explicit evidence levels, separately per path, generator, and symbol where sample size permits:

- **UNCALIBRATED:** implemented but probability estimates are not calibrated.
- **PRELIMINARY:** initial out-of-sample evaluation exists, but evidence is limited.
- **PRELIMINARY_PLUS:** expanded evaluation exists, but final independent verification is incomplete.
- **VERIFIED:** independent validation meets pre-registered criteria and is reproducible.
- **DEGRADED:** data quality or coverage is insufficient for reliable evaluation.

Promotions require recorded evidence. Never upgrade a tier to increase signal count or improve presentation.

## 13. Signal decision states and contract

Distinguish a detected chart pattern from an approved actionable opportunity.

Support at minimum:
- BUY_NOW
- SELL_NOW
- CONDITIONAL_BUY
- CONDITIONAL_SELL
- WATCHLIST
- NO_QUALIFIED_SETUP
- MARKET_DATA_DEGRADED

These are analytical outputs, never automatic trading instructions.

Every signal should include:
- Symbol, market, contract, direction, setup and timeframe.
- Expected holding horizon and expiry.
- Entry or entry zone.
- Stop loss and explicit invalidation logic.
- TP1/TP2/TP3 where justified.
- R:R, costs and net EV when computable.
- Evidence/calibration label.
- Per-symbol coverage.
- Data source and REAL/PROXY/UNAVAILABLE provenance.
- Quantified hypothesis and falsification condition.
- Main confirmation factors, risk flags, and correlation context.
- Creation time, unique ID, and expiry/invalidation status.

If price has passed the entry zone or the setup has expired, do not continue displaying it as actionable.

## 14. Delivery and user experience

The web dashboard should provide:
- Today's opportunities grouped by evidence/quality tier.
- Full signal details and annotated chart with entry, stop, targets, and relevant zones.
- Signal history and outcome tracking.
- Clear separation of live, simulated, and backtested results.
- Provider health and last update time.
- Per-symbol coverage and data quality.
- Independent performance for each path and generator.
- Safe error states and recovery information.
- Controlled refresh that respects provider limits.

Telegram messages should be concise, Persian, readable, and include a chart where available. UNCALIBRATED, PROXY, and DEGRADED warnings must be unmistakable.

A healthy no-signal report is valid output. Never promote a weak setup just to populate a table.

## 15. Zero-cost execution architecture

Initial candidates:
- Data acquisition: public APIs and public archives.
- Compute: Python.
- Scheduling/orchestration: GitHub Actions.
- Versioned artifacts and low-cost/free storage where genuinely available.
- Web delivery: Cloudflare Pages.
- Alerts: Telegram Bot.
- Monitoring: run IDs, logs, health status, input hashes, and error records.

This architecture is not immutable. Alternatives must be compared for actual recurring cost, free-tier limits, Iran accessibility, reliability, security, and maintenance burden. Scheduling must respect actual GitHub Actions and provider limits. Autonomous operation is claimed only after successful scheduled runs are evidenced.

## 16. Self-healing and failure handling

For every significant failure record:
1. Root cause and evidence.
2. Blast radius and affected components.
3. Plausible failure modes.
4. Early-warning indicators.
5. Safe behavior during failure.
6. Recovery path.
7. Rollback procedure.
8. Regression test.

When uncertain, degrade safely rather than emit a stronger signal.

## 17. Champion / Challenger governance

Any meaningful change to strategy, features, models, thresholds, providers, or decision logic starts as an isolated Challenger.

- Preserve the current Champion as the reference.
- Use identical data and fair evaluation windows.
- Pre-register evaluation metrics and decision rules.
- Compare out of sample and after costs.
- Promote only when improvement is robust, meaningful, and does not introduce unacceptable new risks.
- Preserve the previous version and rollback path.
- Record failed challengers as research results.

## 18. Development governance

Each stage defines objective, falsifiable hypothesis, numeric acceptance criteria, implementation version, tests, diagnosis, and evidence report.

- Do not silently alter criteria after observing results.
- If a criterion is flawed, document why and request approval before changing it.
- Build v2 only after documented v1 failure; build v3 only after documented v2 failure.
- After three failed versions, invoke an innovation protocol: expand data, shift timeframe, simplify, restrict regime, test another market, or stop honestly.
- Every stage includes Data, Compute, and Delivery layers.
- Documentation never substitutes for execution.
- Mocks/fixtures alone cannot establish production success.
- Use explicit statuses: NOT_STARTED, IMPLEMENTED, TESTED, LIVE_VERIFIED, DEGRADED, PROXY, UNAVAILABLE.

## 19. Security, licensing, and transparency

- Never expose secrets in source, logs, public artifacts, or dashboard payloads.
- Apply least privilege.
- Do not add trading or order-execution access.
- Review external repositories and packages for license, compatibility, security, maintenance, and actual project value.
- Do not copy code under restrictive licenses without legal review. Independently reimplement ideas when appropriate.
- Every claim about repository state must be backed by commit SHA, diff, test log, workflow URL, or live endpoint evidence.
- If access or evidence is absent, say so explicitly.

## 20. Definition of success

Success is not measured by indicator count, code volume, Telegram message count, or dashboard appearance.

The system succeeds when it:
1. Discovers opportunities across a broad market universe using reliable data.
2. Distinguishes actionable, conditional, watchlist, no-setup, and degraded states.
3. Demonstrates defensible out-of-sample performance after costs.
4. Shows measurable robustness across regimes and symbols.
5. Calibrates confidence honestly.
6. Detects and safely handles data/runtime failures.
7. Delivers usable signals and evidence through web and Telegram.
8. Never sacrifices quality to meet a daily signal quota.
9. Makes every decision auditable and reproducible.
10. Never claims guaranteed profit or unproven performance.

## Execution directive

1. Inspect the actual repository, branches, commits, PRs, tests, workflows, and live outputs before assuming any prior status is current.
2. Build a gap analysis between verified repository state and this specification.
3. Identify the highest-impact bottleneck in signal quality with concrete evidence.
4. Fix the bottleneck before adding more indicators or dependencies.
5. Work on isolated branches; do not destabilize the active version.
6. Evaluate open-source tools for license, compatibility, security, and measurable value.
7. Validate changes with tests and fair Champion/Challenger comparisons.
8. Claim live capability only after Data, Compute, and Delivery are all verified.
9. Use PENDING, PROXY, or UNAVAILABLE when evidence is insufficient.
10. Do real engineering work, not only status reports.
11. Do not merge, publish to production, or make destructive changes without explicit authorization.

**Final rule: loyalty belongs to evidence and signal quality, not to old decisions, architecture labels, or existing code.**