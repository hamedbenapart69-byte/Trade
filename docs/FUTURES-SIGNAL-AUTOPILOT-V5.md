# Futures Signal Autopilot V5

The authoritative requirements are the uploaded `Futures_Signal_Autopilot_V5.pdf` (52 pages). This branch adds a read-only market scanner to the existing Trade control plane. It does not modify the separate Trader_me repository.

## Implemented in this branch

- CoinGecko public API: fetch top 100 assets by market-cap rank, then rank those 100 by reported 24-hour spot volume.
- Excludes configured stablecoins, wrapped representations and duplicate symbols.
- Binance USD-M public endpoints: match active USDT perpetual contracts, verify symbol/contract status, obtain mark-price timestamp and funding, retrieve numerical OHLCV and contract lot/tick/minimum-notional filters.
- Completed 15m, 1h, 4h and 1d candle checks: ordering, duplicate timestamps, gaps, OHLC consistency, finite values, completed-candle status and freshness.
- Deterministic RSI(14), EMA20/50/200, ATR(14), 20-candle volume ratio, MACD(12,26,9), Bollinger Bands(20,2) and StochRSI.
- 1D regime, 4H trend, 1H baseline and 15m entry confirmation.
- Five-bar pivot structure (two bars on either side) and close-through-last-pivot BOS.
- Funding normalization to an 8-hour equivalent; current open interest, 1h OI change when timestamped history exists, and global long/short account ratio where available.
- V3 diagnostic score and a deterministic V5 score mapped to the category maxima in the PDF.
- ATR-based stop, 2R target, quantity rounded down to contract step, minimum quantity/notional checks, maximum planned loss $4, capital assumption $200, maximum leverage 5x and stop-distance bounds 0.5%-3%.
- BUY_NOW/SELL_NOW-only actionable table, separate conditional watchlist, partial-scan footer and explicit DATA_UNAVAILABLE handling.
- SQLite scan/signal persistence and a paper-outcome evaluator using subsequent completed 15m candles. Same-candle stop/target touches are marked UNKNOWN, not guessed.

## Scoring rubric clarification

V5 specifies the maximum points for each category but does not define the sub-point allocation within each category. The code therefore uses an explicit deterministic sub-rubric in `app/signals.py`. It is an implementation interpretation and is test-covered, not a formula quoted from the PDF. Smart-money/on-chain and independent-confirmation categories deliberately remain zero until verifiable providers are integrated.

## API

- `POST /signals/scan` — run the primary scan. Optional query: `universe_limit=1..100`; `extended=true` scans the eligible top-100 universe.
- `GET /signals/latest` — retrieve the latest saved scan.
- `GET /signals/performance` — return verified paper-outcome metrics only.
- `POST /signals/evaluate` — evaluate open actionable signals against subsequent completed 15m candles.

These routes inherit the control plane's operator API-key requirement. They never connect an exchange account and never submit orders.

## Not yet implemented / not verified

- Smart-money/on-chain evidence, whale flows and exchange reserves.
- Liquidation clusters, exchange long/short history beyond the public global ratio, and OI 4h/24h trend.
- Reproducible order-block/FVG/liquidity-pool analytics and full volatility-regime classification.
- Spread/slippage/fees/funding-cost estimation in the planned-loss calculation.
- A secondary independent perpetual-data provider and automatic fallback.
- A persistent scheduled scan service and alert delivery.
- Actual access from the user's Iranian network, VPN, or device.
- A real live scan, performance history, or backtest. Unit tests use fixtures and must not be represented as live market results.

Until the missing provider/strategy components are implemented and live access is tested, this is a functioning first-stage scanner, not a completed V5 release. Missing mandatory market data is recorded as INSUFFICIENT_DATA; it is never filled with a fabricated value.
