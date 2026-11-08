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
