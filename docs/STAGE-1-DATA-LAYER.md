# Stage 1 — Data Layer

## Objective and active implementation
- Target: 100 active USDT-margined perpetual contracts, including BTCUSDT.
- Historical target: at least two years of 1h OHLCV and funding history where exposed by the provider.
- Fear & Greed: daily historical series from Alternative.me.
- Storage: UTC-normalized Parquet, deterministic deduplication, atomic replacement.
- No account credentials, private API keys, or order execution.
- Active collection provider: **OKX public REST through CCXT**. Binance remains a tested but blocked provider.

## Network evidence (GitHub-hosted runner, 2026-11-08)
- Binance USD-M REST: 5/5 attempts per tested endpoint returned HTTP 451. This is a network/geographic restriction on the GitHub runner's egress; it does not prove the user's Iranian ISP result.
- Bybit public REST: HTTP 403 from the same runner.
- OKX public REST: 6/6 checks passed (instruments, tickers, candles, funding, current OI, and OI history); HTTP 200.
- Alternative.me Fear & Greed: HTTP 200, valid value 28 at probe time.
- The user’s own Iranian network has not been tested by this runner. The probe script can be run locally with VPN off/on to record the user's actual route.

## Universe selection
At collection time, CCXT loads active linear USDT perpetuals, filters for contracts whose listing timestamp is at least the requested history window old, ranks by 24h quote volume, and includes BTC. This avoids claiming two years of history for newly listed contracts.

## Data coverage boundaries
- OHLCV: 1h history requested for two years; the report computes expected rows, coverage rate, internal gaps, and first/last UTC timestamps per symbol.
- Funding: paginated historical funding records; report records actual first/last timestamps and row count.
- Open interest: latest 30 days only in this Stage 1 implementation; it is not represented as a two-year series.
- Order-book history: not collected.
- Historical liquidations: not collected.
- Continuous historical basis: not collected.
- Missing order-book/liquidation/basis inputs must be marked unavailable or PROXY in LFS/NSS; do not fabricate them.

## Source licensing decision
Binance Data Vision archives were technically reachable from the GitHub runner and sample checksums were verified. However, the current Binance Vision Dataset Terms (updated 2026-08-26) grant a non-commercial license and expressly prohibit live proprietary trading execution and automated commercial order generation. Because this project is intended to produce trading signals, the archive is not selected as the operational signal-data source. See the official terms in the Binance public-data repository:
https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md

## Commands
Endpoint probe:
`python scripts/run_stage1_data.py --provider okx --probe-only`

Full collection:
`python scripts/run_stage1_data.py --provider okx --symbols 100 --years 2`

Outputs:
`data/stage1/`

## PASS gate
Stage 1 is not PASS merely because endpoints respond. PASS requires:
- 100 selected and successfully collected symbols;
- at least two years of OHLCV coverage for every selected symbol;
- no internal OHLCV gap greater than one hour;
- schema validation, UTC timestamps, and idempotent Parquet writes;
- at least two years of funding coverage where the provider supports it, with any shorter coverage disclosed;
- a valid Fear & Greed historical series;
- explicit, separate OI coverage and data limitations.

A failed symbol or incomplete history remains visible in the report; no synthetic fill is used to make the gate pass.
