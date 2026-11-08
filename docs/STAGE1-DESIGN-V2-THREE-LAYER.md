# Stage 1 Design Doc V2 — Three-Layer Signal Delivery

Status: **REVISED / NOT ACCEPTED AS COMPLETE**
Branch: `stage1-webfirst-v2-clean`
Last evidence reviewed: GitHub Actions run `42468815714` (2026-11-08)

## 1. Product outcome and non-negotiable constraints

The deliverable is a free, browser-first daily crypto-futures signal dashboard with automatic refresh and optional free notifications. The user manually decides whether to place a trade in their own exchange account.

- Zero-cost architecture: GitHub Actions free allowance, public market-data endpoints, static Cloudflare Pages, Telegram Bot API. No VPS, paid APIs, paid tiers, or required credit card.
- Web-first: the dashboard is the primary interface; Telegram is a notification channel only.
- Autonomous: scheduled GitHub Actions every four hours plus `workflow_dispatch`.
- Manual trading only: no exchange account connection, trading API keys, private keys, order placement, or custody.
- Iran access is not assumed. GitHub runner reachability and a user's Iranian ISP reachability are separate tests. Cloudflare Pages, GitHub raw, and Telegram must each be checked from the user's actual network before claiming availability.
- Every phase must preserve Data, Compute, and Delivery (C14). A phase may improve one layer, but must keep the other two functioning and report end-to-end status.

## 2. Three-layer architecture

```text
GitHub Actions (UTC cron every 4h / manual dispatch)
  |
  +--> L1 DATA
  |      OKX public swaps via CCXT (primary)
  |      CoinGecko public API (spot-price metadata fallback only)
  |      Binance Data Vision (optional historical OHLCV/funding source,
  |                           only after runner probe + terms/data validation)
  |      Alternative.me Fear & Greed
  |      Parquet cache + data-quality report
  |
  +--> L2 COMPUTE
  |      signal_autopilot/logic.py
  |        -> signal_autopilot/modules/signal_engine.py (Stage 1 placeholder)
  |        -> strict 7-state C10 output
  |        -> signal_autopilot/data/signals.json + history.csv
  |
  +--> L3 DELIVERY
  |      commit/push generated public, non-secret artifacts
  |        -> Cloudflare Pages Git integration auto-build
  |        -> web/futures dashboard reads same-origin /data/signals.json
  |      signal_autopilot/modules/notifier.py -> Telegram Bot API (Tier-A only)
  |
  +--> evidence artifacts + run summary + health/status fields
```

The dashboard is static and read-only. It never asks for an exchange login or trading key.

## 3. Data sources and known limitations

| Dataset | Primary | Fallback | Current verified state / rule |
|---|---|---|---|
| Perpetual OHLCV 1h | OKX public swap API via CCXT | Binance Data Vision archive, historical-research-only pending terms review | Full-run evidence: 100/100 symbols, 1,753,200 rows, 2-year target, reported 0 missing intervals |
| Funding history | OKX public funding history | Binance Data Vision funding archive, conditional | BTC sample in full run covered 93.67 days only (12.822% of 2-year window); current criterion FAIL |
| Open Interest | OKX public OI history | None accepted yet | Approximately 30 days; label `HISTORICAL_OI_30D`; never imply 2-year OI |
| Fear & Greed | Alternative.me | None needed for Stage 1 | Daily series; no hourly interpolation |
| Spot price / metadata | Exchange market ticker | CoinGecko public API | CoinGecko is not a substitute for perpetual funding, OI, order book, liquidation, or basis |
| Order Book history | UNAVAILABLE | No accepted fallback | `UNAVAILABLE`; no synthetic values |
| Liquidation history | UNAVAILABLE | No accepted fallback | `UNAVAILABLE`; no synthetic values |
| Continuous historical Basis | UNAVAILABLE | No accepted fallback | `UNAVAILABLE`; no synthetic values |

### Data interpretation rules

- OHLCV timestamps are UTC, one-hour bars. A gap greater than one hour is a data-quality failure.
- OI is capped at the latest 30 days in this Stage 1 implementation.
- LFS component based on OI decline over a 90-day high cannot be calculated from 30-day OI. Mark it `PROXY` only if a separately documented proxy is validated; otherwise mark `NOT_CALCULABLE`.
- LFS must not receive a default score such as 0.5 when required inputs are missing. Example: `LFS: NOT_CALCULABLE (missing historical order-book data)`.
- NSS 24-hour OI growth can be computed from the available 30-day OI series if its timestamps and coverage pass validation.
- Funding coverage is independently measured. Current OKX result is not enough for the 95% historical criterion. A GitHub Actions probe verified three Data Vision sample archives with matching SHA-256 checksums (OHLCV, funding, daily metrics); however, the current Binance Vision terms limit permitted use to non-commercial categories including personal historical backtesting and expressly prohibit certain live/commercial signal uses. Do not feed those archives into live signals or redistribute them unless the applicable license is confirmed to allow it.
- Never use a spot-market fallback as if it were perpetual futures data.

## 4. L2 placeholder signal engine

Stage 1 uses a deliberately limited placeholder, not the V8 strategy and not a profitability claim:

- Inputs: validated OHLCV 1h/4h, available funding, market status, and freshness.
- Candidate logic: EMA 20/50 cross + funding-extreme filter.
- Missing required inputs or stale data => `MARKET_DATA_DEGRADED`.
- No valid setup => `NO_QUALIFIED_SETUP`.
- A setup awaiting confirmation => `CONDITIONAL_BUY` or `CONDITIONAL_SELL`.
- `BUY_NOW` / `SELL_NOW` only when every placeholder rule and risk gate passes. The placeholder must remain conservative and clearly labelled `ENGINE_VERSION: STAGE1_PLACEHOLDER`.
- The seven and only seven allowed C10 statuses:
  `BUY_NOW`, `SELL_NOW`, `CONDITIONAL_BUY`, `CONDITIONAL_SELL`, `WATCHLIST`, `NO_QUALIFIED_SETUP`, `MARKET_DATA_DEGRADED`.
- No order execution. Signals contain thesis, invalidation, timestamp, data quality, and source provenance; not an exchange action.

## 5. Output contracts

### `signal_autopilot/data/signals.json`

Top-level fields:
- `schema_version`, `generated_at_utc`, `run_id`, `engine_version`
- `system_status`: `OK` or `MARKET_DATA_DEGRADED`
- `data_quality`: symbols requested/succeeded, OHLCV gap rate, historical coverage, funding coverage, OI window, provider health
- `unavailable_data`: explicit `order_book`, `liquidations`, `basis` states
- `signals[]`: symbol, market, timeframe, C10 status, side, tier, score (only if calculable), entry zone (only if calculable), invalidation, targets (only if justified), hypothesis, confidence label, data flags, source timestamps
- `summary`: counts for all seven statuses

### `signal_autopilot/data/history.csv`

Append-only signal snapshots with:
`generated_at_utc,run_id,symbol,market,timeframe,status,side,tier,engine_version,score,entry,invalidation,source_status,data_quality_flags`.

Do not append duplicate `run_id + symbol + timeframe` records. All timestamps ISO-8601 UTC.

### Parquet

Use provider-specific folders under `signal_autopilot/data/stage1/` (for example `okx_swap/ohlcv_1h/`, `okx_swap/funding/`, `okx_swap/open_interest_1h/`, and `sentiment/`). Writes are atomic. No credentials or notification tokens are stored in artifacts.

## 6. L3 web dashboard

Static files:
- `web/futures/index.html`
- `web/futures/app.js`
- `web/futures/style.css`

Dashboard requirements:
1. Last successful run and UTC timestamp.
2. System health: OK / degraded, provider and freshness.
3. Today's signal cards/table, filterable by status and symbol.
4. Explicit labels for placeholder engine and unavailable datasets.
5. History view backed by `signal_autopilot/data/history.csv`.
6. Mobile-first responsive RTL-capable layout.
7. Same-origin fetch from `/data/signals.json` and `/data/history.csv` to avoid CORS dependency on GitHub raw.
8. If JSON is missing or stale, show a visible error/degraded state, never a fake sample trade.

## 7. Schedule and automation

Workflow path: `.github/workflows/futures-signals.yml`; engine entry point: `signal_autopilot/logic.py`.

- Schedule: `7 */4 * * *` (00:07, 04:07, 08:07, 12:07, 16:07, 20:07 UTC).
- Manual run: `workflow_dispatch`.
- First network step must run the exact CCXT OKX probe:
  `ccxt.okx().fetch_ticker('BTC/USDT:USDT')`.
- Then fetch/validate data, generate signals, append history idempotently, send notifications if configured, and commit only generated artifacts.
- The workflow must not run on its own generated commit, preventing recursive runs.
- GitHub Actions scheduled runs can be delayed or disabled by GitHub inactivity/quota policies; monitor actual run timestamps and free-tier usage.

## 8. Telegram notification

- `modules/notifier.py` sends only newly created Tier-A signals; it records a stable notification key to avoid duplicate alerts.
- Message includes symbol, status/side, timeframe, generated UTC time, engine version, data quality, hypothesis, invalidation, and dashboard URL.
- Bot token and chat ID are GitHub Actions secrets only; never commit them or put them in `config.json`.
- A real test requires the user to create a bot with @BotFather and add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as repository Actions secrets. Until supplied, notification state is `NOT_CONFIGURED`, not PASS.
- Setup: (1) open Telegram and message `@BotFather`; (2) run `/newbot` and save the returned token privately; (3) open the new bot and press Start; (4) obtain the private chat ID using Telegram's official Bot API `getUpdates` after sending the bot a message; (5) in GitHub repository Settings -> Secrets and variables -> Actions, add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; (6) open Actions -> Futures Signals Pipeline -> Run workflow, select `test_telegram`, and verify the test message arrives. Never paste the bot token into this chat or commit it.
- Email is not a mandatory fallback in Stage 1: a free tier may change, require account verification, or become unavailable. Do not rely on SendGrid unless separately verified and configured.

## 9. Cloudflare Pages deployment (one-time owner action)

1. Sign in to Cloudflare and open Workers & Pages.
2. Select Create application, then Pages.
3. Choose Connect to Git.
4. Authorize the GitHub account and select `hamedbenapart69-byte/Trade`.
5. Select branch `stage1-webfirst-v2-clean` for preview, or the approved release branch later.
6. Set the project root directory to `web/futures`.
7. Leave the build command empty and set the build output directory to `.`. The pipeline writes `signals.json` and `history.csv` into `web/futures/data/` and commits both files, so the static site serves them same-origin.
8. Save and deploy; Cloudflare assigns a `.pages.dev` hostname.
9. Open the hostname from the user's actual target network and verify `/data/signals.json` loads.
10. Confirm Git integration auto-deploys after a new workflow commit.

A Cloudflare account authorization cannot be fabricated or completed without the owner's Cloudflare/GitHub consent. The repo can be made deploy-ready, but the final account linking and Iran-network test require the owner.

### Visibility and privacy warning

The GitHub repository `hamedbenapart69-byte/Trade` is currently **public**. The scheduled workflow commits `signals.json` and `history.csv` to the repository, and the Pages site is public by default. Therefore, anyone may be able to read the generated signals and history. Cloudflare Access in front of the Pages URL alone would not hide files already committed to the public repository. Do not put personal account details, exchange credentials, or private portfolio information in these outputs. Repository visibility will not be changed without the owner's explicit approval.

## 10. End-to-end acceptance criteria (revised Stage 1)

### L1 Data
- [ ] 100 active USDT perpetual symbols including BTC.
- [ ] 1h OHLCV 2-year coverage for >=95% symbols, no gap >1h.
- [ ] Funding historical coverage >=95% symbols; current OKX result fails this.
- [ ] OI latest 30 days, explicitly labelled.
- [ ] Alternative.me Fear & Greed stored.
- [ ] Parquet files valid and provider-specific.
- [ ] Quality report lists gaps, coverage, and failed symbols.

### L2 Compute
- [ ] `logic.py` produces valid `signals.json` and `history.csv`.
- [ ] `signals.yml` cron every 4h plus manual dispatch.
- [ ] Exact CCXT OKX ticker probe passes on GitHub Actions runner.
- [ ] Two consecutive scheduled/manual workflow runs succeed.
- [ ] C10 seven-state validation passes; missing data yields degraded status.
- [ ] Output commit is idempotent and does not recursively trigger workflow.

### L3 Delivery
- [ ] Dashboard files present and validated.
- [ ] Cloudflare Pages URL live and accessible on user's actual network.
- [ ] Today's signals, history, and system health render from generated files.
- [ ] No fabricated sample signal.

### Notification / End-to-end
- [ ] Telegram notifier code and setup instructions present.
- [ ] One real Telegram test message received (requires user-provided bot token/chat ID).
- [ ] One end-to-end cycle: Actions -> data -> compute -> JSON/CSV -> Pages -> Telegram.
- [ ] No trading keys, account connection, or order execution.

Stage 1 is **not PASS** until every mandatory item above is evidenced. Items requiring owner account access remain explicitly BLOCKED until the owner performs the one-time authorization or supplies the relevant secret.

## 11. Known actual evidence and current blockers

From Actions run `42468815714` (completed successfully on GitHub-hosted runner):
- OKX collector run completed; 100 active symbols selected; 100 successful; 0 failed.
- 1,753,200 hourly OHLCV rows for 100 symbols; reported gap rate 0.0%, and all 100 symbol reports had no gap >1h.
- BTC funding coverage was 93.67 days / 12.822% of requested 2-year window; therefore >=95% funding acceptance is not met.
- OI coverage was 29.96 days (720 hourly rows for BTC).
- Fear & Greed returned 3,199 daily rows.
- This run used the OKX collector probe, not the exact requested CCXT `fetch_ticker` probe.
- The Actions runner is not the user's Iranian network. No claim about user's ISP reachability is made.
- No Cloudflare Pages account has been linked; no live Pages URL verified. The clean branch places the static app under `web/futures/` so it does not overwrite the existing `web/` control-panel UI on `main`. The static dashboard source exists in `web/` and reads same-origin `web/futures/data/signals.json` / `history.csv`.
- Telegram test-message function and workflow dispatch option exist, but no token/chat ID was supplied; no real Telegram notification has been sent.

## 12. Stage roadmap while preserving all three layers

| Stage | Data | Compute | Delivery |
|---|---|---|---|
| 1 | Establish provider coverage, cache, quality | Placeholder EMA/funding engine + C10 | Initial dashboard + Telegram hook |
| 2 | Validate LFS inputs and honest PROXY/UNAVAILABLE flags | LFS resilience versions | Show LFS inputs, missing-data warnings, signal history |
| 3 | Validate NSS inputs, 24h OI | NSS resilience versions | Display NSS and provenance |
| 4 | Liquidity/phase evidence or unavailable labels | Phase classification | Explain phase evidence in dashboard |
| 5 | MTF and validated market data | LRT/NMT candidate engine | Display hypotheses/invalidation |
| 6 | OOS calibration datasets | Calibration + EV_net | Confidence/calibration labels |
| 7 | Risk and consensus inputs | Consensus/risk gates | Show gate reasons |
| 8 | Historical walk-forward datasets | Plan A backtest | Publish per-path metrics |
| 9 | Cross-sectional factor datasets | Plan B | Factor scores and coverage |
| 10 | Donchian/EMA/funding inputs | Plan C | Strategy comparisons |
| 11 | Seven generator inputs | Plan H | Daily C10 output |
| 12 | Live/paper data monitoring | Paper + Shadow | Dashboard divergence and status |
| 13 | Multi-path history | Meta-Allocator only after gates | Allocation comparison, no execution |
| 14 | Additional public datasets | Innovation Protocol | Surface fallback status |
| 15 | Full evidence archive | Final decision | Final dashboard/report and operating guide |

Every stage retains the same no-paid-service, no-trading-keys, manual-trading, C10, provenance, and three-layer requirements. The V8 strategy remains separate from the Stage 1 placeholder and is not represented as active until its stage gates pass.
