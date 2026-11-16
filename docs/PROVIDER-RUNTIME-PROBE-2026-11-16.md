# Provider-Neutral Runtime Probe — Evidence Snapshot

**Run:** GitHub Actions `43884814188`  
**Job:** `probe` — completed successfully  
**Artifact:** `provider-neutral-read-only-probe` (ID `14233462529`, SHA-256 `f241e58164b951d2801a2c46f476edc6caec60bf5183b6f7db666403a7cb871c`)  
**Generated:** 2026-11-16 14:21:32 UTC  
**Mode:** public read-only HTTP GET, no credentials, no trading access  
**Probe version:** initial 8-endpoint version on commit `530e43df2f4ca2dde02b146054e30fd096cf7514`.

## Observed result

<summary>
This was a reachability and response-shape probe, not a data-quality or production acceptance test.
</summary>

| Provider | Probe | HTTP | Result | Latency | Observation |
|---|---|---:|---|---:|---|
| CryptoHFTData | BTC futures mark-price Parquet | 200 | PASS | 1,967 ms | 105,285 bytes; Parquet magic valid |
| CryptoHFTData | BTC futures open-interest Parquet | 200 | PASS | 1,475 ms | 2,231 bytes; Parquet magic valid |
| CoinGecko | Public API ping | 200 | PASS | 131 ms | JSON object returned without key |
| CoinPaprika | BTC ticker | 200 | PASS | 47 ms | `last_updated=2026-11-16T14:19:14Z` |
| Alternative.me | Fear & Greed latest | 200 | PASS | 307 ms | Provider timestamp `1794787200` = 2026-11-16 00:00:00 UTC |
| DEX Screener | DEX pair search for BTC | 200 | PASS | 75 ms | JSON response, 25,043 bytes |
| DefiLlama | Chain list | 200 | PASS | 43 ms | JSON array with 423 entries |
| Coinalyze | Assets endpoint without key | 401 | AUTH REQUIRED | 235 ms | Confirms API key is required; no key was sent |

**Summary:** 7/8 endpoint probes returned HTTP 200 and passed the limited response-shape check. Coinalyze returned HTTP 401, so it is not usable anonymously from this runtime.

## What this proves

- GitHub-hosted runtime could reach the tested public endpoints at the recorded time.
- CryptoHFTData delivered actual Parquet-formatted files for BTC futures mark price and open interest.
- CoinGecko keyless ping, CoinPaprika ticker, Alternative.me sentiment, DEX Screener search and DefiLlama chain metadata were reachable.
- Coinalyze requires an API key for the tested endpoint.

## What this does not prove

- Full Parquet schema/row validation; this probe checked only the Parquet file magic and byte count.
- Full symbol or market coverage, history depth, completeness, or timestamp alignment.
- That provider terms allow the exact intended distribution or long-term retention.
- That every GitHub Actions run or another compute region has the same reachability.
- That any provider adds predictive value or improves out-of-sample signal quality.
- That the signal engine ran, Telegram delivery succeeded, or Stage 1 passed.

## Next validation

1. Parse CryptoHFTData Parquet files with PyArrow/Polars and validate schemas, rows, timestamp ranges, duplicates, gaps and field semantics.
2. Repeat the probe with CoinMarketCap keyless and GeckoTerminal public endpoints; these were added after this initial run and are not represented in the 8-endpoint artifact.
3. Probe several liquid altcoins and at least one symbol that is absent/incomplete in the current Stage 1B dataset.
4. Compare the same fields across independent sources with explicit instrument and timestamp alignment.
5. Preserve provider attribution and license constraints; CoinPaprika Free is documented for personal use only, and any public/commercial distribution needs a separate license review.
6. Keep Coinalyze as key-required/UNAVAILABLE until a lawful, genuinely free backend credential path exists; do not ask the owner to perform provider setup.

## Related source documents

- `docs/USER-DECISIONS-AND-PROVIDER-POLICY-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2026-11-16.md`
- `docs/PROVIDER-SCREENING-ADDENDUM-2-2026-11-16.md`
