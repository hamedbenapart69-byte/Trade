# Futures Signal Autopilot V5

This document records the implementation boundary against the uploaded 52-page `Futures_Signal_Autopilot_V5.pdf`. The scanner lives in this repository's `feature/futures-signal-autopilot-v5` branch. It does not access or modify the separate `Trader_me` repository.

## Data sources and access

- **CoinGecko public API**: top 100 by market-cap rank, re-ranked by 24-hour volume. No API key is used for discovery.
- **TraderSpy read-only REST API**: actual futures OHLCV, current futures prices, funding, open interest, global/top-trader positioning, and smart-money leaderboard/position evidence. The connected TraderSpy ChatGPT connector was tested in this session and returned current BTCUSDT futures price, 15m/1h/4h/1d candles and derivatives. The underlying public market feed identifies itself as Binance USDⓈ-M futures, accessed through TraderSpy. No direct Binance endpoint, exchange account, exchange API key or order endpoint is used.
- **TraderSpy API key requirement for the repository runner**: the free data-provider plan requires a read-only TraderSpy API key stored as GitHub Actions secret `TRADERSPY_API_KEY`. This is a data-provider key, not an exchange key; it cannot place trades. The key is never stored in source. The connected ChatGPT MCP tools work without this separate REST key, but the GitHub-hosted backend cannot inherit that ChatGPT connector session.
- **Free-plan limits**: TraderSpy documents 300 API calls/day and 10 calls/minute on the free plan. A standard 30-asset run uses about 132 REST calls and takes roughly 13–15 minutes at the enforced pacing. Extended mode is capped at 40 raw-OHLCV assets per run to stay below the per-run budget. These are permanent free-plan limits, not unlimited access.
- **Iran feasibility**: the TraderSpy connector returned live data in this ChatGPT session. Direct REST access from the user's own network and from GitHub-hosted runners has not yet been verified; no VPN or geoblock bypass is assumed. The underlying feed is public Binance USDⓈ-M market data served by TraderSpy, not a Binance account connection.

## Implemented in this branch

- CoinGecko top-100 discovery, duplicate-symbol, stablecoin, wrapped-token and leveraged-token exclusions; ranking by 24-hour volume.
- Matching to TraderSpy's tracked USDT perpetual symbol universe.
- Raw numerical futures OHLCV for 15m, 1h, 4h and 1d; completed-candle filtering; timestamp ordering, duplicate, gap, OHLC, finite-value, volume and freshness checks.
- Deterministic RSI(14), EMA20/50/200, ATR(14), volume ratio, MACD(12,26,9), Bollinger Bands(20,2), StochRSI, ADX, OBV and MFI.
- A 25-check pre-trade self-audit; actionable decisions require every check to pass.
- 1D/4H/1H trend checks; five-candle swing pivots, HH/HL and LH/LL structure, BOS/CHoCH, simple FVG/last-opposite-candle order-block and liquidity-sweep observations, clustered swing levels, ATR-percentile volatility regime.
- V3 mandatory long/short baseline and diagnostic score.
- V5 score categories with maxima preserved: Core Technical 25, Multi-Timeframe 15, Market Structure 15, Volume/Momentum 10, Derivatives 10, Smart Money 5, Entry/Risk 15, Independent Confirmation 5. The PDF defines category maxima but not every sub-point; the sub-rubric in code is an explicit, test-covered interpretation.
- Funding threshold is evaluated per published funding interval, not by assuming an 8-hour interval.
- Derivatives include current OI, 4h/24h OI changes, persisted 1h OI change when a prior snapshot exists, funding, global/top-trader long-short ratios, taker ratio and provider liquidation-regime label.
- Smart-money score uses top-trader positioning and matching open positions where present. No wallet identity or on-chain holdings are claimed. TraderSpy AI signals are supporting evidence only when a numeric confidence above 60 and a timestamp within 15 minutes are both present; stale signals are ignored.
- Independent confirmation compares TraderSpy futures index price with CoinGecko's spot reference. Spot is never used as futures entry, stop or target.
- Anti-chasing check, market/pullback/breakout-retest/liquidity-sweep entry classification, structural-or-ATR stop, TP1/TP2/TP3 where nearby structure supports them.
- Risk sizing uses USD 200 capital assumption, USD 4 maximum planned loss and 5x leverage ceiling. It outputs underlying/base-unit quantity; venue lot step, minimum quantity and contract multiplier are not exposed by the selected feed, so no exact exchange contract count is claimed.
- BUY_NOW/SELL_NOW actionable output, separate conditional watchlist, top-10 ranking, partial-scan indicator, SQLite persistence and paper outcome tracking on actual futures candles. Same-candle stop/target touches are UNKNOWN.
- No account connection, exchange credentials, order execution or automated trading.

## Important thresholds and implementation interpretations

The following are implementation choices where the PDF defines the category or intent but not a numeric threshold: 100 bps for hard cross-source price conflict, 50 bps for full independent-confirmation points, ADX 20 for trend strength, 2 ATR for anti-chasing, 1.2/0.8 for top-trader positioning alignment, and 24-hour paper-signal expiry. They are visible in code and tests, not represented as PDF-specified facts.

## Not yet implemented or not fully verified

- A verified contract lot step, minimum quantity, tick size and contract multiplier per venue. The output therefore reports base-unit sizing only.
- Exact spread/order-book depth, maker/taker fees, slippage and venue-specific liquidation price.
- Full liquidation heatmaps/clusters and on-chain wallet/holder flows.
- Full institutional order-block/FVG and liquidity-pool mapping beyond the documented candle-based approximations.
- TraderSpy free REST API key configured in GitHub Actions; without it, the backend correctly returns `DATA UNAVAILABLE` / `INSUFFICIENT_DATA`. See `docs/SETUP_TRADERSPY_API_KEY.md`.
- A successful end-to-end 30-asset GitHub live scan using that secret. The connected ChatGPT TraderSpy data connector has been live-tested for BTC only; that is not a 30-asset production validation.
- Direct REST reachability from Iran and GitHub runner reachability.
- A verified historical backtest/performance sample. CI fixtures are tests only and must never be presented as live results.

If mandatory live data is missing, stale, contradictory or unavailable, the asset is `INSUFFICIENT_DATA`; no fabricated values or demo signals are emitted. A successful CI run proves code/test/build checks only, not live market-data access or trading performance.
