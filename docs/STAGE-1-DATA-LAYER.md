# Stage 1 — Data Layer (V1)

## Contract
- Public read-only market data only. No account credentials, private API keys, or order execution.
- V1: CCXT + Parquet.
- 100 active USDT linear perpetual symbols, including BTCUSDT.
- Two years of 1h OHLCV and historical funding where the venue exposes it.
- Fear & Greed daily history from Alternative.me.
- UTC millisecond timestamps, schema validation, deterministic deduplication, atomic Parquet replacement.
- Every symbol receives a coverage/gap report; failures remain explicit.

## Known source boundary
Binance USD-M `/futures/data/openInterestHist` exposes only the latest one month of history. Stage 1 therefore stores OI history for the available month and labels it; it does not claim two years of OI. Current OI is a snapshot, not a historical series.

Historical order-book snapshots, historical liquidation feed and a continuous basis history are not included in this V1 dataset. They must be treated as PROXY or unavailable in later LFS/NSS modules, with stricter thresholds.

## Network probe
`python scripts/run_stage1_data.py --probe-only`

The probe makes up to five attempts against Binance USD-M public endpoints and checks Bybit public server time as a candidate fallback. A GitHub Actions run measures GitHub runner egress, not the user's Iranian ISP/mobile network. Run the probe locally from the target Iranian network (VPN off and on as separate runs) for an actual location-specific result.

## Full collection
`python scripts/run_stage1_data.py --symbols 100 --years 2`

Output is under `data/stage1/`; the directory is ignored by Git and must be uploaded as a workflow artifact or stored in a user-controlled data bucket. Re-running the same collection replaces deterministic Parquet files atomically and deduplicates rows by timestamp.

## V1 limitations / gate
A successful endpoint smoke test is not a two-year coverage pass. Stage 1 is PASS only after the full collection report shows 100 successful symbols, at least two years of OHLCV/funding coverage, no OHLCV gap greater than one hour, valid UTC/schema, and a successful Fear & Greed history. OI's one-month history limitation is separately disclosed and does not get silently padded.
