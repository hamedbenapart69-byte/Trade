# SLRP — Education-to-Research Subproject Closure

**Date:** 2026-11-10  
**Scope:** H1/LRT liquidity-sweep research versions and educational hypothesis transfer  
**Repository:** `hamedbenapart69-byte/Trade`  
**Branch:** `research/education-ohlcv-prototypes-v1`  
**Status:** V1/V2/V3 pre-screen FAIL; Honest Stop for current price-only variants

## Objective

Convert public educational concepts into falsifiable, causally implemented research events; run a fee-aware historical pre-screen; reject unsupported methods before any production integration.

## Acceptance criteria

This is a **pre-screen**, not a formal strategy Gate.

- A candidate may pass this pre-screen only if at least one pre-registered horizon has positive mean return after the known round-trip fee, with adequate OOS event count and no obvious single-fold dependence.
- A pre-screen PASS would still not authorize production. Formal acceptance requires realistic slippage/funding, stop/target fills, portfolio-level metrics, matched controls, baselines, DSR/PBO and the project's relevant Gate.
- If all tested horizons remain negative after fees, the version is FAIL and parameters are not relaxed.

Known fee model: 0.04% per side, 0.08% round trip. Slippage and complete historical funding are unavailable and excluded; therefore every reported net return is **fee-only**, not fully costed.

## V1 — 1h sweep/reclaim, all regimes

**Assumption:** A causal liquidity sweep beyond a prior swing followed by a close back inside the range has positive short-horizon reversal expectancy across the full universe.

- Data: 100 symbols, 1,753,200 one-hour OHLCV rows, 2024-11-08 to 2026-11-08.
- Events: 84,165 across the archive.
- OOS observations: 63,173 / 63,166 / 63,159 at 1h / 4h / 8h.
- Mean net after fee-only: **-0.0879% / -0.0913% / -0.0847%**.
- Result: **FAIL**.
- Diagnosis: **D5 Regime** — one all-regime rule did not isolate a positive conditional state. **D2 Assumption** — sweep/reclaim alone is insufficient to establish reversal edge.

## V2 — neutral-regime LRT restriction

**Why V1 failed:** all three OOS means were negative after fees. A reversal event may be more plausible in a balanced/neutral market than when the higher timeframe is directional.

**Changed assumption (not parameter tuning):** retain H1 sweep/reclaim events only when the completed 4h EMA20/EMA50 regime is NEUTRAL.

- Variant: `H8_LRT_RANGE_V2`.
- Events: 26,975 across the archive.
- OOS observations: 20,713 / 20,711 / 20,708 at 1h / 4h / 8h.
- Mean net after fee-only: **-0.0856% / -0.0714% / -0.0557%**.
- Relative to V1: descriptive improvement of 0.23 / 1.99 / 2.90 basis points, respectively.
- Result: **FAIL**. All horizons remain negative after fees.
- Diagnosis: **D5 Regime** — neutral restriction reduces losses but does not create positive expectancy. This is not enough to accept an edge.

## V3 — 4h signal-timeframe shift

**Why V2 failed:** the neutral-regime subset remained negative. A slower signal timeframe may capture more meaningful auction extremes and reduce 1h noise.

**Changed assumption:** detect sweep/reclaim on resampled 4h candles using the same causal 20-bar lookback; map the event only to an hourly candle with the exact same close time; enter at the next hourly open (the next 4h bar open); evaluate 4h/8h/12h holding horizons. No threshold was tuned.

- Variant: `H1_LRT_V3_4H`.
- Events: 30,846 across the archive.
- OOS observations: 23,423 / 23,423 / 23,412 at 4h / 8h / 12h.
- Mean net after fee-only: **-0.0751% / -0.1474% / -0.1298%**.
- Result: **FAIL**. All horizons remain negative after fees; the longer horizons are materially worse.
- Diagnosis: **D5 Regime / D6 Expectations** — timeframe shift did not produce a robust positive mean. The 4h result is still negative and is not a Gate PASS.

## SLRP result

- V1: FAIL — D5/D2 — evidence above.
- V2: FAIL — D5 — neutral regime reduces losses but remains negative.
- V3: FAIL — D5/D6 — 4h signal timeframe remains negative.
- Active version: **NONE**.
- Handoff: **Innovation Protocol / Honest Stop**. No fourth version is permitted in this cycle.

## Innovation Protocol disposition

1. **Data Expansion — completed as an audit, not a full backfill.** The repository has 2y 1h OHLCV for 100 symbols, approximately 94 days of funding, 30 days of OI, and only a point-in-time 1,773-row L2 sample across 3 providers and 10 symbols. There is no persisted trade tape or continuous historical order book.
   - Official OKX public `history-trades` supports up to 3 months, 100 records/page and exposes taker side. That is useful for a bounded recent collector but shorter than the project's 6m training window. No backfill is claimed.
2. **Timeframe Shift — tested.** The 4h signal version V3 failed. Original H1 15m signal timeframe remains untested because the persisted archive is 1h only.
3. **Simplicity Audit — completed.** The H1 base trigger is already simpler than the H8 composites. H8_LRT_DLC (trend-aligned) is worse than H1 at all horizons. H8_LRT_RANGE_V2 improves the means modestly but remains negative. H8_NMT_DLC improves H5 by 2.14 bps only at 4h but remains negative and is worse at 1h/8h. Added gates have not demonstrated positive net edge.
4. **Regime Restriction — tested.** V2 restricts LRT events to neutral 4h regime and still fails.
5. **Alternative Market — not executed.** No comparable, gap-free 2y alternative-provider dataset is currently persisted in the repository. Mixing different contract histories without a verified symbol/contract mapping would invalidate the comparison. This step remains a data-acquisition task, not evidence of failure or success.
6. **Honest Stop — current versions stopped.** Do not promote any tested price-only variant. Reopen only after a new data asset or genuinely new hypothesis is available; do not tune these failed rules on the same OOS sample.

## Other hypothesis disposition

- H2 real Volume Profile / POC / VAH / VAL: **BLOCKED**. `H2_TIME_REJECTION_PROXY` is only a rolling 24h OHLCV time/price rejection proxy; all 1h/4h/8h means are negative after fees.
- H3 real CVD divergence: **BLOCKED** until continuous trade-side history with validated aggressor-side semantics and contract normalization exists.
- H4 real absorption: **BLOCKED** until synchronized trade flow and continuous sequenced order-book/depth history exists.
- H5 price-only acceptance proxy: pre-screened; all tested means negative after fees. It is not real delta/footprint.
- H6 breakout/retest and H7 HTF filter: pre-screened; all tested means negative after fees.
- H8: two LRT/NMT price-only variants and one neutral-regime LRT variant were tested. Location/confirmation were inherited from H1/H5 triggers; only the direction/regime gate was ablated. Full independent gate ablations remain incomplete.

## Educational-source completion status

- Eight public source/course pages were reviewed and mapped into the cross-source synthesis and H1-H8 specifications.
- Full lesson-by-lesson video playback/transcript extraction is **not complete**. Some earlier video transcripts were extracted, but the exact full lesson inventory is not reproducibly available in this closure artifact.
- The integrated vidIQ transcript route consumes 5 credits per call; no paid credits were used or authorized. No transcript-derived quotations are claimed.
- Public course-page descriptions are not treated as proof of a teacher's full method or of profitability.
- No strategy is accepted from instructor reputation or educational claims.

## Self-critique

1. **Future data / look-ahead:** no future candle is used for the signal. HTF filters use only candles whose close time is at or before the signal close. Entries use the next bar open. A dedicated event-study timing test passed.
2. **Parameters tuned on test:** no parameters were tuned on OOS windows. V1/V2/V3 differ by assumption/regime/timeframe, not by test-set optimization.
3. **Costs included:** only the known 0.04% per-side fee is included. Slippage and full-window funding are unavailable and excluded. Therefore these are not fully costed results.
4. **No-signal case:** event-study summaries return `INSUFFICIENT_SAMPLE` when no observations exist; the production scanner is not modified by this research.
5. **Weakest assumption:** 1h OHLCV cannot reveal real aggressor flow, volume-at-price, absorption or historical liquidity. The current pre-screen cannot validate those concepts.

## Validation limits

- 17 rolling 6m-train / 2m-test / 1m-step windows; test windows overlap by one month.
- The event study is descriptive and does not fit a model in the training window.
- No stop/target fill simulation, matched controls, EMA/RSI/Buy&Hold baselines, portfolio equity curve, PF, MaxDD, Sharpe, DSR or PBO is included.
- No Gate_A/B/C/H verdict is claimed.
- OOS mean-return observations are not a substitute for a full strategy backtest.

## Reproducibility

- GitHub Actions run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42879753589
- Verified: 145 root tests, 68 signal-autopilot tests, event-study execution-timing unit test, dashboard JS validation, Compose validation, Docker build and container health smoke test.
- Event-study artifact: `education-hypothesis-event-study`, artifact ID `13793721069` (14-day retention).
- No production scanner integration, no merge to `main`, and no production deployment.
