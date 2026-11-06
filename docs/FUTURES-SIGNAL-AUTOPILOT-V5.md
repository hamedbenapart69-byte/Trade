# Futures Signal Autopilot V5

The authoritative requirements are the uploaded `Futures_Signal_Autopilot_V5.pdf` (52 pages). This branch adds a read-only scanner to the existing Trade control plane. It does not modify the separate Trader_me repository.

## Free public data sources

- **CoinGecko Public API**: discovers the top 100 coins by market-cap rank; the set is then ranked by reported 24-hour spot volume. One discovery request per scan; no account or API key is configured.
- **OptimistFi Perps Data API**: public, no key or account. Supplies matched crypto perpetual assets across 44 venues, OI-weighted mark price, volume, OI, hourly-normalized funding, venue leverage caps, price dispersion and venue-level fields. The provider documents a 4-second refresh. The system consumes the aggregator endpoint, not exchange account APIs.
- **GeckoTerminal Public API**: no key; supplies numerical DEX spot OHLCV. The free public API has a 30-request/minute rate limit. Requests are paced at about one every 2.05 seconds. A 30-asset scan can take about five minutes.

## Implemented in this branch

- Top-100 CoinGecko discovery, duplicate-symbol and configured stablecoin/wrapped-asset exclusions, ranked by 24-hour spot volume.
- Matching against OptimistFi crypto perpetual assets and their aggregated venue data.
- GeckoTerminal pool resolution using the CoinGecko token ID, with explicit WBTC/BTC and WETH/ETH proxy mappings; pools below USD 100,000 reserve are excluded.
- Completed 15m, 1h, 4h and 1d DEX spot OHLCV retrieval, continuity/OHLC/duplicate/order/freshness checks.
- Deterministic RSI(14), EMA20/50/200 where enough bars exist, ATR(14), 20-candle volume ratio, MACD(12,26,9), Bollinger Bands(20,2) and StochRSI.
- 1D regime, 4H trend, 1H baseline, 15m entry confirmation, five-bar swing pivots and close-through-last-pivot BOS.
- Perps funding per hour normalized to an 8-hour equivalent, aggregated OI, venue OI-side values where published, venue dispersion and a persisted OI change estimate after a prior scan 45–75 minutes earlier.
- Large taker trade observation from OptimistFi's public whale endpoint. The endpoint provides size/side but no wallet/account identity; it is not scored as smart money.
- Independent spot/perps price-basis check. More than 100 bps divergence is rejected as inconsistent; 50 bps or less earns the independent-confirmation points. These thresholds are explicit engineering interpretations, not values supplied by the PDF.
- V3 diagnostic score and deterministic V5 category score. The PDF specifies category maxima but not the sub-point allocation; the sub-rubric in `app/signals.py` is therefore an explicit, test-covered implementation interpretation.
- ATR stop, 2R target, base-quantity and contract-equivalent reference sizing, maximum planned loss USD 4, capital assumption USD 200, maximum leverage 5x and stop-distance bounds 0.5%-3%.
- BUY_NOW/SELL_NOW-only actionable table, separate conditional watchlist, partial-scan footer, SQLite signal history and paper outcome evaluation.
- Same-candle stop/target touches are marked UNKNOWN; no intrabar order is guessed.

## Important data interpretation

The futures mark price, funding and OI come from OptimistFi. The OHLCV candles come from GeckoTerminal DEX spot pools, not the futures contract itself. The system cross-checks the two prices and rejects large basis differences, but it must label its OHLCV as spot-derived and remains Data Grade B. It must not claim that DEX spot candles are futures candles.

The aggregated API does not provide every venue's lot step or minimum quantity. Quantity is therefore expressed as base units and a reference contract equivalent using the selected venue's contract multiplier; it is not an exact exchange order quantity. No order is placed.

The OI 1h change is unavailable on the first scan and until a previous stored snapshot falls within the 45–75 minute comparison window. Missing history earns zero points.

## API

- `POST /signals/scan` — primary scan. Query: `universe_limit=1..100`; `extended=true` scans the eligible top-100 universe.
- `GET /signals/latest` — latest saved scan.
- `GET /signals/performance` — paper outcome metrics only.
- `POST /signals/evaluate` — evaluates open actionable signals against subsequent completed 15m DEX candles.

Routes inherit the control plane's operator API-key requirement. They never connect an exchange account, use exchange credentials, or submit orders.

## Not yet implemented / not verified

- Wallet-identified smart money, on-chain holder flows, and exchange reserves.
- Liquidation clusters, order blocks, FVGs and full liquidity-pool analysis.
- Exchange lot-step/minimum-quantity validation for a chosen execution venue.
- Fee, spread, slippage, funding-cost and venue-specific liquidation modeling.
- A second OHLCV source/fallback when no suitable DEX pool exists.
- Automated scheduled scanning and alert delivery.
- Actual reachability from the user's Iranian network or device. The public API docs do not establish that every network in Iran can reach the endpoints; no bypass is assumed.
- A verified live scan, backtest or performance history. Unit tests use fixtures and must not be presented as live market results.

If a mandatory source, pool, or candle set is missing or stale, the asset is INSUFFICIENT_DATA. It is never filled with fabricated values. A successful CI run proves code/test/build checks only, not live data availability.
