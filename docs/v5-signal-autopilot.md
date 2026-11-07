# V5 Futures Signal Autopilot

## Runtime

- Market discovery: CoinGecko public market list, top 100 by market cap; eligible OKX USDT linear perpetuals are ranked by reported 24-hour volume.
- Futures market data: OKX public read-only API (instruments, last trade, mark/index, OHLCV, funding, open interest and global account ratio).
- Scheduled scan: every 15 minutes at minutes 07, 22, 37 and 52 UTC.
- Manual scan: GitHub Actions -> V5 Futures Signal Autopilot -> Run workflow.
- Dashboard: GitHub Pages project site, served from the generated `site/` artifact.
- No exchange account connection, exchange API credentials, private trading keys, order placement or order execution.

## Publication gates

The static payload builder independently filters candidates before publication.

An immediate signal must be BUY_NOW or SELL_NOW, grade A/B, score >=70, pass self-audit, use a verified contract specification, have a confirmed non-chasing entry, stop distance 0.5%-3%, planned loss <= $4, leverage <=5x and reward/risk >=2. The published table is deduplicated and capped at 10 rows.

Conditional entries are kept separate and require a numeric trigger, explicit confirmation, grade A/B, score >=60 and the same contract/risk constraints. WAIT, REJECT and INSUFFICIENT_DATA never enter either signal table.

If the scan is older than 15 minutes, the dashboard hides the old entries from the current-entry tables and labels the scan stale. A no-signal scan is valid; thresholds must not be weakened just to fill the table.

## Paper tracking and persistence

The scanner writes a local SQLite state file. GitHub Actions cache restores the previous file and saves the updated file after each successful run. This is a free, cache-based continuity mechanism, not a guaranteed database service. GitHub may evict caches under its storage policy; if no state is restored, the dashboard marks paper history as restarted. Cache entries expire after prolonged inactivity, so the scheduled workflow must remain enabled.

Paper outcomes use public OHLCV candles and are not exchange fills or executed-trade performance. The provider name is taken from the latest scan, not hardcoded.

## Public deployment

The dashboard payload is intentionally sanitized. It includes only the latest scan summary, publication-approved signals, conditional watchlist, performance summary, data-source labels and limitations. It does not publish raw candidate diagnostics, local SQLite state or credentials.

The repository must be public for the intended no-subscription GitHub Pages and standard public-runner path. In repository Settings -> Pages, select **GitHub Actions** as the build and deployment source. This repository setting is not writable through the connected GitHub source-control permission, so an owner must enable it once. After that, a push to `main` and the scheduled workflow can publish the site.

The project Pages URL is derived from the repository name and is not considered live until the first successful Pages deployment is recorded in Actions.

## Current release hardening — 2026-11-07

- The scheduled production scanner selects `V5_DATA_PROVIDER=okx`. CoinGecko is used for top-100 discovery and independent spot-price comparison; OKX supplies the USDT linear perpetual instruments, live prices, completed OHLCV, funding, mark/index, open interest and global account ratio.
- The OKX adapter now requires the public instrument `lever` field and carries the venue maximum leverage into the sizing gate. The engine enforces both the user's 5x ceiling and the venue's published maximum.
- Position sizing and reward/risk are calculated from unrounded V5 entry/stop values. Prices and quantity are then rounded to venue tick/lot rules; the rounded stop distance and final planned loss are rechecked, and the quantity is reduced or the candidate rejected if the actual rounded risk, venue leverage, minimum/maximum quantity or RR gate fails.
- The dashboard tables follow the V5 column order. Only BUY_NOW / SELL_NOW are in the immediate table; conditional decisions remain separate. Stale entries older than 15 minutes are hidden.
- Current live access is verified from GitHub-hosted runners. Direct API reachability and futures-account eligibility from Iran are not established by that cloud test; do not treat cloud access as proof of local account eligibility.
- Smart-money / on-chain evidence is not supplied by the active OKX adapter. Missing evidence receives no invented score. Paper outcomes are OHLCV observations, not exchange fills or real-trade performance.
- No exchange account, private exchange credential, order endpoint or order execution is used. The dashboard and scan use public/free endpoints and GitHub Pages / public-repository Actions.


- Market regime is explicitly classified as TRENDING, RANGING, BREAKOUT, HIGH_VOLATILITY, LOW_VOLATILITY or UNSTABLE. An unstable 1H candle blocks immediate-entry publication and requires volatility normalization plus a completed 15m confirmation.
- Four-hour structure uses centered five-candle swing pivots. FVGs use a three-candle gap definition and record zone bounds, formation time, mitigation state and distance. Candidate order blocks use the last opposing candle before a BOS displacement of at least 0.5 ATR, recording origin, displacement, mitigation and distance. Previous-day/week liquidity levels are emitted only when sufficient completed bars exist.
- OKX does not supply verified liquidation clusters or on-chain wallet evidence in this adapter. Those fields are explicitly marked unavailable; no liquidation or institutional-flow claims are fabricated.

- Funding, open-interest and positioning evidence is source-attributed; global/top-trader and taker ratios contribute only when their own observation timestamps are present and within the configured freshness window. Stale or untimestamped ratios receive no score.
