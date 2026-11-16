# Provider Screening Addendum 2 — Market Aggregators and DEX Data

**Date:** 2026-11-16  
**Status:** Official-documentation screen; runtime and licence checks still pending.

## Additional findings

| Provider | Official free access | Useful data | Important limits / decision |
|---|---|---|---|
| **CoinMarketCap** | Two free options are documented: keyless access to a curated subset of 35+ live endpoints, or Basic at $0 with a free Developer Portal account, 15,000 monthly call credits and 50 requests/minute. | Asset discovery, live quotes/listings, market pairs, metadata and global market metrics; selected historical endpoints. | Strong candidate for independent market-wide discovery and metadata. Free Basic requires a provider API key but no credit card is stated in the provider's signup guide. Endpoint history depth varies; do not assume it supplies full intraday perpetual derivatives. |
| **GeckoTerminal Public API** | CoinGecko support documentation describes a free beta public API with no paid plan and 30 requests/minute. | On-chain DEX pools, token/pair pricing, volume and liquidity for a very broad token universe. | Useful for DEX discovery and on-chain liquidity context, not centralized perpetual futures OHLCV, funding or OI. Check current public API terms and schema before use. |
| **CoinGecko Public API** | Official support page (updated 2026-11-03) says keyless Public API is rate-limited to 5–15 calls/minute; a free Demo account provides a stable 100 calls/minute. The Demo tier has a 10,000 monthly-call cap. | Broad asset metadata, aggregated price/market data, derivatives-market metadata and selected on-chain endpoints. | Keyless access is a lower-rate path; Demo key requires provider account creation on the backend. Historical interval depth varies by endpoint and tier. |
| **CoinMarketCap Keyless Public API** | No signup or key for a curated subset of live endpoints. | Rapid one-off market discovery and metadata probes. | The keyless subset is not a substitute for the full Basic API; use only documented endpoints. |
| **Dune** | Free plan is view-only for dashboards and queries. | Public on-chain dashboards and research results that already exist. | Query execution/API is not included in free view-only access; a 7-day trial is not a qualifying zero-cost dependency. Exclude from the automated core. |
| **Santiment** | Search surfaced an older access-plan document from 2019, not a sufficiently current official plan specification. | Potential on-chain/social metrics. | **UNVERIFIED** until current official free quotas, retention and terms are established. Do not rely on stale plan details. |

## Source references

- CoinMarketCap free/keyless API FAQ: https://coinmarketcap.com/api/faq/
- CoinMarketCap API pricing and plan details: https://coinmarketcap.com/api/
- CoinMarketCap authentication and credit accounting: https://coinmarketcap.com/api/documentation/guides/authentication
- CoinGecko public API rate limit (updated 2026-11-03): https://support.coingecko.com/articles/5125303456-what-is-the-rate-limit-for-coingecko-api-public-plan
- GeckoTerminal API availability and free limit (updated 2026-10-02): https://support.coingecko.com/articles/6867086195-does-geckoterminal-have-an-api
- Dune free plan and query-execution boundary: https://dune.com/pricing
- Santiment access plans (historical 2019 page; not accepted as current evidence): https://santiment.github.io/articles/access-plans/

## License and distribution note

CoinPaprika's current official API page states its free tier is for personal use and requires a “Powered by CoinPaprika” credit; commercial use begins with a paid plan. Therefore, CoinPaprika is not approved for a public/commercial signal-distribution product under the free tier unless the provider confirms the intended use is permitted. It remains a conditional candidate for strictly personal/internal use only.

CoinDesk's Personal tier is explicitly non-commercial and uses CC BY-NC-SA 4.0. It is not approved for public/commercial redistribution without a compatible licence. The intended Telegram channel's audience and distribution model must be reflected in the licence review before production use.

## Probe expansion

Add CoinMarketCap keyless and GeckoTerminal public endpoints to the bounded read-only runtime probe. Do not add Dune query execution or stale Santiment assumptions. Any provider key needed for free tiers remains a backend-only credential and must never be requested from the owner as a user-facing setup task.
