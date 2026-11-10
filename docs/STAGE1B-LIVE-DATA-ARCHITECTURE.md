# Stage 1b: Rolling 15m Data and Freshness

## Why this exists
The former scheduled job re-downloaded a complete 730-day Parquet snapshot every UTC day. Two snapshots already occupied about 202 MB in the market-data working tree, and the date-exclusive window ended at the previous day's 23:45 candle. A complete historical window was therefore not proof of live freshness.

## Storage layout
- `datasets/stage1b/lrt15m/base/<SYMBOL>_15m.parquet`: one validated 730-day baseline, migrated from the newest legacy snapshot.
- `datasets/stage1b/lrt15m/live_tail/YYYY-MM-DD/<SYMBOL>_15m.parquet`: completed UTC-day partitions only.
- Current-day candles are fetched on each 4-hour run and used ephemerally for compute. They are persisted once the UTC day is complete.
- `signal_autopilot/data/stage1b_compute/` is temporary runner data and is never committed to `market-data`.

## Freshness gate
- Only closed 15m candles are accepted.
- The latest candle close must be no more than 30 minutes old.
- The rolling compute window must contain exactly 70,080 continuous 15m bars.
- A stale or discontinuous symbol is emitted as `MARKET_DATA_DEGRADED`; it is never converted into a trade setup.
- The workflow publishes both `PASS` and `DEGRADED` reports so the daily report is not silently lost.

## Provider and honesty rules
- Public OKX swap candles are tried first; public MEXC futures candles fill missing bars.
- 1000PEPE may use the already-labelled OKX spot scaling proxy only when the real swap feed is unavailable.
- CVD remains `PROXY` unless real trade-side data exists.
- EV remains `NOT_CALIBRATED` until calibrated win probability and payoff distributions exist.
- No trading credentials, private endpoints, order placement, or paid data services are used.

## Operational limits
The live tail repair is bounded to seven days per symbol per run and fetched in API chunks of at most 100 candles. A longer gap is marked degraded rather than pretending the missing interval was repaired. Baseline migration removes duplicate date-stamped snapshots from the current branch tree; it does not rewrite Git history or force-push.
