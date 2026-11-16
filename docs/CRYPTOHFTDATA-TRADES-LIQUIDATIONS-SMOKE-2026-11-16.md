# CryptoHFTData Trades and Liquidations Smoke — 2026-11-16

**GitHub Actions run:** `43887793170`  
**Job:** `adapter-smoke` — completed successfully  
**Artifact:** `cryptohftdata-internal-adapter-smoke-v6` (ID `14234324684`, SHA-256 `a239f78ecf043991da1ebb5d39cbf11c19977ede0fee2d87d6a2a981651430c2`)  
**Generated:** 2026-11-16 14:38:16 UTC  
**Hour tested:** `2026-11-16 13:00:00 UTC`  
**Mode:** read-only; raw data parsed in memory and not persisted.

## Core market snapshots

**PASS — 8/8** mark-price and open-interest snapshots for BTCUSDT, ETHUSDT, SOLUSDT and FILUSDT:
- Each mark-price file: 3,600 rows, valid schema.
- Each open-interest file: 12 rows, valid schema.
- Required columns had zero nulls; requested symbol identity matched.

## Trade and liquidation snapshots

**PASS — 3/3** optional files:

| Symbol | Data type | Rows | Schema | Quality observations |
|---|---|---:|---|---|
| FILUSDT | Trades | 16,261 | Valid | 16,261 unique trade IDs; 0 duplicates; 0 internal ID gaps; all 16,261 rows had positive price and quantity; order_type=MARKET for all rows |
| SOLUSDT | Trades | 77,599 | Valid | 77,599 unique trade IDs; 0 duplicates; 0 internal ID gaps; 4 rows had order_type=NA and were identified for exclusion from OHLCV/volume calculations |
| FILUSDT | Liquidations | 3 | Valid | 1 SELL and 2 BUY events; source semantics are sampled force-order observations, not a complete liquidation tape |

Trade direction counts from the source's `is_buyer_maker` field:
- FILUSDT: 7,264 true; 8,997 false.
- SOLUSDT: 40,135 true; 37,464 false.

Per Binance Futures wire semantics, `is_buyer_maker=true` means the buyer was maker and the seller was taker; `false` means the buyer was taker. `order_type=NA` rows have zero price and quantity and must be excluded from OHLCV/volume calculations while retaining their trade IDs for continuity checks.

The liquidation file is a sampled force-order feed. Its counts and volumes must be treated as `PROXY` / `SAMPLED_LOWER_BOUND`, never as complete market-wide liquidation totals.

## Engineering interpretation

1. The archive supplies a valid FILUSDT trade file for the tested hour, so reconstructing 15-minute FIL candles from trades is technically feasible for this sample.
2. Trade IDs were unique and internally continuous for the tested FIL and SOL files. This is a one-hour sample, not a guarantee of continuous history.
3. The adapter now supports mark price, open interest, trades and liquidations in memory.
4. No OHLCV reconstruction or comparison against the Stage 1B dataset has yet been accepted.
5. No raw provider data or reconstructed candles were persisted to the public repository or workflow artifact.

## Next validation

- Reconstruct 15-minute OHLCV in memory from FILUSDT trades, excluding `order_type=NA`, nonpositive price/quantity and out-of-window rows.
- Compare the reconstructed candles with overlapping Stage 1B FILUSDT 15-minute bars using exact timestamp alignment and separately measured OHLC and volume differences.
- Identify the exact 200 missing FILUSDT timestamps in the latest data report; test whether the archive covers every missing hour without gaps.
- Preserve the rule that no synthetic zero-volume or forward-filled candles may be created.
- Keep liquidation metrics labelled as sampled lower bounds.
- Only after a successful coverage and comparison report should a separate PR integrate this source into the active Stage 1B compute path.

## Licence boundary

The Trade repository is public. CryptoHFTData raw files are processed in memory only. The terms permit internal research and derived signals/features that cannot reconstruct the raw feed, but prohibit raw-data redistribution and republishing. The smoke artifact contains only counts, schemas, null counts, timestamp ranges and quality metrics.

## Official references

- Binance Futures trade wire format: https://www.cryptohftdata.com/docs/wire-format-binance-futures
- CryptoHFTData REST: https://www.cryptohftdata.com/docs/rest-introduction
- CryptoHFTData terms: https://www.cryptohftdata.com/terms
