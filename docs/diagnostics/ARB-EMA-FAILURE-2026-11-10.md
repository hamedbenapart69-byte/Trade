# ARB/USDT EMA Trend Continuation Failure Review — 2026-11-10

## Scope and evidence boundary

- Repository: hamedbenapart69-byte/Trade
- Signal engine matching the Telegram message: signal_autopilot/modules/signal_engine.py
- Historical signal timestamp: 2026-11-10T04:52:46.726704+00:00
- Symbol/side: ARB/USDT:USDT BUY
- Entry: 0.17055; stop: 0.1666285714; TP1: 0.1757785714; TP2: 0.1810071429
- Historical source: signals/history.csv on the signals branch. The row confirms timestamp, symbol, side, provider kucoinfutures, engine EMA20_EMA50_ATR14_MVP, EMA spread 1.2272%, NOT_CALIBRATED, and PROXY entry-time quality.
- The historical CSV row does not preserve entry, stop, targets, EMA values, ATR, ticker timestamp, or the OHLCV input window. The later 08:18 snapshot cannot be substituted for the 04:52 input. Exact candle-by-candle reconstruction is therefore UNAVAILABLE.

## Quantitative reconstruction from the published levels

The legacy code used stop = entry ± 1.5 × ATR and targets = entry ± 2 × ATR / 4 × ATR.

- Risk distance = 0.17055 - 0.1666285714 = 0.0039214286
- Implied ATR14 = 0.0039214286 / 1.5 = 0.0026142857
- TP1 distance = 0.0052285714 = 2 × implied ATR
- TP2 distance = 0.0104571429 = 4 × implied ATR
- Stop distance ≈ 2.30% of entry.
- TP1 reward/risk ≈ 1.33R; TP2 reward/risk ≈ 2.67R.

These calculations are arithmetic deductions from the message, not a reconstruction of the missing candles.

## Root-cause diagnosis

### D2 — Assumption failure: EMA separation was treated as continuation confirmation

The old engine selected BUY whenever EMA20 > EMA50 and SELL whenever EMA20 < EMA50, provided the absolute EMA spread exceeded 0.5%. It did not require:
- both EMA slopes to point in the trade direction;
- the last completed candle close to be on the correct side of EMA20;
- RSI momentum, ADX trend strength, or relative volume confirmation;
- a directional candle trigger;
- a higher-low / lower-high short-term structure;
- an anti-chasing distance limit.

Therefore the 1.2272% spread proved only that the two smoothed averages were separated. It did not prove that the current entry had a fresh continuation trigger.

### D1 — Data-quality limitation: entry time was a proxy

The Telegram message explicitly reported PROXY_FETCH_TIME. In the fetcher, when the provider omits its own ticker timestamp, receipt time is substituted and labeled FETCH_TIME_PROXY. The legacy engine nevertheless allowed that record to become BUY_NOW.

This does not prove that the quoted price itself was stale. It means the actual exchange event time could not be verified, so the system could not honestly claim a fully timestamp-verified immediate entry.

### D3 — Implementation weakness: insufficient EMA50 warm-up and non-structural risk levels

The old fetcher requested 70 hourly candles. With an SMA seed and only 20 subsequent EMA50 updates, the remaining seed weight is approximately (1 - 2/51)^20 ≈ 0.44. Thus a material part of EMA50 could still reflect the initial seed window.

The old stop was a fixed 1.5 × simple-average True Range distance from the ticker price, not a structural invalidation level. TP1/TP2 were fixed at 2/4 × ATR. No nearby support/resistance or structure-aware feasibility check was used.

### D4 — Calibration failure

The signal explicitly said NOT_CALIBRATED. There is no evidence that this EMA rule had passed out-of-sample win-rate, profit-factor, drawdown, or probability-calibration gates. One stopped trade cannot establish a population win rate or prove a particular numerical cause.

### D6 — Observability failure

The historical row stores the decision and a reason string but not the input OHLCV window, exact ticker timestamp, entry/stop/target values, or indicator values. The system could not conduct a full forensic replay after the loss. This is a data-contract weakness, not merely a charting inconvenience.

## Ranked causal hypotheses for this individual loss

1. Most strongly supported design weakness: EMA spread alone was insufficient to establish a fresh continuation setup. This is directly visible in the legacy implementation.
2. Material execution uncertainty: entry timestamp was a fetch-time proxy and still received BUY_NOW status.
3. Plausible but unproven: price may have been extended or entering a pullback/reversal when the alert was emitted.
4. Plausible but unproven: the stop may have been placed inside ordinary local structure/noise because it was ATR-only.
5. Not determinable: whether BTC/market regime, funding, open interest, order flow, or a nearby resistance level invalidated the ARB long at 04:52 UTC. The historical input snapshot is missing.

## V2 changes on an isolated feature branch

- Increase requested hourly history to 210 candles and require at least 200 completed candles.
- Require EMA20/EMA50 directional alignment, both slopes aligned, and last close on the trend side of EMA20.
- Add RSI, ADX, relative volume, candle-trigger, short-term structure, and anti-chase gates.
- Make FETCH_TIME_PROXY entries CONDITIONAL rather than BUY_NOW/SELL_NOW.
- Use the more conservative of an ATR stop and recent structural stop; reject stops wider than 3% rather than silently widening risk.
- Set targets at 1.5R and 2.5R.
- Persist a SHA-256 input hash, gate results, metrics, and full 200-candle replay window for qualified setups.
- Expand history CSV so future signals retain entry, stop, targets, EMA/ATR, source timestamp quality, metrics, hypothesis, falsification, and input hash.

## SLRP

Stage: EMA Trend Continuation reliability V2

Acceptance criteria:
- 100% of actionable BUY_NOW/SELL_NOW signals pass every V2 quality gate.
- Any FETCH_TIME_PROXY price is never emitted as BUY_NOW/SELL_NOW.
- Fewer than 200 completed hourly candles => MARKET_DATA_DEGRADED.
- Every qualified setup has an input hash and a replayable 200-candle evidence window.
- History records entry, stop, targets, EMA20/50, ATR14, timestamp source, gate metrics, and signal ID.
- No thresholds are relaxed to increase signal count.
- V2 is not declared profitable or calibrated until genuine walk-forward/OOS evidence meets the project gates.

v1 → FAIL (specific evidence): The ARB signal was stopped; its published record shows only a 1.2272% EMA spread and a PROXY_FETCH_TIME entry, while the legacy implementation had no momentum, structure, slope, or anti-chase gates. Historical candle inputs are absent, so the exact trade path is unreconstructable.

v2 → PENDING: Code and deterministic tests are being added on an isolated branch. PASS requires GitHub Actions test evidence and later market-data/paper validation; synthetic unit tests alone are not trading-performance evidence.

v3: Not built. R11: no v2 failure has yet been observed.

Active: Legacy V1 remains on main until review, CI and a separate activation decision. The feature branch is not live.

Escalation: If V2 cannot meet acceptance criteria, classify D1/D3/D4 using real run evidence, then use the project's Innovation Protocol. Do not relax gates.

Budget: Maximum three versions; current V2 is the only proposed successor.

## Self-critique

1. Future data used? No in the V2 implementation; only completed candles are fetched. Must remain tested.
2. Params tuned on test data? No OOS optimization was performed. V2 thresholds are conservative engineering gates, not statistically optimized.
3. Costs included? Not yet in this isolated EMA engine's setup qualification; fee/slippage/funding must be included in paper/OOS evaluation before performance claims.
4. No-signal reporting? Yes, C10 states remain supported; conditional and degraded states are explicit.
5. Weakest assumption? The chosen RSI/ADX/volume/structure cutoffs may reduce false positives but have not been proven to improve OOS expectancy. Only walk-forward evidence can answer that.
