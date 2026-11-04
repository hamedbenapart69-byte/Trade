# Independent market-data adapters

This document records the currently implemented public, read-only adapters. It is not a guarantee that any provider is reachable from every country or network.

| Provider | Current adapter | Data returned | Important limitations |
|---|---|---|---|
| CoinGecko | `app/integrations/coingecko.py` | Allowlisted simple spot-price snapshot and 24h change | Current adapter is intentionally limited to seven allowlisted assets and USD/EUR; it is not a universe scanner or OHLCV feed. |
| DexScreener | `app/integrations/dexscreener.py` | Search-result DEX pools, chain/pair identity, price, liquidity, FDV/market cap where supplied, 24h volume/change and transactions | Search results are not a complete token universe and their order is not a quality ranking. Missing fields remain null. Pool/token identity and contract risk require independent checks. |
| DeFiLlama | `app/integrations/defillama.py` | Protocol directory, category, chains, TVL, 1d/7d changes and market cap where supplied | Protocol-level TVL is not token valuation, token-holder flows or proof of sustainable revenue. Protocols may not map one-to-one to tradable tokens. |

## Data integrity rules

- Each adapter is read-only and uses a fixed provider hostname; callers cannot supply arbitrary URLs.
- HTTP failures, invalid JSON and invalid top-level schemas raise provider-specific errors. They are never converted to empty successful snapshots.
- Provider fields that are absent, malformed or non-finite are represented as `None` or cause the record to be skipped; no synthetic price, liquidity, market cap, TVL or volume is generated.
- DexScreener records include retrieval time and exact chain/pair identifiers. DeFiLlama records retain provider identity and protocol slug.
- A provider response is a raw observation, not a buy signal. It must pass freshness, liquidity, contract, manipulation and cross-source validation gates before scoring.
- No exchange account credentials, private endpoints, order placement or trade execution are used.

## Availability and operational caveats

Public endpoints and free access policies can change, rate-limit, block traffic or vary by region. Connectivity from Iran, including any VPN-dependent behavior, has not been verified by this code or CI. Before relying on a provider, deploy-time health checks must record success/failure, latency, response age and rate-limit headers without exposing secrets. A failed source must lower coverage and may result in `INSUFFICIENT_DATA`; it must not be silently replaced with invented values.

## Not yet implemented

These adapters do not yet constitute a complete scanner. The following remain separate milestones: paginated global asset-universe discovery; multi-timeframe OHLCV; reliable token-to-protocol mapping; on-chain holder/exchange flows; derivatives/funding/open-interest; unlock calendars; contract honeypot/rug checks; source consensus; persistent historical storage; alert scheduling; backtesting and paper-trading. No profitability or signal accuracy claim is justified before those stages and out-of-sample validation.
