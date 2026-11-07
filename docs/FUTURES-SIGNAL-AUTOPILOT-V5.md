# Futures Signal Autopilot V5

This document records the implementation boundary against the uploaded 52-page `Futures_Signal_Autopilot_V5.pdf`. The scanner lives in this repository's `feature/futures-signal-autopilot-v5` branch. It does not access or modify the separate `Trader_me` repository.

## Data sources and access

- **CoinGecko public API**: top 100 by market-cap rank, re-ranked by 24-hour volume. No API key is used for discovery.
- **TraderSpy read-only REST API**: actual futures OHLCV, current futures prices, funding, open interest, global/top-trader positioning, and smart-money leaderboard/position evidence. **Official Binance USDⓈ-M public `exchangeInfo` endpoint** is used only to verify that the matching contract is a trading PERPETUAL and to obtain tick size, lot step, minimum quantity and minimum notional; it is public market metadata, requires no account/API key, and is not used for prices, candles, or order execution. The live tracked-symbol check returned 760 USDT symbols and zero USDC symbols; the current scanner therefore covers USDT contracts only, not USDC contracts. The connected TraderSpy ChatGPT connector was tested in this session and returned current BTCUSDT futures price, 15m/1h/4h/1d candles and derivatives. The underlying public market feed identifies itself as Binance USDⓈ-M futures, accessed through TraderSpy. No Binance account connection, exchange API key, private endpoint or order endpoint is used; public exchangeInfo is read-only contract metadata.
- **TraderSpy API key requirement for the repository runner**: the free data-provider plan requires a read-only TraderSpy API key stored as GitHub Actions secret `TRADERSPY_API_KEY`. This is a data-provider key, not an exchange key; it cannot place trades. The key is never stored in source. The connected ChatGPT MCP tools work without this separate REST key, but the GitHub-hosted backend cannot inherit that ChatGPT connector session.
- **Free-plan limits**: TraderSpy documents 300 API calls/day and 10 calls/minute on the free plan. A standard 30-asset run uses about 132 REST calls and takes roughly 13–15 minutes at the enforced pacing. Extended mode is capped at 40 raw-OHLCV assets per run. The application persistently caps its own daily usage at 240 calls, reserving 60 calls for other account use. These are permanent free-plan limits, not unlimited access.
- **Iran feasibility**: the TraderSpy connector returned live data in this ChatGPT session. Direct REST access from the user's own network and from GitHub-hosted runners has not yet been verified; no VPN or geoblock bypass is assumed. The underlying feed is public Binance USDⓈ-M market data served by TraderSpy, not a Binance account connection.

## Implemented in this branch

- CoinGecko top-100 discovery, duplicate-symbol, stablecoin, wrapped-token and leveraged-token exclusions; ranking by 24-hour volume.
- Matching to TraderSpy's tracked USDT perpetual symbol universe.
- Raw numerical futures OHLCV for 15m, 1h, 4h and 1d; completed-candle filtering; timestamp ordering, duplicate, gap, OHLC, finite-value, volume and freshness checks.
- Deterministic RSI(14), EMA20/50/200, ATR(14), volume ratio, MACD(12,26,9), Bollinger Bands(20,2), StochRSI, ADX, OBV and MFI.
- A 25-check pre-trade self-audit; actionable decisions require every check to pass.
- A read-only provider readiness endpoint at `GET /signals/status`; a configured secret is not treated as proof of network reachability.
- The live workflow runs on merge to `main`, daily at 08:00 UTC, or manually; it restores and saves `data/control.db` using GitHub Actions cache, preserving signal outcomes, OI snapshots and the local API-call budget across regular runs. GitHub documents 10 GB of cache per repository at no additional cost by default; unused cache entries are evicted after seven days, so regular daily runs keep the state warm.
- 1D/4H/1H trend checks; five-candle swing pivots, HH/HL and LH/LL structure, BOS/CHoCH, simple FVG/last-opposite-candle order-block and liquidity-sweep observations, clustered swing levels, ATR-percentile volatility regime.
- V3 mandatory long/short baseline and diagnostic score.
- V5 score categories with maxima preserved: Core Technical 25, Multi-Timeframe 15, Market Structure 15, Volume/Momentum 10, Derivatives 10, Smart Money 5, Entry/Risk 15, Independent Confirmation 5. The PDF defines category maxima but not every sub-point; the sub-rubric in code is an explicit, test-covered interpretation.
- Funding threshold is evaluated per published funding interval, not by assuming an 8-hour interval.
- Derivatives include current OI, 4h/24h OI changes, persisted 1h OI change when a prior snapshot exists, funding, global/top-trader long-short ratios, taker ratio and provider liquidation-regime label.
- Smart-money score uses top-trader positioning and matching open positions where present. No wallet identity or on-chain holdings are claimed. TraderSpy AI signals are supporting evidence only when a numeric confidence above 60 and a timestamp within 15 minutes are both present; stale signals are ignored.
- Independent confirmation compares TraderSpy futures index price with CoinGecko's spot reference. Spot is never used as futures entry, stop or target.
- Anti-chasing check, market/pullback/breakout-retest/liquidity-sweep entry classification, structural-or-ATR stop, TP1/TP2/TP3 where nearby structure supports them.
- Risk sizing uses USD 200 capital assumption, USD 4 maximum planned loss and 5x leverage ceiling. It verifies public USDⓈ-M PERPETUAL/TRADING status, asset identity, tick size, lot step, minimum quantity and minimum notional; rounds entry/stop/TP1 to tick increments and floors base-asset quantity to the permitted lot step before rechecking planned loss, leverage and reward-to-risk.
- BUY_NOW/SELL_NOW actionable output, separate conditional watchlist, top-10 ranking, partial-scan indicator, SQLite persistence and paper outcome tracking on actual futures candles. Same-candle stop/target touches are UNKNOWN.
- No account connection, exchange credentials, order execution or automated trading.

## Important thresholds and implementation interpretations

The following are implementation choices where the PDF defines the category or intent but not a numeric threshold: 100 bps for hard cross-source price conflict, 50 bps for full independent-confirmation points, ADX 20 for trend strength, 2 ATR for anti-chasing, 1.2/0.8 for top-trader positioning alignment, and 24-hour paper-signal expiry. They are visible in code and tests, not represented as PDF-specified facts.

## Not yet implemented or not fully verified

- A verified contract multiplier for any non-linear or non-unit contract type. The current USDⓈ-M linear USDT perpetual path verifies base/quote/margin assets, PERPETUAL/TRADING status, tick size, lot step, minimum quantity and minimum notional from public exchange metadata; quantities are reported in base-asset units.
- Exact spread/order-book depth, maker/taker fees, slippage and venue-specific liquidation price.
- Full liquidation heatmaps/clusters and on-chain wallet/holder flows.
- Full institutional order-block/FVG and liquidity-pool mapping beyond the documented candle-based approximations.
- The owner reports adding the TraderSpy free REST API key to GitHub Actions; the value is intentionally not readable to the assistant. Successful use of the secret remains unverified until the live workflow runs. See `docs/SETUP_TRADERSPY_API_KEY.md`.
- A successful end-to-end 30-asset GitHub live scan using that secret. The connected ChatGPT TraderSpy data connector has been live-tested for BTC only; that is not a 30-asset production validation. The workflow runs once on a push to `main` after merge, then daily at 08:00 UTC, and also supports manual `workflow_dispatch`.
- Direct REST reachability from Iran and GitHub runner reachability.
- A verified historical backtest/performance sample. CI fixtures are tests only and must never be presented as live results.

If mandatory live data is missing, stale, contradictory or unavailable, the asset is `INSUFFICIENT_DATA`; no fabricated values or demo signals are emitted. A successful CI run proves code/test/build checks only, not live market-data access or trading performance.

---

## Current live validation update — 2026-11-06

This section supersedes earlier statements in this document that describe Binance/TraderSpy as the only live runner path.

### Verified public data path

- The current experimental default is **OKX public linear USDT perpetual market data**. No exchange account, exchange API key, or paid data subscription is used.
- From GitHub-hosted Actions, OKX returned HTTP 200 with valid JSON for instruments, tickers, candles, funding, open interest, mark price, index price, and global long/short account ratio.
- Binance USDⓈ-M exchange metadata returned HTTP 451 from the same runner. Bybit public linear endpoints returned HTTP 403. These were tested alternatives, not assumptions.
- CoinGecko public market discovery returned HTTP 200.
- The OKX adapter keeps instrument identity, candles, price, mark/index, funding, and open interest on the same venue. It does not combine OKX contract rules with Binance candles.
- OKX BTC-USDT-SWAP metadata was verified as a live linear perpetual: contract value 0.01 BTC, tick size 0.1 USDT, lot step 0.01 contracts, minimum size 0.01 contracts.
- Contract-aware sizing now converts contract count to base-asset exposure using the published multiplier, rounds to the venue lot step, and rechecks planned loss, leverage, and reward-to-risk.

### Actual test evidence

- One-symbol live BTC smoke test: **passed**. It retrieved 220 candles per timeframe (15m, 1h, 4h, 1d), live price, funding, open interest, mark/index, account ratio, and verified contract-aware risk sizing.
- Full live market scan: **30 of 30 selected assets screened** from the CoinGecko top-100 discovery universe. Zero candidates had missing mandatory data. All 30 were rejected by the mandatory V3 baseline; no BUY_NOW or SELL_NOW signal was published. The output was: No qualifying signals today. This is a valid no-signal result, not a failed scan and not evidence of profitability.
- The live scan was read-only and used public endpoints only. No order was placed.
- The full-scan artifact is retained in GitHub Actions run 42309970270 (artifact: v5-okx-live-scan).
- The OKX path does not currently supply TraderSpy smart-money records, top-trader positioning, taker ratio, liquidation clusters, or on-chain flows. Missing supplementary evidence receives no score; it is not fabricated.
- The connected ChatGPT TraderSpy connector remains a separate data access path and is not inherited by GitHub Actions.
- Direct access from the user's own network in Iran remains unverified. GitHub-hosted runner access is verified for the tested OKX endpoints only.

### Current implementation boundary

- This work is on diagnostics/public-market-endpoint-probe, based on the existing V5 test branch. It has not been merged to main and has not been deployed.
- The earlier Binance/TraderSpy adapter remains in the code as an explicitly selected legacy provider (V5_DATA_PROVIDER=traderspy); it is not the current default because its Binance contract-metadata dependency fails with HTTP 451 in GitHub Actions.
- A green CI result validates automated tests/build checks. The one-symbol smoke and 30-asset scan are separate live-data evidence. Neither establishes profitable trading performance.
- Historical out-of-sample strategy performance, exact execution fees/slippage, full liquidation mapping, and on-chain intelligence remain unverified or incomplete.