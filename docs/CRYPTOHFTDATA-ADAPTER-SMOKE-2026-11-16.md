# CryptoHFTData Adapter Runtime Smoke — 2026-11-16

**GitHub Actions run:** `43887257922`  
**Job:** `adapter-smoke` — completed successfully  
**Artifact:** `cryptohftdata-internal-adapter-smoke-v5` (ID `14233564464`, SHA-256 `9a96c0e9c14c0a758645ce8d57ee5941c335b4ec5d4bce15390dcb40825ea35d`)  
**Generated:** 2026-11-16 14:35:18 UTC  
**Hour tested:** `2026-11-16 13:00:00 UTC`  
**Repository visibility:** public  
**Mode:** read-only internal processing; raw data not persisted.

## Result

**PASS — 8/8 required snapshots passed** for Binance Futures via CryptoHFTData.

The provider's symbol-discovery endpoint returned:
- 1,003 symbols for `mark_price`
- 923 symbols for `open_interest`
- BTCUSDT, ETHUSDT, SOLUSDT and FILUSDT were present in both lists.

| Symbol | Mark-price rows | Mark-price nulls in required fields | OI rows | OI nulls in required fields |
|---|---:|---:|---:|---:|
| BTCUSDT | 3,600 | 0 | 12 | 0 |
| ETHUSDT | 3,600 | 0 | 12 | 0 |
| SOLUSDT | 3,600 | 0 | 12 | 0 |
| FILUSDT | 3,600 | 0 | 12 | 0 |

For all eight files:
- Parquet parsing succeeded.
- The returned symbol matched the requested symbol.
- Required schema columns were present.
- Required columns had zero nulls.
- The data was processed in memory; `raw_file_persisted=false`.

For the tested hour, mark-price `event_time` spans 13:00:00–13:59:59 UTC (3,600 one-second rows). OI `timestamp` spans 13:00–13:55 UTC (12 five-minute observations). These are observed sample characteristics, not a guarantee for all hours or venues.

## Engineering interpretation

1. CryptoHFTData is a strong candidate for recent mark-price, funding-context and OI enrichment across the four tested Binance USDⓈ-M symbols.
2. The test confirms **recent FILUSDT mark-price and OI availability**, so it is worth testing as a source for the current FIL tail gap.
3. It does not yet supply a proven replacement for the project's full two-year 15-minute OHLCV baseline. The archive starts on 2025-06-28.
4. It does not yet prove trade-file availability, 15-minute OHLCV reconstruction, taker-flow quality or liquidation coverage. Those are the next probes.
5. This tested dataset is specifically `binance_futures` data delivered by a separate archive provider. It is not a user account connection, but its underlying observations originate from the venue's public market feeds.

## Freshness caveat

The smoke ran at 14:35:18 UTC against the 13:00–14:00 UTC file, so the tested hour ended 35 minutes before retrieval. This does not measure the earliest publication time; it only records the observed age at this run. For short 30-minute LRT decisions, the system must use a separate fresh current-price/market feed and enforce its freshness gate. Do not promote an old hourly archive snapshot to `BUY_NOW` by assumption.

## Licence and retention

CryptoHFTData terms permit internal research and derived signals/features that cannot reconstruct the raw feed, but prohibit redistribution or republishing of raw data. Because the Trade repository is public:
- Raw Parquet remains in runner memory only.
- No raw Parquet or reconstructable tables are written to the public `market-data` branch or workflow artifacts.
- Only non-reconstructable metadata, quality metrics, features and signal outputs may persist.

## Next validation

- Probe and parse FILUSDT and SOLUSDT `trades` files and FILUSDT `liquidations` files.
- Verify trade IDs, event/trade/received timestamps, decimal price/quantity semantics and buyer-maker direction.
- Exclude `order_type=NA` rows from price/volume/VWAP calculations while retaining trade IDs for sequence-gap checks.
- Reconstruct 15-minute OHLCV in memory and compare coverage with the current Stage 1B tail, without publishing raw or re-aggregated provider data.
- Cross-check the same timestamps against a second independent provider.
- Only after evidence passes, propose a separate integration into Stage 1B. This PR remains isolated and does not change the active pipeline.

## Official references

- REST API and hourly file structure: https://www.cryptohftdata.com/docs/rest-introduction
- Binance Futures wire semantics: https://www.cryptohftdata.com/docs/wire-format-binance-futures
- Provider terms: https://www.cryptohftdata.com/terms
