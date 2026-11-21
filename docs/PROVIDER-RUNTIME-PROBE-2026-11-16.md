# Provider-Neutral Runtime Probe — Evidence Snapshot

**Latest completed multi-symbol run:** GitHub Actions `43885572155`  
**Job:** `probe` — completed successfully  
**Artifact:** `provider-neutral-read-only-probe` (ID `14235285305`, SHA-256 `0245df7a4370b60d9473eb14b12ade79ffe9a5d36210c80fd48dc6d88ea7c60e`)  
**Generated:** 2026-11-16 14:25:48 UTC  
**Mode:** public read-only HTTP GET, no credentials, no trading access  
**Probe version:** 18-endpoint multi-symbol version on commit `3c5585b24722fa0ca5cc6dda489c4d04214d1799`.

## Observed result

| Provider | Probe | HTTP | Result | Observation |
|---|---|---:|---|---|
| CryptoHFTData | BTCUSDT mark price | 200 | PASS | 3,600 rows; schema valid |
| CryptoHFTData | ETHUSDT mark price | 200 | PASS | 3,600 rows; schema valid |
| CryptoHFTData | SOLUSDT mark price | 200 | PASS | 3,600 rows; schema valid |
| CryptoHFTData | FILUSDT mark price | 200 | PASS | 3,600 rows; schema valid |
| CryptoHFTData | BTCUSDT open interest | 200 | PASS | 13 rows; schema valid |
| CryptoHFTData | ETHUSDT open interest | 200 | PASS | 13 rows; schema valid |
| CryptoHFTData | SOLUSDT open interest | 200 | PASS | 13 rows; schema valid |
| CryptoHFTData | FILUSDT open interest | 200 | PASS | 13 rows; schema valid |
| CoinGecko | Public API ping | 200 | PASS | Keyless endpoint reachable |
| CoinMarketCap | Keyless public listings | 429 | RATE LIMITED | Keyless path was rate-limited in this run; not suitable as a reliable core without a free backend key or a lower polling schedule |
| GeckoTerminal | Public DEX networks | 200 | PASS | Keyless public endpoint reachable |
| CoinPaprika | BTC ticker | 200 | PASS | Ticker response returned |
| Alternative.me | Fear & Greed latest | 200 | PASS | Daily sentiment response returned |
| DEX Screener | DEX pair search | 200 | PASS | Keyless pair-search response returned |
| DefiLlama | Chain list | 200 | PASS | 423 chain records |
| DefiLlama | Perpetual DEX open-interest overview | 200 | PASS | Free DEX-perpetual OI overview reachable |
| DefiLlama | DEX volume overview | 200 | PASS | Free DEX-volume overview reachable |
| Coinalyze | Assets endpoint without key | 401 | AUTH REQUIRED | API key required; no key was sent |

**Summary:** 16/18 endpoint probes returned HTTP 200 and passed the applicable JSON/Parquet schema check. The two non-PASS results were CoinMarketCap keyless HTTP 429 and Coinalyze HTTP 401.

## Important CryptoHFTData result

For the tested UTC hour `2026-11-16/12`, the provider supplied mark-price and open-interest files for **all four test symbols: BTCUSDT, ETHUSDT, SOLUSDT and FILUSDT**. The four mark-price files each contained 3,600 rows and the four open-interest files each contained 13 rows. PyArrow parsed the Parquet metadata and schemas successfully.

The BTC mark-price schema includes `received_time`, `event_time`, `symbol`, `mark_price`, `index_price`, `estimated_settle_price`, `funding_rate` and `next_funding_time`. The open-interest schema includes `received_time`, `symbol`, `sum_open_interest`, `sum_open_interest_value` and `timestamp`.

**Engineering significance:** this is the first tested independent archive source that has returned both mark/funding context and OI for FILUSDT in the actual GitHub Actions runtime. It is a strong candidate to investigate for filling the recent FIL tail gap. It does **not** yet prove that the archive contains every missing 15-minute OHLCV candle, because trade-file parsing and 15-minute candle reconstruction have not passed.

## What this proves

- The actual GitHub-hosted runtime can reach CryptoHFTData's public REST download service without an API key.
- It can retrieve and parse hourly BTC/ETH/SOL/FIL mark-price and OI Parquet files from the tested hour.
- CoinGecko, GeckoTerminal, CoinPaprika, Alternative.me, DEX Screener and DefiLlama public endpoints were reachable in this run.
- CoinMarketCap's keyless endpoint was rate-limited at this time; Coinalyze requires a key.

## What this does not prove

- Full semantic validation of all rows, timestamp continuity, duplicate handling, instrument mapping, unit conventions and source corrections.
- Two-year historical coverage: CryptoHFTData documents its archive start as 2025-06-28, so it cannot independently replace the full two-year baseline.
- That trades, liquidations or order-book files for FILUSDT are available and valid.
- That provider terms allow the exact intended distribution or long-term retention.
- That any provider adds predictive value or improves out-of-sample signal quality.
- That the signal engine ran, Telegram delivery succeeded, or Stage 1 passed.

## Next validation

1. Parse CryptoHFTData trade and liquidation Parquet files for FILUSDT and SOLUSDT; verify event timestamps, trade side, quantity and row coverage.
2. Reconstruct 15-minute OHLCV from tick trades for FILUSDT, compare against the current dataset and calculate missing-bar coverage without silently filling gaps.
3. Probe the same target assets across Bybit, OKX, Bitget and Hyperliquid datasets using the provider's symbol-discovery endpoint; do not guess symbol aliases.
4. Compare mark price, funding and OI with a second independent source using aligned instrument IDs and timestamps.
5. Keep CoinMarketCap keyless as rate-limited/UNAVAILABLE unless its documented free key path is available to the backend; do not ask the owner to configure it.
6. Keep Coinalyze as key-required/UNAVAILABLE until a lawful, genuinely free backend credential path exists.
7. Preserve attribution, licence and provider caveats; CoinPaprika Free is personal-use only and CoinDesk Personal is non-commercial.

## Provider caveats

CryptoHFTData's official documentation says the archive begins on 2025-06-28, publishes one UTC-hour Parquet file per symbol/data type, and the last completed hour is typically available about 15 minutes after close. Anonymous REST access is capped at 60 file downloads per minute; a free account key removes that cap, but no key is required for the current bounded probe.

Its known-gaps page is material:
- The 2026-10 data-quality release was still marked **not yet deployed** on the documentation page when checked on 2026-11-16.
- Binance Futures mark-price streams have documented 1–2 minute gaps around HH:02–HH:05 in most hours since at least mid-August 2026; the provider says those ticks cannot be recovered.
- Bybit trade streams can have reconnect gaps from a few seconds to about three minutes.
- Other venue/type combinations have documented timestamp, quantity, duplicate, order-book reset and missing-hour caveats. Consult the exact venue notes and known-gap ledger before using each data type.
- Corrected historical files may replace prior files at the same object key; refresh previously downloaded files after a correction is published.

Therefore, CryptoHFTData is a **high-priority independent archive candidate**, not an unquestioned source of truth. Use it for cross-source validation and carefully bounded backfill, retain venue and timestamp provenance, and do not mark a symbol complete until per-file timestamps, sequence/gap checks, row semantics and cross-source consistency pass.

## Licence boundary and repository visibility

The `Trade` repository is public. CryptoHFTData's official terms (updated 2026-10-06) allow internal research and derived signals/features, but prohibit raw-data redistribution, republishing and embedding the data in a downstream feed or product. They permit derived outputs only when the raw data cannot be reconstructed.

The current probe stores only sanitized metadata in the workflow artifact. Any future adapter must process raw Parquet in the ephemeral runner and must not write the downloaded files to the public `market-data` branch, public workflow artifacts, Pages or Telegram. Only non-reconstructable derived features, quality summaries, provenance and final signals may persist. This is a hard implementation requirement, not an optional optimization.

Official terms: https://www.cryptohftdata.com/terms

## Related source documents

- `docs/USER-DECISIONS-AND-PROVIDER-POLICY-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2-2026-11-16.md`
