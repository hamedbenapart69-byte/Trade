# Stage 1 Design Document V2 — Three-Layer Signal Delivery

**Status:** Approved design baseline; implementation and end-to-end acceptance are still in progress.  
**Branch:** `stage-1-data-layer-v1`  
**Policy:** C1–C18 apply. C14–C18 are additive project constraints accepted on 2026-11-08.

## 1. Product outcome

The deliverable is a free, browser-first crypto futures signal dashboard. The system reads public market data, computes research signals, publishes a read-only dashboard and optionally sends Telegram alerts. The user places any trade manually in their own exchange account.

**Hard boundaries**
- No exchange account connection, trading API keys, private keys, order placement or execution.
- No paid VPS, paid data plan or paid notification provider.
- The dashboard is the primary interface; Telegram/email are notification channels only.
- Missing/blocked data must result in an explicit degraded state, never fabricated values.
- A GitHub-hosted runner test proves access only from that runner's network, not from a user's Iranian ISP/mobile carrier.

## 2. Three-layer architecture

```text
GitHub Actions cron (UTC, every 4 hours) / workflow_dispatch
          |
          v
L1 DATA: modules/data_fetcher.py
  OKX public USDT perpetuals -> OHLCV / funding / OI snapshots
  CoinGecko fallback -> spot price metadata only (not derivatives)
  Alternative.me -> Fear & Greed
  Historical collector -> Parquet + quality report
          |
          v
L2 COMPUTE: logic.py -> modules/signal_engine.py
  validate timestamps/schema/freshness
  EMA(20/50) cross + funding-extreme placeholder
  emit exactly one C10 status per symbol
  missing required inputs -> MARKET_DATA_DEGRADED
          |
          v
STORAGE: modules/storage.py
  data/signals.json + data/history.csv
  web/data/signals.json + web/data/history.csv (public read-only copies)
  Parquet historical dataset retained as a workflow artifact
          |
          +--------------------------+
          |                          |
          v                          v
L3 DELIVERY: Cloudflare Pages    NOTIFICATION: modules/notifier.py
  web/index.html                 Telegram Bot (optional)
  web/app.js                     Tier-A only; secrets stay in Actions
  web/style.css                  no token in browser or repository
          |                          |
          v                          v
  browser dashboard             user's Telegram chat
  read-only/manual trading      manual trade only
```

## 3. Data sources and honest coverage

| Dataset | Primary source | Fallback | Known limitation |
|---|---|---|---|
| USDT perpetual OHLCV | OKX public REST via CCXT | Binance Vision historical files only after independent availability/license checks; CoinGecko is not a futures OHLCV replacement | OKX access can vary by runner/network/region |
| Current spot price | OKX ticker | CoinGecko public API | Spot fallback cannot support a futures setup by itself |
| Funding | OKX public funding history | No equivalent CoinGecko fallback | Current Stage 1 evidence shows about 93.67 days for BTC, not two years |
| Open Interest | OKX public OI + history | None approved yet | Historical window observed about 30 days |
| Fear & Greed | Alternative.me public API | None required for placeholder | Daily series, not hourly |
| Order book / liquidation / basis | Not available in current Stage 1 collector | None | Emit UNAVAILABLE; never synthesize |

### Verified Stage 1 historical run (GitHub Actions)

Run: [42468815714](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42468815714)  
Runner: GitHub-hosted `ubuntu-latest`; workflow completed successfully.

- Active symbols: 100; successful OHLCV symbols: 100; failed: 0.
- 1h OHLCV rows: 1,753,200 expected and 1,753,200 observed.
- Symbols with full requested 2-year window: 100/100.
- Symbols with no gap over 1h: 100/100; reported gap rate: 0%.
- Fear & Greed: 3,199 rows, 2018-02-01 through 2026-11-08 UTC.
- OKX required endpoint probe: 5/5 passed.
- Bybit runner probe: HTTP 403.
- BTC funding history: 282 rows / 93.67 days. Do not describe funding as 2-year coverage.
- BTC OI history: 720 hourly rows / 29.96 days.
- Parquet evidence artifact: 46,111,701 bytes, currently retained by Actions for 30 days.
- This run did **not** execute the specifically requested CCXT `fetch_ticker('BTC/USDT:USDT')` smoke-test; that exact runner test is required in `.github/workflows/signals.yml`.

The current collector writes paths containing `binance_usdm` even when provider=OKX. Treat this as a naming defect to correct; it does not change the provider probe evidence.

## 4. Compute and C10 placeholder

The first compute implementation is deliberately not V8 and is not a profitability claim.

Inputs per symbol:
- completed 1h OHLCV sufficient for EMA20 and EMA50;
- current funding rate;
- fresh timestamps and schema-valid numeric values.

Placeholder rules:
- bullish EMA20/EMA50 cross + sufficiently negative funding -> CONDITIONAL_BUY;
- bearish EMA20/EMA50 cross + sufficiently positive funding -> CONDITIONAL_SELL;
- near-cross / incomplete confirmation -> WATCHLIST;
- valid data without a qualified setup -> NO_QUALIFIED_SETUP;
- stale, missing or invalid required data -> MARKET_DATA_DEGRADED.
- BUY_NOW / SELL_NOW are reserved; placeholder must not manufacture them.

Every symbol emits exactly one of:
`BUY_NOW | SELL_NOW | CONDITIONAL_BUY | CONDITIONAL_SELL | WATCHLIST | NO_QUALIFIED_SETUP | MARKET_DATA_DEGRADED`.

LFS is not calculated by this placeholder. In particular, missing order book means `LFS: NOT_CALCULABLE (missing order book)`; it must not be replaced with 0.5. Order Book, Liquidation and Basis are explicitly `UNAVAILABLE`. OI history is labeled `OKX_PUBLIC_HISTORY_WINDOW_30D`. LFS5 (90-day OI drop) is not fully supportable from 30 days; if later approximated, label it PROXY and apply stricter thresholds. NSS1 (24-hour OI growth) is supportable within the observed 30-day window when timestamps and coverage validate.

## 5. Workflow schedule and runner smoke test

File: `.github/workflows/signals.yml`
- Cron: `0 */4 * * *` (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC).
- `workflow_dispatch` for operator-triggered diagnostics.
- First step must run CCXT OKX `fetch_ticker('BTC/USDT:USDT')` and fail the job if unreachable.
- Then collect current market snapshots, compute placeholder signals, write JSON/CSV, optionally send Telegram, and commit only generated text outputs.
- Use concurrency protection and a timeout. No exchange credentials.
- Two consecutive successful scheduled executions are required for Stage 1 acceptance.

A GitHub-hosted runner success does not establish that OKX or Cloudflare is reachable from Iran. That requires a separate user-network check.

## 6. Output contracts

### data/signals.json

```json
{
  "schema_version": "1.0",
  "generated_at_utc": "ISO-8601 UTC",
  "provider": "okx",
  "pipeline_status": "OK | DEGRADED",
  "engine": "EMA20_EMA50_FUNDING_PLACEHOLDER",
  "is_v8": false,
  "manual_trade_only": true,
  "data_availability": {
    "ohlcv": "OK | UNAVAILABLE",
    "funding": "OK | UNAVAILABLE",
    "open_interest": "OK | UNAVAILABLE",
    "open_interest_history_days": 30,
    "order_book": "UNAVAILABLE",
    "liquidation": "UNAVAILABLE",
    "basis": "UNAVAILABLE",
    "fear_greed": "OK | UNAVAILABLE"
  },
  "signals": [
    {
      "symbol": "BTC/USDT:USDT",
      "status": "NO_QUALIFIED_SETUP",
      "side": null,
      "tier": "NONE",
      "entry": null,
      "stop_loss": null,
      "take_profit": [],
      "reason": "No qualified placeholder setup",
      "lfs": "NOT_CALCULABLE (missing order book)",
      "nss": "NOT_CALCULATED",
      "hypothesis": "EMA/funding placeholder only",
      "falsification": "Fresh completed 1h candle invalidates cross",
      "confidence": "NOT_CALIBRATED",
      "ev_net": "NOT_CALIBRATED"
    }
  ],
  "quality": {
    "symbols_requested": 100,
    "symbols_processed": 0,
    "symbols_degraded": 0,
    "max_candle_age_minutes": null
  }
}
```

The JSON above is a schema example, not a market signal or a live result. Null means unavailable; do not insert made-up values.

### data/history.csv

Append-only signal snapshots with UTC timestamp, symbol, status, side, tier, provider, engine version, reason, confidence, EV calibration state and a deterministic idempotency key. Deduplicate by `generated_at_utc + symbol + engine_version`.

## 7. Web dashboard

Static, framework-free files:
- `web/index.html`: Persian RTL dashboard shell and accessible status regions.
- `web/app.js`: fetches only `./data/signals.json` and `./data/history.csv`; handles loading, stale data, HTTP failure and degraded state.
- `web/style.css`: responsive mobile-first layout.
- Shows generation time, pipeline/provider status, data availability, counts by C10 status, signal cards, recent history and explicit unavailable-data warnings.
- No trading buttons, exchange login, secret, or order endpoint.

## 8. Telegram notifications

- Bot created by user through Telegram `@BotFather`.
- GitHub Actions secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Send only newly created Tier-A signals; idempotency key prevents repeated alerts on reruns.
- Message contains symbol, direction/status, timeframe, entry/SL/TP only when valid, timestamp, reason, confidence calibration and dashboard URL.
- No token in `config.json`, committed files, logs, web JavaScript or browser requests.
- If secrets are absent, notification is `SKIPPED_NOT_CONFIGURED`, not a pipeline failure.
- Email is not enabled in V2: a free tier can change, require billing details or geo-restrictions; no assumption of permanently free delivery.

## 9. Cloudflare Pages deployment — one-time setup

1. Create/sign in to a Cloudflare account; confirm the Free plan and dashboard access from the intended network.
2. Open Workers & Pages.
3. Select Create application, then Pages.
4. Choose Connect to Git.
5. Authorize GitHub and select `hamedbenapart69-byte/Trade`.
6. Select branch `stage-1-data-layer-v1` for preview; production branch can be chosen after review.
7. Set framework preset to None.
8. Set build command to empty / none.
9. Set output directory to `web`.
10. Save and deploy; verify the generated `*.pages.dev` URL from the user's device/network.

Cloudflare account authorization and the initial Pages project creation require the user's own account action. The repository code can be prepared here, but a Pages URL must not be claimed until the deployment URL is verified. Git integration will redeploy on commits to the selected branch.

## 10. Cost and operational boundaries

- GitHub Actions free allowance and artifact retention are subject to GitHub account/repository quotas and policy; 30-day artifact retention is not permanent storage.
- Cloudflare Pages Free availability, quotas, account verification and reachability from Iran must be tested at deployment time.
- Telegram is free at the Bot API level, but reachability from Iran is network-dependent.
- No VPS, paid API, paid storage, paid email or exchange account credential is required by the design.
- The 46 MB Parquet artifact is temporary evidence today. A durable zero-cost long-term store is not yet proven; Stage 1 acceptance must explicitly decide whether the user accepts a public repository dataset, bounded Actions artifact retention, or another verified free store.

## 11. Stage 1 acceptance gates (revised)

**L1 Data**
- 100 symbols; 2-year 1h OHLCV for at least 95%; no gap >1h; UTC; schema-valid; Parquet evidence.
- Funding history for at least 95% of symbols, with actual history window reported (current BTC evidence: 93.67 days, not 2 years).
- OI history labeled 30 days; Fear & Greed loaded.
- Report per-symbol failures, coverage and gaps.

**L2 Compute**
- `logic.py` generates `signals.json` and idempotent `history.csv`.
- Every symbol has exactly one C10 state.
- Cron every 4 hours plus workflow_dispatch.
- Exact OKX CCXT smoke test passes on GitHub Actions runner.
- At least two consecutive successful scheduled executions.
- Missing data becomes MARKET_DATA_DEGRADED.

**L3 Delivery**
- Static dashboard reads the published JSON/CSV and shows latest signals, history and system/data status.
- Cloudflare Pages URL is actually deployed and reachable from the user's network; alternatively, before deployment only, the repository includes the complete 10-step guide.
- At least one actual generated record is displayed; demo data must be clearly labeled and cannot masquerade as a live signal.

**Notification**
- Telegram notifier code and BotFather/secret instructions exist.
- At least one actual test notification is delivered after user supplies secrets; otherwise report NOT_CONFIGURED and do not claim PASS.

**End-to-end**
- One complete run: runner test -> data -> compute -> JSON/CSV -> commit -> Pages deploy -> dashboard view -> Telegram delivery (if configured).
- Two successful scheduled runs are required for compute automation.
- Stage 1 remains NOT PASS until all required gates are evidenced. Any external account setup blocked by missing user credentials is marked BLOCKED, not fabricated.

## 12. Stage 2–15: preserve all three layers

| Stage | Core engineering focus | Data layer | Compute layer | Delivery layer |
|---|---|---|---|---|
| 2 | LFS resilience | order-flow inputs or explicit PROXY/UNAVAILABLE | LFS v1/v2/v3; no fake 0.5 | expose LFS availability and proxy labels |
| 3 | NSS resilience | OI/funding/basis coverage | NSS variants and validation | show NSS and evidence per signal |
| 4 | Liquidity zones / phase | candles, volume profile, available depth | phase + zone agreement | visualize zones and confidence |
| 5 | LRT + NMT | validated MTF market data | path-specific entries/exits | show path, invalidation and time-stop |
| 6 | Calibration / EV | outcomes and costs | OOS calibration, Brier, EV_net | show NOT_CALIBRATED until valid |
| 7 | Consensus / risk | validated regime and risk inputs | risk/execution gate | explain conditions_to_flip |
| 8 | Plan A backtest | point-in-time data | walk-forward Gate_A | publish metrics and limitations |
| 9 | Plan B factors | cross-sectional inputs | Gate_B | compare path results |
| 10 | Plan C ensemble | Donchian/EMA/funding | Gate_C | compare path results |
| 11 | Plan H generators | data required per generator | seven generators, Tier A/B/C | daily C10 board |
| 12 | Paper + Shadow | live public snapshots and outcomes | shadow divergence | paper results and alerts |
| 13 | Meta-Allocator | path-level results | only after 180d/100 trades/path | allocation status, no premature activation |
| 14 | Innovation Protocol | expand sources only if justified | six fallback routes, honest stop | show fallback status |
| 15 | Final decision | complete audited dataset | final gates and recommendation | final report + stable dashboard |

Every stage must preserve the read-only, zero-cost, browser-first, manual-trade-only contract. Stage contracts still follow SLRP v1/v2/v3, D1–D6 diagnosis, R1–R11 and the original V8 gates.


## 13. Verified compute-run evidence (2026-11-08)

A GitHub-hosted runner completed run [42478801565](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42478801565) successfully:
- The requested CCXT `fetch_ticker("BTC/USDT:USDT")` step passed on the GitHub Actions runner.
- Unit tests passed.
- `logic.py` completed with provider `okx`, pipeline status `OK`, and 100 symbols processed.
- 100 signal records were appended to history: 15 `WATCHLIST`, 85 `NO_QUALIFIED_SETUP`, zero BUY/SELL or conditional signals.
- The four public outputs were committed and pushed in the successful run.
- Telegram was skipped because bot secrets were not configured.

A subsequent hard-gate revision removes `continue-on-error` from the OKX smoke-test step. The exact smoke test was also observed successful on run [42478911424](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42478911424); its final pipeline/push result is tracked separately from the earlier completed run.

The historical Stage 1 report contains Funding history for 100/100 symbols, each with 93.67 days of coverage, and OI history for 100/100 symbols, each with 29.96 days. Funding is therefore historically present for all selected symbols, but not two years.

## 14. Scheduling limitation on the current feature branch

The repository default branch is `main`; this work is on `stage-1-data-layer-v1`. GitHub scheduled workflows run from the repository's default branch. Therefore the four-hour cron is defined in this branch but does not become an autonomous scheduled job until this workflow is merged into `main` or the repository default branch is changed. Neither action is performed automatically here. Until then, `workflow_dispatch` and branch push runs are available, but they are not a substitute for two successful scheduled executions.

## 15. Remaining external acceptance blockers

- Cloudflare Pages project creation and the actual `*.pages.dev` URL require the owner's Cloudflare account authorization. The 10-step guide is committed at [CLOUDFLARE_PAGES_DEPLOY.md](CLOUDFLARE_PAGES_DEPLOY.md); no live deployment is claimed yet.
- Telegram delivery requires the owner to add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository Actions secrets. No token is present in this environment; no test notification is claimed.
- The current placeholder intentionally emits no Tier-A classification and never emits BUY_NOW/SELL_NOW. Telegram Tier-A notifications will remain silent until a later validated engine assigns Tier A.
- Two successful scheduled runs cannot be claimed until the workflow is active on the default branch.


### Latest hard-gate workflow result

Run [42479108791](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42479108791) completed with overall `success`:
- The OKX `fetch_ticker("BTC/USDT:USDT")` smoke test passed as a blocking step (no `continue-on-error`).
- Unit tests passed.
- Compute processed 100 OKX perpetual symbols and returned `pipeline_status=OK`.
- `signals.json` contains 100 records: 15 WATCHLIST and 85 NO_QUALIFIED_SETUP; no BUY/SELL status was manufactured.
- `history.csv` now contains 200 rows (100 from each of two successful branch pipeline runs).
- Commit/push of `data/signals.json`, `data/history.csv`, and the public `web/data/` copies succeeded after replacing the conflict-prone rebase with fetch/reset/stage of generated outputs.
- Telegram remains `SKIPPED_NOT_CONFIGURED`; no token or chat ID was available.


## 16. Zero-cost email correction

The original suggestion of a permanent SendGrid Free tier with 100 emails/day is outdated. Twilio's current official pricing describes 100 emails/day as a **60-day free trial**, after which a paid plan is required to continue sending. The official changelog also records retirement of the former free plan in 2025. Therefore SendGrid is not accepted as a permanent zero-cost fallback under C15. Telegram remains optional and secret-configured; no email provider is enabled unless a genuinely ongoing free option is verified.

Sources:
- [Twilio SendGrid Email API pricing](https://www.twilio.com/en-us/products/email-api/pricing)
- [Twilio changelog: changes to SendGrid Free Plan](https://www.twilio.com/en-us/changelog/sendgrid-free-plan)

Signal history idempotency is now keyed by symbol + engine + four-hour UTC bucket, so reruns in the same bucket do not append duplicate snapshots.
