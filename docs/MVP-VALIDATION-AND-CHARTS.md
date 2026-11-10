# MVP validation and signal-chart delivery

## Current state

The live engine remains the existing EMA20/EMA50 + ATR14 MVP. It is not a proven profitable strategy. The current signal output must retain \`NOT_CALIBRATED\` until out-of-sample probability calibration exists.

## Telegram delivery change

Every actionable signal now carries its own last 70 completed 1H candles. The notifier renders a real candlestick PNG from those candles, overlays EMA20/EMA50, and draws Entry, Stop Loss, TP1 and TP2. The caption includes analysis type, timeframe, reason, hypothesis, falsification condition, all price levels, and the dashboard link. If chart rendering fails, the notifier sends the full text analysis instead and reports the fallback in logs.

The chart is an explanatory rendering of the exact candle payload used by the signal engine. It is not a separately generated or guessed chart.

## First research stage: baseline validation

The new walk-forward harness evaluates the current EMA20/EMA50 + ATR14 rule on the isolated two-year OKX 1H OHLCV archive:

- Train window: 6 months
- Test window: 2 months
- Step: 1 month
- Signal decision: completed candle close
- Entry: next candle open
- Stop: 1.5 × ATR14
- TP1: 2 × ATR14, 50% exit
- TP2: 4 × ATR14, remaining 50% exit
- Same-candle stop/target ambiguity: stop is assumed first
- Fees: 0.04% each side
- Slippage: 0.02% each side, explicitly a PROXY assumption

### Known blockers

The archived Stage 1 report documents two-year 1H OHLCV but only about 94 days of historical funding, about 30 days of OI, and no historical order-book or liquidation series. Therefore the full two-year net result cannot be called fully cost-adjusted. Funding is labelled UNAVAILABLE in the baseline trades. DSR, PBO, calibration, portfolio concurrency/correlation constraints, and the required baseline comparisons are not yet implemented in this first harness.

The report is research evidence only. It cannot pass a profitability gate or promote the MVP to the live engine.

## Promotion policy

No candidate is promoted unless all required OOS gates pass, data and execution costs are adequately covered, the sample size is sufficient, and paper/shadow evidence confirms live-like behavior. A profitable backtest alone is not proof of future profitability.

## Next stages

1. Run and inspect baseline OOS evidence; diagnose failure using D1-D6.
2. Build a distinct v2 only after a measured v1 failure.
3. Add the LRT/NMT dual engine with explicit PROXY/UNAVAILABLE handling for missing order-flow data.
4. Add Plan B, Plan C, and Plan H as independent paths with separate gates and reports.
5. Add calibration, EV, risk/consensus gates, and a 30-60 day paper/shadow period.
6. Keep manual trading only. No exchange account keys or order execution.


## First baseline evidence (GitHub Actions run 42520083908)

The first reproducible run completed successfully as a computation, but the strategy result **FAILED** the profitability screen:

| Metric | OOS result |
|---|---:|
| Symbols | 100 / 100 |
| Trades | 53,043 |
| Win rate | 42.51% |
| Profit factor | 0.9042 |
| Expectancy | -0.0579R / trade |
| Trade-sequence drawdown proxy | 100.0% |

The backtest now checks signals on the production four-hour scan cadence, uses a six-month warm-up/train period, two-month test windows, and one-month steps. Entry is modeled at the next 1H open after the signal candle. The 100 symbol files were read successfully.

Additional diagnostics:
- 37,734 trades (71.14%) exited at a stop or same-bar stop ambiguity; 14,251 (26.87%) reached TP2.
- 88 of 100 symbols had PF below 1.0; none reached PF 1.2.
- Monthly PF was unstable, ranging from 0.538 to 1.301; only one monthly bucket reached 1.2.
- Long PF was 0.867 and short PF was 0.939. The failure is not isolated to one direction.

### SLRP baseline verdict

- v1: **FAIL** — PF 0.9042 is below Gate_C 1.2 and expectancy is negative.
- Diagnosis evidence: the current EMA spread-only condition produces too many stop exits and does not separate profitable continuation regimes.
- D2 is the leading hypothesis (the premise that EMA ordering plus a 0.5% spread is enough to identify continuation). D5 regime sensitivity is also indicated by the monthly PF dispersion, but the current report does not establish causality.
- No v2 is promoted or deployed. A v2 research candidate must change the entry assumption, add explicit structure/regime confirmation, and be tested against the required baselines before any live promotion.

### Interpretation limits

The 100% drawdown figure is a sequential trade-equity proxy across symbols, not a concurrency-aware portfolio drawdown. It must not be used as the official portfolio MaxDD gate. Funding is still unavailable for most of the two-year window, slippage is PROXY, and DSR/PBO plus EMA-cross/RSI/Buy-and-Hold baseline comparisons remain outstanding. Therefore this run is a valid negative screening result, not a complete Gate_C verdict.


## SLRP — MVP baseline stage contract

**Objective:** determine whether the existing EMA20/EMA50 + ATR14 engine has positive OOS expectancy after realistic execution costs, before changing its assumptions or promoting it.

**Acceptance criteria:** PF ≥ 1.20, portfolio-aware OOS MaxDD ≤ 25%, PBO < 0.50, positive net expectancy, sufficient trade count, and cost coverage including funding. The present report is not a PASS because PF and expectancy failed and several required statistics/costs remain unavailable.

### Versions

- **v1 — state-only EMA continuation:** EMA20/EMA50 relative spread > 0.5%; SL 1.5 ATR; TP1 2 ATR; TP2 4 ATR. **FAIL:** 53,043 OOS trades; Win 42.51%; PF 0.9042; expectancy -0.0579R. Stops/same-bar stop ambiguity: 71.14%; TP2: 26.87%.
- **v2 — structure-confirmed pullback:** 4H EMA50/EMA200 defines regime; 1H pullback toward EMA50 followed by a closed-candle rejection in the regime direction. This changes the entry premise from “EMA state is enough” to “trend regime plus pullback/rejection is required.” **Defined only; not implemented or tested.**
- **v3 — simple breakout fallback:** 20-period Donchian breakout with ATR trailing exit, independent of the EMA pullback premise. **Defined only; not implemented or tested.**

**Diagnosis:** D2 is the leading hypothesis because EMA ordering plus a spread threshold does not establish continuation; 71.14% of exits were stop-related and PF was below 1.0 for 88/100 symbols. D5 is also indicated by monthly PF dispersion (0.538–1.301), but no causal regime attribution is claimed. D1 remains a separate blocker for complete costs because two-year funding is unavailable.

**Active:** existing MVP remains in production only as an uncalibrated signal source; it is not promoted as profitable.  
**Escalation:** if v2 and v3 fail, invoke the Innovation Protocol rather than repeatedly tuning EMA parameters.  
**Budget:** maximum three versions for this baseline stage. No thresholds may be relaxed.


## Methodology correction — 2026-11-10

A code-level review identified a structural weakness in the first walk-forward aggregation: the fixed-rule strategy was restarted flat in overlapping two-month test windows stepped monthly. Each fold could independently open positions, close an unfinished position at its own test-window boundary, and then deduplicate trades by entry timestamp. This means the reported 53,043-trade result was generated by overlapping fold simulations rather than one continuous position lifecycle per symbol.

The previous result remains a historical output of that implementation, but it is **superseded for decision-making** until the corrected run is completed. The direction and size of any metric bias are not assumed.

The corrected fixed-rule evaluation uses the first six months only as indicator warm-up (the EMA/ATR rules do not fit parameters), then runs one continuous chronological OOS path per symbol. A symbol can have only one active position at a time; positions continue across all OOS bars and are not reset at monthly fold boundaries. This correction does not yet create a concurrency-aware multi-symbol portfolio simulation; the reported drawdown remains a trade-sequence proxy until portfolio capital allocation and simultaneous cross-symbol positions are modeled.

The corrected workflow must rerun on the same archived input, preserve the data hash, and publish a new artifact. No new performance claim is made before that run completes.
