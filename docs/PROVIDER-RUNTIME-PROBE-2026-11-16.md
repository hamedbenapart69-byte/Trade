# Provider-Neutral Runtime Probe — Evidence Snapshot

**Latest run:** GitHub Actions `43885281503`  
**Job:** `probe` — completed successfully  
**Artifact:** `provider-neutral-read-only-probe` (ID `14234176523`, SHA-256 `362ad50768a16810abca20a9d50f62169130375bae701507d88990dbce357302`)  
**Generated:** 2026-11-16 14:23:59 UTC  
**Mode:** public read-only HTTP GET, no credentials, no trading access  
**Probe version:** 12-endpoint version on commit `b7d604875fee1017b049ff542e560ff17ff2120d`.

## Observed result

This is a reachability and response-schema probe, not a data-quality or production acceptance test.

| Provider | Probe | HTTP | Result | Latency | Observation |
|---|---|---:|---|---:|---|
| CryptoHFTData | BTC futures mark-price Parquet | 200 | PASS | 1,956 ms | 105,285 bytes; PyArrow validated 3,600 rows; columns: received_time, event_time, symbol, mark_price, index_price, estimated_settle_price, funding_rate, next_funding_time |
| CryptoHFTData | BTC futures open-interest Parquet | 200 | PASS | 1,372 ms | 2,231 bytes; PyArrow validated 13 rows; columns: received_time, symbol, sum_open_interest, sum_open_interest_value, timestamp |
| CoinGecko | Public API ping | 200 | PASS | 145 ms | JSON object returned without key |
| CoinMarketCap | Keyless public listings | 200 | PASS | 261 ms | JSON object returned without key |
| GeckoTerminal | Public DEX networks | 200 | PASS | 90 ms | JSON response returned |
| CoinPaprika | BTC ticker | 200 | PASS | 152 ms | JSON ticker returned |
| Alternative.me | Fear & Greed latest | 200 | PASS | 184 ms | Provider timestamp `1794787200` = 2026-11-16 00:00:00 UTC |
| DEX Screener | DEX pair search for BTC | 200 | PASS | 64 ms | JSON response returned |
| DefiLlama | Chain list | 200 | PASS | 138 ms | JSON array with 423 entries |
| DefiLlama | Perpetual DEX open-interest overview | 200 | PASS | 123 ms | Aggregated protocol/chain OI structure returned |
| DefiLlama | DEX volume overview | 200 | PASS | 189 ms | Aggregated DEX protocol/chain volume structure returned |
| Coinalyze | Assets endpoint without key | 401 | AUTH REQUIRED | 234 ms | Confirms API key is required; no key was sent |

**Summary:** 11/12 endpoint probes returned HTTP 200 and passed their applicable JSON/Parquet schema checks. Coinalyze returned HTTP 401, so it is not usable anonymously from this runtime.

## What this proves

- GitHub-hosted runtime could reach the tested public endpoints at the recorded time.
- CryptoHFTData delivered actual BTC futures Parquet files and PyArrow parsed both schemas: 3,600 mark-price rows and 13 open-interest rows for the tested hour. The mark-price file includes funding_rate and next_funding_time columns.
- CoinGecko keyless ping, CoinMarketCap keyless listings, GeckoTerminal, CoinPaprika ticker, Alternative.me sentiment, DEX Screener search and DefiLlama endpoints were reachable.
- Coinalyze requires an API key for the tested endpoint.

## What this does not prove

- Full semantic validation of all rows, timestamp continuity, duplicate handling, instrument mapping, unit conventions and source corrections. Only schema and row count were validated for the two BTC files.
- Full symbol or market coverage, history depth, completeness, or timestamp alignment.
- That provider terms allow the exact intended distribution or long-term retention.
- That every GitHub Actions run or another compute region has the same reachability.
- That any provider adds predictive value or improves out-of-sample signal quality.
- That the signal engine ran, Telegram delivery succeeded, or Stage 1 passed.

## Next validation

1. Extend CryptoHFTData probes to ETH, SOL and FILUSDT; current runtime evidence covers BTC only.
2. Validate CryptoHFTData trades and liquidation files, and test whether order-book files can be consumed within bounded storage/runtime limits.
3. Compare CoinMarketCap keyless and GeckoTerminal data with a second independent provider; this run only validates reachability and response shape.
4. Probe at least one symbol that is absent/incomplete in the current Stage 1B dataset.
5. Compare the same fields across independent sources with explicit instrument and timestamp alignment.
6. Preserve provider attribution and license constraints; CoinPaprika Free is documented for personal use only, and any public/commercial distribution needs a separate license review.
7. Keep Coinalyze as key-required/UNAVAILABLE until a lawful, genuinely free backend credential path exists; do not ask the owner to perform provider setup.

## Related source documents

- `docs/USER-DECISIONS-AND-PROVIDER-POLICY-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2-2026-11-16.md`
