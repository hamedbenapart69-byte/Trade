# Provider Screening Addendum — 2026-11-16

This addendum extends `USER-DECISIONS-AND-PROVIDER-POLICY-2026-11-16.md`. These are screening findings, not runtime integration approvals.

## Newly verified candidates

| Provider | Officially documented capability / terms | Best potential use | Limits and cautions | Screening priority |
|---|---|---|---|---|
| **Coinalyze API** | API documentation exposes futures-market metadata, current and historical open interest, funding and predicted funding, liquidation history, long/short ratio history, and OHLCV history. Free API; key generated after sign-up; 40 requests/minute per API key. | Strong candidate for an independent multi-venue derivatives feed and recent OI/funding/liquidation/L-S cross-check. Its OHLCV response includes buy-volume and buy-transaction fields, which may support a measured taker-flow proxy. | Intraday history retains only about 1,500–2,000 datapoints and old points are deleted daily; daily history is retained. API key required. The documentation's free-use wording asks for attribution when data is shown publicly. Need test actual symbol coverage, endpoint call accounting, free key behavior, and whether the intended Telegram publication context is covered by its terms. | **TOP PRIORITY FOR BACKEND PROBE**, especially current derivatives and recent history; not a two-year intraday archive. |
| **CoinDesk Data API — Personal** | Official pricing describes a free Personal plan for non-commercial projects, CC BY-NC-SA 4.0, aggregate REST data, capped lifetime calls, 365 days of daily OHLCV, 7 days of hourly OHLCV, and 1 hour of minute data. | Independent aggregate OHLCV/price cross-check and market context. | Non-commercial license and capped lifetime calls. Hourly and minute history are too short for the full research archive. Check attribution/share-alike obligations and current endpoint authentication. | **SECONDARY CANDIDATE**, subject to licence and quota review. |
| **Alternative.me API** | Official docs expose Fear & Greed and market tickers/global endpoints. The ticker API updates every five minutes and is limited to 60 requests/minute over a 10-minute window. The Fear & Greed API returns historical values with timestamps; attribution is required for the index. | Independent sentiment/macro context, broad market price cross-check. | Fear & Greed is currently Bitcoin-focused; it is a daily sentiment index, not a coin-specific intraday signal. API may be discontinued or changed at provider discretion. | **ACCEPT FOR PROBE** as an auxiliary sentiment source, not a core futures feed. |
| **DEX Screener API** | Official docs expose DEX pair/token search and market data. Pair and token-pair endpoints document up to 300 requests/minute; profile/boost endpoints document 60 requests/minute. | DEX liquidity/volume discovery, token activity and narrative/event screening for assets with meaningful on-chain pools. | DEX pool observations are not centralized perpetual-futures OHLCV, OI, funding or liquidation data. Validate pair identity, chain, liquidity and manipulation risk. | **ACCEPT FOR PROBE** as a separate on-chain/DEX discovery source. |

## Official references

- Coinalyze API docs: https://api.coinalyze.net/v1/doc/
- CoinDesk Personal pricing: https://developers.coindesk.com/pricing/
- CoinDesk daily historical OHLCV: https://developers.coindesk.com/documentation/legacy/Historical/dataHistoday
- Alternative.me API docs: https://alternative.me/crypto/api/
- Alternative.me Fear & Greed API rules: https://alternative.me/crypto/fear-and-greed-index/
- DEX Screener API docs: https://docs.dexscreener.com/api/reference

## Probe plan

1. **Coinalyze:** obtain supported futures market metadata; choose a small representative set (BTC, ETH and a liquid alt); test current OI/funding, historical OI/funding, liquidations, long/short ratio and OHLCV; record actual points returned, symbol coverage, request count and timestamps. Do not request a key from the owner; backend secret setup is an engineering operation only if an approved secret is already available or the provider's free account can be lawfully provisioned without owner-facing work.
2. **CoinDesk:** test keyless/keyed status, lifetime quota behavior and one daily/hourly historical sample; reject if the license does not cover the project's intended distribution.
3. **Alternative.me:** test latest and historical Fear & Greed response, timestamps, attribution, update cadence and ticker/global endpoints.
4. **DEX Screener:** test a known liquid DEX pool and compare pair identity, liquidity, volume and timestamps with a second source; keep DEX evidence separate from perpetual-futures data.
5. All probes must run from the actual GitHub Actions environment or the intended project runtime, be read-only and bounded, and record exact HTTP status, latency, response schema, provider timestamp, source timestamp, rate-limit headers and errors.

## Decision rule

No candidate becomes a production dependency merely because its official docs advertise a free API. It must pass runtime reachability, terms/licensing, schema, freshness, coverage, cost/quota and fallback checks. The user's personal ability to access the provider is not a prerequisite.
