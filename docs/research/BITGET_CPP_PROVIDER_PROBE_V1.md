# Bitget C++ Public Futures Provider Probe v1

**Status:** RESEARCH ONLY — not connected to the production provider chain.  
**Production language:** C++20.  
**Access boundary:** public unauthenticated GET endpoints only. No API key, account endpoint, trading permission, or order route.

## Why this probe exists

The current production C++ market-data adapter is OKX-only. A provider-health HTTP response from a second venue is not an acceptable fallback. Before a venue can be considered, the same instrument must provide complete and correctly normalized public inputs under the V18.2 data contract.

This isolated probe checks BTCUSDT and ETHUSDT from Bitget V3. It deliberately does not send Bitget data into the production L1 contract or merge any data with OKX.

## Official endpoints used

- Instruments: `GET /api/v3/market/instruments?category=USDT-FUTURES`
- Tickers: `GET /api/v3/market/tickers?category=USDT-FUTURES`
- Historical 1H candles: `GET /api/v3/market/history-candles`
- Historical funding: `GET /api/v3/market/history-fund-rate`
- Historical open interest: `GET /api/v3/market/open-interest-history?period=1h`

Official references:
- [Bitget Market Data V3](https://www.bitget.com/docs/catalog/market/market-data)
- [Bitget Derivatives and Funding Rate V3](https://www.bitget.com/docs/catalog/market/derivatives)
- [Bitget V3 API changelog](https://www.bitget.com/legacy-docs/uta/changelog)

## Acceptance gates

For each tested symbol:

1. Instrument is online, perpetual, crypto type, and USDT quoted.
2. 24-hour quote turnover is strictly greater than USD 10,000,000.
3. Closed 1H OHLCV covers two years or the complete time since listing, with no missing 1H intervals in the measured span.
4. Funding history covers at least 30 days, including the contract's published funding interval.
5. Historical OI at 1H covers at least 30 days with no missing hourly intervals.
6. Prices, timestamps, funding rates, OI, volume units and quote notional pass normalization checks.

A failed or missing field remains unavailable. The code keeps Bitget's OHLCV volume in BASE_COIN units and OI in BASE_COIN / USDT value units. It never relabels base-coin volume as contracts.

## Version and scope

- v1 is a live research probe only.
- No fallback order is changed.
- No production adapter is registered.
- No cross-venue dataset is merged.
- Promotion requires a separate equivalence review for contract identity, listing time, quote/base/settlement, volume units, funding intervals, OI units, candle finality and history continuity.
- Even a successful BTC/ETH probe does not prove coverage for the full 100-symbol universe.

## SLRP status

- Objective: determine whether Bitget can independently satisfy the L1 public futures data requirements for the two reference symbols.
- Acceptance: the six gates above.
- v1: awaiting C++20 build, fixture tests and live GitHub Actions evidence.
- D1–D6: diagnosis will be written only from observed test or endpoint results.
- v2/v3: not built unless v1 records a measured failure; R11 remains in force.
- Escalation: if any required market history is unavailable, record the exact endpoint/status/coverage. Do not replace it with a spot market or another venue's fields.
- Budget: maximum three versions; research-only, no production activation.

## Live result

Pending GitHub Actions evidence. No successful live Bitget coverage is claimed in this source file.
