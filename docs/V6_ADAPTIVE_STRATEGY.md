# Futures Signal Autopilot V6 — Adaptive Strategy Layer

## Status

V6 is a separate adaptive strategy layer built alongside the strict V3/V5 baseline. It is not a claim of profitability or a validated high-win-rate system. It must pass CI and a chronological walk-forward evaluation before deployment to the public scheduled scanner.

## Discovery and coverage

- CoinGecko discovery requests up to 250 market assets per request.
- The engine filters to verified live OKX linear USDT perpetual contracts.
- The extended scan ranks eligible contracts by CoinGecko-reported 24-hour volume and evaluates up to 100 contracts.
- The dashboard reports discovered assets, eligible contracts, selected contracts, screened contracts, and insufficient-data counts separately.
- CoinGecko's published documentation says the `/coins/markets` endpoint accepts up to 250 assets per page. See https://docs.coingecko.com/reference/coins-markets and https://www.coingecko.com/learn/coingecko-api-troubleshooting-guide-and-solutions.

## Strategy families

1. `V3_STRICT_BASELINE`: original strict RSI/volume/EMA/4H/funding rules remain intact as a distinct legacy strategy.
2. `TREND_PULLBACK`: aligned 1D/4H/1H regime, directional EMA20/EMA50 stack, and a pullback within 1.75 ATR of 1H EMA20. If RSI is stretched, the setup remains conditional until RSI resets into its operating band and a completed 15m candle retests 1H EMA20 and closes back in the trend direction.
3. `BREAKOUT_CONFIRMATION`: completed 1H close beyond the previous 20-bar range with volume ratio at least 1.15 and ADX at least 18; a completed 15m close beyond the breakout level is required for immediate-entry eligibility.
4. `BREAKOUT_RETEST`: the breakout conditions plus a 15m retest/rejection around the broken level.
5. `LIQUIDITY_SWEEP_REVERSAL`: a structurally detected 4H liquidity sweep with a completed 15m directional reversal.
6. `RANGE_MEAN_REVERSION`: a ranging regime with RSI and Bollinger location at an edge; stochastic RSI and 15m confirmation strengthen the score.

A market that passes data validation but has no qualifying pattern is `WAIT`, not `REJECT`. `REJECT` remains for failed hard instrument, data, funding-safety, or risk constraints. Missing or inconsistent mandatory data remains `INSUFFICIENT_DATA`.

## Scoring and publication

- V6 blends 60% of the existing evidence-weighted technical/market score with 40% of the adaptive pattern score.
- `confidence_v6` is a deterministic ranking score from 0–100, not a probability of winning.
- The old `confidence_v5` field remains as a compatibility alias during migration.
- Adaptive signals must also have at least 2R of clear space before the nearest verified opposing structure level; otherwise they remain WAIT.\n- Immediate signals require score at least 70, data grade A/B, completed-candle confirmation, no unresolved daily conflict, verified contract and prices, and all risk gates.
- Conditional signals require score at least 60 and publish a measurable trigger/confirmation rule. Trend pullbacks use a retest-and-rejection trigger (wick touches the 1H EMA20 zone, then the 15m close returns in the trend direction); other families use explicit close-above/close-below triggers.
- The strict V3 baseline keeps its original funding ceiling of 0.05% per 8-hour equivalent. Adaptive families may continue through moderate funding with a score penalty, but funding at or above 0.15% per 8-hour equivalent is a hard safety rejection.
- Risk remains capped at $4 planned loss, 5x leverage maximum, 0.5%–3.0% stop distance, and at least 2.0 reward-to-risk. Actual losses can exceed planned loss due to slippage, gaps, fees, and funding.

## Data and safety boundaries

- Public read-only OKX perpetual market data and CoinGecko discovery only.
- No exchange account connection, API credentials, or order execution.
- No invented liquidation clusters, on-chain flows, whale identities, or smart-money claims. Those sources remain explicitly unavailable unless independently connected and timestamp-verified.
- Signals are paper-tracked against subsequent public OHLCV candles, not exchange fills.

## Required validation before promotion

1. Full unit test suite and container smoke test green.
2. Live scan against the expanded 250-asset discovery universe and up to 100 verified perpetual contracts.
3. Chronological walk-forward test with no look-ahead, fees/funding/slippage sensitivity, and per-strategy breakdown.
4. Separate out-of-sample reporting of sample count, win rate, expectancy in R, profit factor, max drawdown, and confidence intervals.
5. Promote thresholds only when out-of-sample expectancy and drawdown improve; never optimize only for in-sample win rate.
