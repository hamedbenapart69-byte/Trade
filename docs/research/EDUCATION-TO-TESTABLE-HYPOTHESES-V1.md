# Trading Education Research: Evidence-to-Test Specification (V1)

**Status:** Research specification only. No strategy edge is established by this document.  
**Target repository:** `hamedbenapart69-byte/Trade`  
**Isolation:** `research/education-ohlcv-prototypes-v1`; no production or main-branch changes.  
**Date:** 2026-11-10

## 1. Scope and evidence standard

This document converts publicly documented educational frameworks into falsifiable research hypotheses for the Trade system. It is not a claim that every video lesson has been watched or transcribed.

### Source-access disclosure

The following public instructor/course pages and curriculum descriptions were reviewed:
- Andrea Cimitan, Complete Order Flow Masterclass (17 lessons): https://www.chartacademy.com/masterclass/order-flow
- Carmine Rosato, Order Flow Strategy (8 lessons): https://www.chartacademy.com/masterclass/order-flow-strategy
- Fabio Valentini, Complete Order Flow Trading System (5 lessons): https://www.chartacademy.com/masterclass/complete-order-flow-trading-system
- FuturesTrader71 resources and webinar index: https://www.linnsoft.com/ft71
- Al Brooks course index and public educational pages: https://www.brookstradingcourse.com/trade-price-action/
- Trader Mayne public site: https://www.tradermayne.com/home
- Follis / Kraken public market-analysis page: https://www.kraken.com/gb/follis
- SMB Training free-content index: https://support.smbtraining.com/support/solutions/articles/44002792399-does-smb-training-offer-any-free-content

**Not verified:** Full video playback/transcripts for every lesson, paid/private course material, instructor account statements, and independent audited performance of the methods. The vidIQ transcript endpoint costs 5 credits per call; no paid credits were spent or authorized. Therefore, statements below are limited to public curriculum/page descriptions and general testable interpretations. No transcript-derived quotations are claimed.

## 2. Cross-source synthesis

### Convergent ideas

1. **Context before trigger.** Fabio's Direction–Location–Aggression and Carmine's Context–Location–Confirmation both require market context and a meaningful location before an entry trigger.
2. **Auction state matters.** Fabio and FuturesTrader71 emphasize balance/imbalance, volume profile, and auction behavior. This maps naturally to regime classification and value-area acceptance/rejection.
3. **Aggression alone is insufficient.** Order-flow information becomes meaningful when interpreted at a pre-defined level and alongside price response. An isolated delta/volume spike is not a trade.
4. **Failed attempts are informative.** Liquidity sweeps, failed breakouts, failed second entries, and inability to continue after aggressive activity can be tested as reversal/continuation context.
5. **Continuation requires acceptance/follow-through.** Breakout direction alone is weak evidence; acceptance beyond a level and a successful retest are more falsifiable conditions.
6. **Risk and selection dominate storytelling.** Fabio describes strict per-trade risk and daily loss limits; Carmine describes minimum reward/risk; Brooks emphasizes day type, setup selection, and discipline. These are design constraints, not proof of profitability.
7. **Statistical homework is mandatory.** FuturesTrader71's public resource index explicitly discusses extracting distributions and conditional probabilities from raw data. This is the strongest methodological bridge to the Trade system: test the frequency and conditional outcomes of an event rather than adopting a visual rule by reputation.

### Differences that must not be blended

- **Auction/order-flow models:** Andrea, Carmine, Fabio, and FT71 emphasize traded volume, order book, footprint, profile, and market mechanics.
- **Price-action models:** Al Brooks emphasizes trend/range context, bars, pullbacks, second entries, breakouts, failed breakouts, and signal quality.
- **Crypto discretionary market reading:** Trader Mayne and Follis describe price action, ranges, liquidity sweeps, auction theory, and live market reasoning. Their public pages do not expose a complete deterministic rule set.
- **Institutional playbook/trader development:** SMB provides broad free educational material and trade reviews; it is a source for process and review discipline, not a directly specified algorithm.

These families should be implemented and tested as separate hypotheses. Do not combine their triggers into a composite score before independent evaluation.

## 3. Data truth table

| Feature | Minimum data needed | OHLCV-only status | Trade system label |
|---|---|---|---|
| Candle structure, swing highs/lows, ranges, breakout/retest | OHLCV | Directly computable | REAL_OHLCV |
| Volume profile / POC / VAH / VAL | Volume-at-price or sufficiently granular trade data | Bar-volume allocation is an approximation | REAL only with trade/volume-at-price; otherwise PROXY |
| Aggressor delta / CVD | Trades with aggressor-side classification | Not recoverable reliably from OHLCV | REAL only with trade-level side; otherwise UNAVAILABLE/PROXY |
| Footprint imbalance | Trade volume at each price and side | Not recoverable from standard OHLCV | UNAVAILABLE unless source supports it |
| Absorption | Aggressive flow plus price response at a level, preferably depth/order-book context | Cannot be proven from OHLCV | PROXY or UNAVAILABLE |
| Resting liquidity walls / spoofing / iceberg | Order-book updates with sequence/timestamps; ideally order-level data | Not recoverable from OHLCV | UNAVAILABLE unless source quality supports it |
| Liquidity sweep/reclaim | Prior swing/level plus trade/price penetration and reclaim | Price sweep can be measured; stop-loss execution itself is not observable | REAL_OHLCV for price event, not proof of stop orders |
| Auction acceptance/rejection | Time/volume distribution around pre-defined levels | Time acceptance can be measured; volume acceptance requires real volume-at-price | Split REAL_TIME / PROXY_VOLUME |

**Hard rule:** A candle-derived estimate must never be named CVD, footprint, absorption, or real order flow.

## 4. Hypothesis specifications

All hypotheses are initially **UNVALIDATED**. Each is to be tested independently, with no parameter tuning on the final test period. Thresholds below are research definitions, not claimed optimal values. The maximum of five tunable parameters per strategy path still applies.

### H1 — Liquidity sweep and reclaim (LRT)

- **Source-derived concept:** Trader Mayne's public description explicitly names ranges and liquidity sweeps; Andrea's curriculum includes stop runs and failed auctions.
- **Hypothesis:** After price penetrates a pre-registered swing extreme and closes back inside the prior range, short-horizon reversal expectancy is higher than for matched non-sweep events.
- **Universe/timeframe:** Liquid perpetual futures; 15m signal bars with 1h context. Use only symbols passing the system liquidity gate.
- **Operational definition:** Identify a swing level using a causal pivot rule; sweep = high/low exceeds the level by at least a volatility-normalized buffer; reclaim = bar closes back across the level. Entry is next-bar executable, never at the signal close.
- **Required data:** OHLCV is sufficient for the price event. Stop-order execution is not observable.
- **Falsification:** No positive net expectancy after fees, slippage and funding; or no improvement versus matched non-sweep controls.
- **Path:** Plan A / LRT. Keep distinct from breakout continuation.
- **Status:** Candidate; no edge claim.

### H2 — Value-area acceptance/rejection (LRT or NMT by regime, tested separately)

- **Source-derived concept:** Fabio's course describes balanced versus directional markets, value areas and absorption; FT71's public resources focus on volume profile and auction statistics.
- **Hypothesis:** Rejection at a prior value boundary predicts rotation back toward value more often than acceptance beyond that boundary predicts reversal.
- **Operational definition:** Build prior-session profile only from completed data. Rejection requires excursion outside VAH/VAL followed by close back inside; acceptance requires a specified number of closes and/or volume share outside the boundary. Pre-register the exact rule before OOS.
- **Required data:** Trade-level volume-at-price for REAL profile. OHLCV-based profile allocation is PROXY only.
- **Falsification:** Conditional outcome distributions do not differ from matched controls, or net expectancy is non-positive.
- **Path:** Test rotation as LRT and acceptance/continuation as NMT in separate experiments.
- **Status:** Real profile version BLOCKED; profile fidelity is a gating dependency.
- **Implemented alternative:** `H2_TIME_REJECTION_PROXY` uses a rolling 24-hour high/low from completed 1h OHLCV bars and requires two consecutive completed closes back inside after a close outside the boundary. It is a time/price rejection proxy only; it does not calculate Volume Profile, POC, VAH or VAL.

### H3 — Price / CVD divergence at a structural level (LRT)

- **Source-derived concept:** Fabio's public curriculum lists CVD, footprint and aggression; Andrea's lists CVD and big-trade filtering.
- **Hypothesis:** At a pre-defined support/resistance or liquidity level, price making a marginal new extreme while real aggressor CVD fails to confirm is associated with a higher reversal rate than ordinary tests of that level.
- **Operational definition:** Compare price extreme and cumulative signed trade volume over the same fixed window; define divergence mechanically and causally.
- **Required data:** Time-stamped trades with reliable aggressor-side classification. OHLCV proxy is not accepted as real CVD.
- **Falsification:** No statistically significant incremental predictive value over price-only structure after costs; unstable sign across walk-forward folds.
- **Path:** Plan A / LRT.
- **Status:** Blocked until real trade-side data is available.

### H4 — Absorption / failed continuation at a key level (LRT)

- **Source-derived concept:** Carmine's public curriculum describes absorption, delta outliers, rebid/re-offer and reversal setups; Fabio's includes absorption and exhaustion.
- **Hypothesis:** When aggressive traded volume is unusually high at a pre-defined level but price progress is unusually small, subsequent reversal expectancy improves versus matched high-volume events without stalled progress.
- **Operational definition:** Define aggression percentile and price-progress-per-unit-aggression using trade-level data. Require a subsequent price confirmation; do not enter solely on a large volume print.
- **Required data:** Trade-level aggressor volume; preferably synchronized order-book/depth data. OHLCV is insufficient to prove absorption.
- **Falsification:** No incremental value over volume and price-response controls; result disappears after realistic slippage.
- **Path:** Plan A / LRT.
- **Status:** Blocked pending real order-flow data and sequence-quality checks.

### H5 — Imbalance breakout continuation (NMT)

- **Source-derived concept:** Fabio's balanced/imbalanced market framework; Andrea's curriculum includes breakouts and liquidity auction mechanics.
- **Hypothesis:** A breakout from a pre-defined balance area followed by acceptance and aligned aggressive flow has better continuation expectancy than a breakout without acceptance.
- **Operational definition:** Freeze balance boundaries before breakout; define acceptance by closes/time outside; require flow alignment only when real aggressor data exists. Test price-only and flow-confirmed versions separately.
- **Required data:** OHLCV for price-only version; trade-side data for real delta confirmation.
- **Falsification:** No positive net expectancy or no improvement over simple Donchian breakout baseline.
- **Path:** Plan A / NMT.
- **Status:** Candidate; two variants must remain separately labelled.

### H6 — Breakout acceptance and successful retest (NMT)

- **Source-derived concept:** Carmine's course explicitly includes breakout retest; Brooks' public course index covers breakout, follow-through, failed breakout and trend continuation.
- **Hypothesis:** Breakouts that hold beyond the broken level and pass a retest have better multi-bar continuation than breakouts that immediately return into the prior range.
- **Operational definition:** Level and balance range are defined using only prior bars; breakout close beyond level; retest within a fixed causal horizon; invalidation on close back through the level. Entry occurs after retest confirmation.
- **Required data:** OHLCV.
- **Falsification:** No incremental net expectancy versus breakout-only and Donchian baselines; performance is explained by a small number of symbols/regimes.
- **Path:** Plan A / NMT; may be compared to Plan C baseline but not blended.
- **Status:** Candidate.

### H7 — Higher-timeframe structure + lower-timeframe trigger (multi-timeframe filter)

- **Source-derived concept:** Brooks' course index explicitly covers higher/lower timeframes, trend/range classification, pullbacks, and second entries; Fabio's framework requires direction before location and aggression.
- **Hypothesis:** Restricting lower-timeframe entries to the direction of a causal higher-timeframe regime improves net expectancy or drawdown versus the same entry trigger without the filter.
- **Operational definition:** Higher-timeframe regime computed only from completed bars; lower-timeframe trigger evaluated after the higher-timeframe state is fixed. No use of an unfinished HTF candle.
- **Required data:** OHLCV.
- **Falsification:** Filter does not improve OOS expectancy/MaxDD, or improvement is offset by excessive missed opportunities.
- **Path:** Evaluate as a standalone filter ablation within each relevant path, not as a universal overlay.
- **Status:** Candidate.

### H8 — Direction + Location + Confirmation (DLC/CLC family)

- **Source-derived concept:** Fabio's Direction–Location–Aggression and Carmine's Context–Location–Confirmation are structurally similar but not identical.
- **Hypothesis:** A three-stage gate (direction/regime, pre-defined location, then confirmation) reduces low-quality entries versus the confirmation trigger alone, without destroying sample size or net expectancy.
- **Operational definition:** Implement as a sequence of independently logged gates. Direction and location are frozen before confirmation; confirmation must be a distinct measurable event. Run ablations for each gate.
- **Required data:** Depends on confirmation type; OHLCV-only confirmation must be labelled price confirmation, not order flow.
- **Falsification:** The full gate does not improve OOS net expectancy/MaxDD over each component and simple baselines, or the gate reduces the sample below a meaningful count.
- **Path:** Research framework only; test separately for LRT and NMT. Do not use as an unvalidated composite score.
- **Status:** Candidate.

## 5. Additional source-derived research tracks (not yet formal strategies)

### Al Brooks — price-action and market-cycle taxonomy
Public course index exposes structured topics: trend versus trading range, pullbacks, signal bars, second entries, failed breakouts, breakout follow-through, channels, wedges, and higher/lower timeframe context. These are suitable for causal event labelling and baseline comparison. They should not be converted into fixed pattern rules without a precise definition and independent testing.

### FuturesTrader71 — statistical market homework
The public Linnsoft archive describes studies of overnight range retests, VPOC revisits, rotation-size distributions, timing of session highs/lows, and volatility-regime adjustments. The transferable principle is to define a market question, calculate the conditional frequency/distribution from raw data, then validate the resulting rule on later data. Historical ES/NQ session effects must not be assumed to transfer to 24/7 crypto.

### Trader Mayne and Follis — discretionary crypto context
Their public pages describe price action, ranges, liquidity sweeps, auction theory and live market reasoning. The public pages do not expose enough deterministic rules to implement a faithful algorithm. Treat them as sources for candidate event taxonomies and manual-review examples, not as an algorithmic specification.

### SMB Capital — review process and playbook discipline
The official free-content page points to trade reviews, strategy videos, articles and a swing-trade evaluation template. This can inform journaling, setup classification and post-trade review. It does not directly specify an independently reproducible futures signal model.

## 6. Experimental protocol

1. **Freeze definitions before testing.** Store the hypothesis ID, version, event definition, data requirements, entry timing, exit logic, cost model and falsification condition in a versioned config.
2. **Use causal data only.** No future pivots, revised profile levels, unfinished higher-timeframe candles, or same-bar fills unless execution is demonstrably possible.
3. **Use the project's walk-forward policy:** train 6 months / test 2 months / step 1 month. Preserve an untouched final holdout.
4. **Include costs:** fee 0.04% plus measured slippage and funding. If funding is missing, label the test incomplete or use a conservative documented proxy.
5. **Compare baselines:** EMA Cross, RSI, Buy & Hold; for breakout hypotheses also include a plain Donchian breakout.
6. **Report per hypothesis/path:** OOS trades, Win, PF, expectancy in R and quote currency, Sharpe, MaxDD, DSR, PBO, Brier where probabilistic forecasts exist, and fold-by-fold stability.
7. **Prevent leakage:** group overlapping events, avoid duplicate entries from the same level, and ensure train/test boundaries do not share forward outcome windows.
8. **Minimum sample:** no acceptance based on a handful of trades. Use pre-registered minimum trade counts and confidence intervals; the project's 150–200 trades per generator remains the relevant Gate_H target.
9. **Do not optimize thresholds on OOS.** If a threshold is selected, select it within training folds only and freeze it for the next test fold.
10. **No blend before proof.** Each hypothesis is evaluated alone before any combination is considered.

## 7. Data and implementation gates

| Gate | Requirement | If missing |
|---|---|---|
| G-PRICE | Continuous, timestamp-clean OHLCV with gap checks | MARKET_DATA_DEGRADED |
| G-TRADES | Trade-level data and reliable aggressor-side classification | H3/H4 real versions BLOCKED |
| G-BOOK | Sequenced order-book snapshots/deltas with synchronization and depth checks | No real absorption/wall claims |
| G-PROFILE | Valid volume-at-price aggregation and session definition | H2 real profile BLOCKED |
| G-COST | Fees, slippage and funding coverage | No PASS claim |
| G-OOS | Complete walk-forward and holdout report | Research-only, no acceptance |

## 8. Prioritization

1. **First implementation candidates:** H1, H6, H7. They can be defined from OHLCV without pretending to have order-flow data.
2. **Second:** H2 price-time version and volume-profile version as separate variants.
3. **Blocked until data readiness:** H3 and H4 real order-flow versions.
4. **Framework/ablation track:** H8, after its components are separately specified and tested.
5. **Keep as educational context:** discretionary live analysis from Trader Mayne/Follis and SMB material until deterministic rules can be extracted from accessible primary material.

## 9. Current research disposition

- Public curriculum/page descriptions reviewed: Andrea, Carmine, Fabio, FT71, Al Brooks, Trader Mayne, Follis, SMB.
- Initial eight hypotheses converted into falsifiable specifications: H1–H8.
- Full lesson-by-lesson transcript extraction: **NOT COMPLETE**. The available review is based on public instructor/course descriptions and curriculum pages. No paid transcript credits used.
- OHLCV research prototypes implemented in `app/research_education.py`: H1 sweep/reclaim, H2 time-boundary rejection proxy, H5 price-only acceptance proxy, H6 breakout/retest, H7 higher-timeframe gate. These are isolated from the production V5 path and emit research events, not executable signals.
- Unit tests added in `tests/test_research_education.py`. Latest verified GitHub Actions run **42877304242** passed: 139 root tests, 68 signal-autopilot tests, dashboard JavaScript validation, Compose validation, Docker build, container health smoke test, and the expanded H1/H2/H5/H6/H7 event-study job.
- **Historical pre-screen completed:** 100 symbols, 1,753,200 one-hour OHLCV rows from the public OKX archive (2024-11-08 through 2026-11-08), with 17 rolling 6m-train/2m-test/1m-step windows. H1/H2_TIME_REJECTION_PROXY/H5_PRICE_PROXY/H6/H7 event counts across the full archive were 84,165 / 30,183 / 53,271 / 49,973 / 24,635. Aggregate metrics below include only events whose signal and forward outcome fit inside at least one OOS test window.
- **Timeframe qualification:** the original H1 research specification called for 15m signals with 1h context. The available Stage-1 archive contains 1h OHLCV only, so the run tests a 1h adaptation, not the original 15m implementation. H7's 4h context is resampled from completed 1h candles; no native 4h series was used.
- **Mean forward return after round-trip fees only** (0.04% per side; slippage and funding unavailable for the full 2y window and excluded):
  - H1: 1h **-0.0879%**, 4h **-0.0913%**, 8h **-0.0847%**.
  - H2_TIME_REJECTION_PROXY: 1h **-0.0620%**, 4h **-0.0730%**, 8h **-0.0710%**.
  - H5_PRICE_PROXY: 1h **-0.0867%**, 4h **-0.0411%**, 8h **-0.1261%**.
  - H6: 1h **-0.0557%**, 4h **-0.0470%**, 8h **-0.0766%**.
  - H7: 1h **-0.0519%**, 4h **-0.0411%**, 8h **-0.1154%**.
- **Interpretation:** all fifteen aggregate mean returns are negative after fees alone. Slippage and funding are still missing, so the fully-costed result cannot improve on these figures under non-negative costs. H1/H2_TIME_REJECTION_PROXY/H5_PRICE_PROXY/H6/H7 therefore do not show a positive mean-forward-return edge in this pre-screen. This is not a formal Gate_A/B/C verdict because there is no stop/target execution model, matched-control design, EMA/RSI/Buy&Hold baseline comparison, portfolio equity curve, PF/MaxDD/Sharpe, DSR or PBO. The test windows overlap and there is no separate untouched final holdout.
- Integration with the production scanner: **NOT DONE**. The research module remains isolated.
- Formal strategy backtest / Gate evaluation: **NOT DONE**. The completed event study is a pre-screen only.
- Edge acceptance: **NONE**. Do not promote H1/H2_TIME_REJECTION_PROXY/H5_PRICE_PROXY/H6/H7 into live signal generation.
- Production integration/deployment: **NOT DONE**.

Data inventory and blocked requirements are documented in `docs/research/DATA-READINESS-AUDIT-2026-11-10.md`. The expanded event-study artifact is attached to [GitHub Actions run 42877304242](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42877304242) and retained for 14 days.

This is a research handoff, not a strategy PASS.
