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
