# Data Readiness Audit — Education Research

**Audit date:** 2026-11-10  
**Repository:** `hamedbenapart69-byte/Trade`  
**Inspected data ref:** `market-data`  
**Purpose:** Determine which educational hypotheses can be tested honestly with data already persisted, and which require a bounded data-expansion phase.

## 1. Persisted data inventory

### OHLCV

The `STAGE1_COMPLETE.json` manifest reports:

- Provider: OKX public market-data API.
- Universe: 100 active symbols; 100 successful; 0 failed.
- Timeframe: 1 hour.
- History: 2024-11-08 through 2026-11-08.
- Rows: 1,753,200 total (17,532 per symbol).
- Missing intervals estimate: 0.
- Gap-free symbols: 100/100.
- Requested-window coverage: 100% for all successful symbols.

This supports OHLCV-only event studies on the archived 1h timeframe. It does not provide the originally specified 15m H1 data.

### Funding and open interest

- Funding files exist for the 100-symbol universe, but the manifest reports approximately 94 days of coverage (2026-08-06 through 2026-11-08), not two years.
- BTC funding: 283 rows, 94 days, 12.868% of the two-year requested window.
- Open-interest history is limited to the latest 30 days (720 hourly rows per symbol in the manifest).
- Therefore, funding and OI cannot be treated as complete two-year historical covariates.

### Order book

The latest persisted L2 sample summary reports:

- 1,773 rows across OKX, Bybit and KuCoin.
- 10 symbols: BTC, ETH, SOL, XRP, DOGE, ADA, LINK, LTC, BCH and AVAX.
- Captured at 2026-11-10 17:54:46 UTC.
- This is a point-in-time collection, not a continuous historical order-book sequence.
- The Stage-1 manifest explicitly states that no historical order-book snapshots are stored.

This sample can verify schema/provider connectivity only. It cannot support historical absorption, spoofing, iceberg or depth-replenishment claims.

### Other unavailable series

The Stage-1 manifest explicitly marks these as unavailable:

- Verified historical liquidation feed.
- Continuous historical basis series.
- Two-year open-interest history.
- Historical order-book snapshots.

The current `market-data` tree contains no persisted trade-tape archive. Therefore, H3/H4 cannot currently be run as real historical order-flow studies from the repository's stored data.

## 2. Public OKX trade-history feasibility

Official OKX API documentation describes:

- `GET /api/v5/market/history-trades` as historical public transactions from the last three months, with pagination.
- Maximum 100 records per response.
- Rate limit: 20 requests per 2 seconds per IP.
- Trade response includes `side` as the taker side (`buy` or `sell`), price, size, trade ID and timestamp.

Official reference: https://www.okx.com/docs-v5/en/#rest-api-market-data-get-trades-history

This is a technically viable zero-key/public-data route for a bounded recent trade archive. It does not provide two years of trade history, and the 100-record page size can make a full 90-day multi-symbol backfill expensive in runtime and storage. No such backfill has been run or claimed in this audit.

## 3. Hypothesis readiness

| Hypothesis | Available data | Honest status |
|---|---|---|
| H1 sweep/reclaim | 2y 1h OHLCV | 1h adaptation tested; original 15m version unavailable |
| H2 volume-profile acceptance/rejection | No volume-at-price archive | Real VAH/VAL/POC blocked |
| H2 time-boundary rejection | 2y 1h OHLCV | Implemented as `H2_TIME_REJECTION_PROXY`; not a real volume profile |
| H3 price/CVD divergence | No stored trade tape; public history endpoint max 3 months | Real version blocked pending capture and continuity validation |
| H4 absorption | No continuous synchronized trade + order-book archive | Real version blocked |
| H5 imbalance breakout | 2y 1h OHLCV | Price-only proxy tested; real delta version blocked |
| H6 breakout/retest | 2y 1h OHLCV | Tested as OHLCV event pre-screen |
| H7 HTF/LTF gate | 2y 1h OHLCV; 4h resampled | Tested as OHLCV filter pre-screen |
| H8 Direction/Location/Confirmation | H1/H5 price triggers plus completed 4h EMA20/EMA50 direction filter | H8_LRT_DLC and H8_NMT_DLC pre-screened separately; only direction-gate ablation is complete, not independent location/confirmation ablations |

## 4. Decision and next evidence required

1. Keep H2_TIME_REJECTION_PROXY explicitly separate from real volume-profile logic.
2. Do not label OHLCV volume allocation as real POC/VAH/VAL, CVD, delta, footprint or absorption.
3. A bounded OKX trade-history collector can be evaluated for a limited liquid-symbol set, but its maximum three-month lookback is shorter than the project's 6m-train / 2m-test walk-forward policy. It is suitable for data-pipeline validation and recent microstructure research, not a full Stage-8 OOS pass.
4. H3 requires at least a validated, continuous trade-side series with contract-size normalization and timestamp checks.
5. H4 additionally requires synchronized order-book snapshots/deltas with sequence continuity. A one-time snapshot cannot substitute for this.
6. A full H2 real profile implementation requires actual volume-at-price data or sufficiently granular trade prints, with a fixed 24/7 session definition.
7. H8 now has two isolated price-only variants: H1 + completed 4h direction gate for LRT, and H5 + completed 4h direction gate for NMT. The direction-gate ablation is tested against unfiltered H1/H5; location and confirmation have not been separately ablated. Do not treat these variants as validated strategies.

**Disposition:** Current data supports OHLCV research prototypes only. Real order-flow and volume-profile claims remain blocked. No production integration or strategy acceptance is authorized by this audit.
