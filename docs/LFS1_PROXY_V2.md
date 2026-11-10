# LFS1 Proxy V2 — Implementation Boundary

## Source rule

V9 defines LFS1 REAL as Order Book Depth relative to traded volume. If REAL depth history is unavailable, the approved proxy inputs are ATR and Volume Ratio. REAL and PROXY must never be described as equivalent.

## Implemented proxy

The current signal engine computes a deliberately conservative, short-window proxy from completed 1h OHLCV candles:

- ATR14 as a percentage of close, ranked against the available prior ATR observations.
- Rolling 24h volume, ranked against prior rolling 24h volume observations.
- Low-volume percentile = 1 minus the current volume percentile.
- LFS1 proxy score = 0.5 × ATR percentile + 0.5 × low-volume percentile.
- A high-thinness flag requires score >= 0.90 AND both component percentiles >= 0.85.
- At least 52 hourly candles are required. Short history is reported as UNAVAILABLE, never zero.
- Every result is tagged data_class=PROXY and calibration=NOT_CALIBRATED.

The 70-bar live fetch currently provides only about 70 hours of history. These percentiles are short-window diagnostics, not a 90-day calibrated threshold. The 0.90 / 0.85 gates are conservative implementation assumptions and must be evaluated before any promotion.

## LFS v2 aggregate

The weighted aggregate uses the V9 weights:
- LFS1 0.25
- LFS2 0.20
- LFS3 0.20
- LFS4 0.20
- LFS5 0.15

The aggregator refuses to calculate a score if any component is missing or outside [0,1]. Current live pipeline lacks historical same-market funding distribution, Long/Short positioning, 90-day BB-width distribution, and OI-change history. Therefore LFS v2 currently reports UNAVAILABLE with missing component names. It does not substitute zeros or manufacture a full score.

## REAL L2 collection boundary

The WebSocket collector records public snapshots and raw top-of-book levels from OKX, Bybit and KuCoin Futures. Quantities are stored in each venue's native unit; they are not comparable across venues without contract multiplier normalization. No USD-depth ratio or LFS1 REAL score is emitted by this collector.

The scheduled collector samples for 10 minutes every hour at 10-second intervals. This is intermittent sampling, not a continuous 24/7 feed. A 30-calendar-day archive will therefore contain sampled observations only. REAL promotion requires:
1. At least 30 calendar days with per-symbol coverage and gap reports.
2. Correct contract-size / multiplier normalization per venue.
3. Depth-to-traded-volume calculation in compatible units.
4. Sequence, timestamp, stale-book and cross-provider integrity checks.
5. A separate validation report before replacing PROXY.

No trading account, private channel, API key or order endpoint is used.
