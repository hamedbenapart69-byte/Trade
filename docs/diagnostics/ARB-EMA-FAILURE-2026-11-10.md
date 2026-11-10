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

## Existing OOS evidence for V1

The repository's reproducible baseline report records 53,043 out-of-sample trades, 42.51% win rate, PF 0.9042, and expectancy -0.0579R/trade. 71.14% exited at stop or same-bar stop ambiguity; 26.87% reached TP2; 88 of 100 symbols had PF below 1.0. Monthly PF ranged from 0.538 to 1.301.

This is strong evidence that the EMA-state-only V1 premise is failing as a population strategy, not merely that one ARB trade lost. The report is still not a complete Gate_C verdict: historical funding is incomplete, slippage is PROXY, the drawdown is a trade-sequence proxy rather than concurrency-aware portfolio MaxDD, and DSR/PBO plus required baseline comparisons are missing.

## V2 changes on an isolated feature branch

V2 follows the already documented Stage design: change the entry premise from "EMA20/EMA50 state and spread are enough" to "4H EMA50/EMA200 regime plus a 1H pullback toward EMA50 followed by a closed-candle rejection in the regime direction."

- Fetch 210 completed 1H candles (require 200) and 700 completed 4H candles. The 700-bar 4H history reduces the EMA200 seed influence below approximately 1%.
- 4H EMA50/EMA200 define the directional regime; the 4H close must remain on the regime side of EMA50.
- 1H entry requires a pullback within 0.25 ATR of EMA50 and a completed rejection candle back in the 4H regime direction.
- G4 liquidity guard: 24H quote turnover must be at least 10,000,000 USD; missing turnover is MARKET_DATA_DEGRADED.
- FETCH_TIME_PROXY entries are CONDITIONAL, never BUY_NOW/SELL_NOW.
- Stop is beyond the rejection/nearby structure with a 0.25 ATR buffer; reject risk wider than 3%.
- Targets are 1.5R and 2.5R.
- Persist a SHA-256 input hash, gate results, 1H/4H metrics, 200 1H candles, and 700 4H candles for qualified setups.
- Expand history CSV so future signals retain entry, stop, targets, 1H/4H EMA values, ATR, source timestamp quality, metrics, hypothesis, falsification, and input hash.

## Other paths: deliberate separation

The scheduled 15m LRT path is a separate engine and must not inherit EMA entry logic. Its current design already uses 4H Kumo and 1H Kijun bias, LFS components, sweep/OB/FVG, CVD with PROXY labeling when needed, and returns WATCHLIST/NO_QUALIFIED_SETUP with NOT_CALIBRATED status rather than immediate BUY_NOW/SELL_NOW. It is not changed by this 1H EMA V2 branch. Other V5/Plan A/B/C/H paths must keep their own gates and reports; only cross-cutting data-integrity and audit requirements should be shared.

## SLRP

Stage: EMA Trend Continuation reliability V2

Acceptance criteria:
- 100% of actionable BUY_NOW/SELL_NOW signals pass every V2 quality gate.
- Any FETCH_TIME_PROXY price is never emitted as BUY_NOW/SELL_NOW.
- Fewer than 200 completed 1H candles or 700 completed 4H candles => MARKET_DATA_DEGRADED.
- Every qualified setup has an input hash and replayable 200-candle 1H plus 700-candle 4H evidence windows.
- History records entry, stop, targets, EMA20/50, 4H EMA50/200, ATR14, timestamp source, gate metrics, and signal ID.
- Tunable strategy parameters remain capped at five: pullback tolerance, stop buffer, maximum stop percentage, TP1 R, and TP2 R. EMA periods and G4 are fixed design/constitution constraints.
- G4: every qualified symbol has verified 24H quote turnover >= 10,000,000 USD.
- EMA200_4H warm-up residual seed weight is below approximately 1% (700 completed 4H bars).
- No thresholds are relaxed to increase signal count.
- V2 is not declared profitable or calibrated until genuine walk-forward/OOS evidence meets the project gates.

v1 → FAIL (specific evidence): OOS baseline is 53,043 trades, 42.51% win, PF 0.9042, expectancy -0.0579R; 71.14% stop/same-bar stop exits. The ARB example also had only a 1.2272% EMA spread and PROXY_FETCH_TIME entry. The historical ARB candle snapshot is absent, so its exact path is unreconstructable.

v2 → PENDING: The branch implements the documented 4H EMA50/200 regime + 1H EMA50 pullback/rejection premise, data freshness checks, conditional handling for proxy timestamps, structural risk, and replay evidence. PASS requires green GitHub Actions tests plus a new OOS walk-forward comparison against V1 and baselines. Synthetic unit tests alone are not trading-performance evidence.

v3: Not built. R11: no v2 failure has yet been observed.

Active: Legacy V1 remains on main until review, CI and a separate activation decision. The feature branch is not live.

Escalation: If V2 cannot meet acceptance criteria, classify D1/D3/D4 using real run evidence, then use the project's Innovation Protocol. Do not relax gates.

Budget: Maximum three versions; current V2 is the only proposed successor.

## Self-critique

1. Future data used? No in the V2 implementation; only completed 1H and 4H candles are fetched. Must remain tested.
2. Params tuned on test data? No OOS optimization was performed. V2's pullback/stop/target values remain fixed design assumptions pending validation.
3. Costs included? Not yet in this isolated EMA engine's setup qualification; fee/slippage/funding must be included in paper/OOS evaluation before performance claims.
4. No-signal reporting? Yes, C10 states remain supported; conditional and degraded states are explicit.
5. Weakest assumption? The chosen RSI/ADX/volume/structure cutoffs may reduce false positives but have not been proven to improve OOS expectancy. Only walk-forward evidence can answer that.


## Implementation follow-up — 2026-11-10 09:17 UTC

- Added paginated 4H OHLCV retrieval: requests are capped at 300 bars per page and continue by timestamp until 701 raw bars are collected (700 required completed bars plus one in-progress-bar allowance).
- Anchored the history window to the latest required completed interval; this avoids returning a sufficiently long but stale window that would fail the candle-freshness gate.
- Added a deterministic pagination test proving three requests produce exactly 700 latest completed 4H bars after the current incomplete candle is removed.
- Latest branch head: 93439747fe88806cf57946bdc6ad70edc664a4e0.
- GitHub Actions on this head: repository CI PASS; pytest PASS; Futures Signals Pipeline PR validation PASS. Root suite: 127 tests PASS. Signal-autopilot suite: 40 tests PASS.
- These PR workflows skip the live data-fetch/Telegram/publication steps. No live signal activation or Telegram runtime delivery is proven by these checks.
- Walk-forward workflow completed technically, but its output is still the V1 baseline only: 53,043 trades, 42.51% win rate, PF 0.9042, and gate BLOCKED because funding history is incomplete and DSR/PBO plus baseline comparison are not implemented. This is not a V2 OOS result.
- V2 remains PENDING. It must not be merged into the active production branch or represented as profitable/calibrated until V2-specific OOS validation, cost-aware portfolio drawdown, calibration and paper/shadow evidence pass the existing gates.
