# Repository Truth and Zero-Cost Gate

- Audit date: 2026-11-09 UTC
- Audited production branch: main
- Audited production commit: 64f8d8fcafc1300987bd9345b3551abbdd151c83
- Evidence branch: docs/v2-specs (derived from audit/repo-truth-v1)
- Evidence rule: workflow YAML, committed source, Actions logs, and generated output outrank README prose. Documentation-only assumptions are never promoted to REAL.
- Scope: read-only market-data system. No exchange account credentials, trading API keys, private account endpoints, or order execution.

## 1. Repository identity and visibility

| Item | Result | Evidence |
|---|---|---|
| Repository visibility | PUBLIC | GitHub repository metadata: https://github.com/hamedbenapart69-byte/Trade |
| Default branch | main | GitHub repository metadata |
| Audited main HEAD | 64f8d8fcafc1300987bd9345b3551abbdd151c83 | https://github.com/hamedbenapart69-byte/Trade/commit/64f8d8fcafc1300987bd9345b3551abbdd151c83 |
| Public standard GitHub-hosted runner cost | $0 for public-repository standard runners | Official GitHub billing docs: https://docs.github.com/en/actions/concepts/billing-and-usage |

## 2. Workflow inventory: every YAML file on main

All 13 workflow YAML files present under .github/workflows on audited main were matched to at least one historical Actions run in the repository's retrieved run history. None is labeled NEVER_RUN. “Last run” is the latest observed run for that workflow file; branch and event are shown because a run on a feature branch does not prove that the workflow is active on main.

| Workflow file | Current trigger in main YAML | Cron | Last observed run | Result / note |
|---|---|---|---|---|
| additional-public-futures-probe.yml | workflow_dispatch | None | [42310288347](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42310288347), 2026-11-06, push on diagnostics/public-market-endpoint-probe | success |
| ci.yml | push, pull_request | None | [42523754306](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42523754306), 2026-11-08, push on audit/repo-truth-v1 | success |
| deploy-railway.yml | workflow_run after CI completes on main | None | [42520860582](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520860582), 2026-11-08, workflow_run on main | job succeeded, but Railway token check caused install/deploy/health steps to be skipped; no Railway deployment occurred in this run |
| futures-signals.yml | schedule, push, pull_request, workflow_dispatch | 7 */4 * * * | [42520941228](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228), 2026-11-08, schedule on main | success as a workflow; pipeline payload itself was DEGRADED |
| mvp-validation.yml | pull_request path filters, workflow_dispatch | None | [42520378016](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520378016), 2026-11-08, pull_request | success |
| okx-live-smoke.yml | workflow_dispatch | None | [42310295990](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42310295990), 2026-11-06, push on diagnostics/public-market-endpoint-probe | success |
| okx-market-fields-probe.yml | workflow_dispatch | None | [42310291763](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42310291763), 2026-11-06, push on diagnostics/public-market-endpoint-probe | success |
| public-market-endpoint-probe.yml | workflow_dispatch | None | [42310246693](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42310246693), 2026-11-06, push on diagnostics/public-market-endpoint-probe | success |
| stage1-history.yml | push on stage1-webfirst-v2-clean with RUN_FULL_HISTORY.txt path filter | None | [42479427928](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42479427928), 2026-11-08, push on stage1-webfirst-v2-clean | success |
| universe-validation.yml | push on fix/crypto-usdt-perpetual-universe with path filters | None | [42492231646](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42492231646), 2026-11-08, push on fix/crypto-usdt-perpetual-universe | success |
| v5-live-validation.yml | workflow_dispatch | None | [42362344969](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42362344969), 2026-11-07, push on fix/v5-contract-metadata-access | success |
| v5-okx-live-scan.yml | workflow_dispatch | None | [42310301331](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42310301331), 2026-11-06, push on diagnostics/public-market-endpoint-probe | success |
| v5-signal-autopilot.yml | workflow_dispatch only | None | [42504492392](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42504492392), 2026-11-08, push on main | success; current YAML is manual-only and explicitly describes legacy diagnostics |

### 2.1 Actual scheduled workflow

- The only cron in the 13 main-branch workflow files is in futures-signals.yml.
- Exact schedule: 7 */4 * * * (every four hours at minute 7 UTC).
- The latest successful scheduled run observed is Run 42520941228, event=schedule, commit 64f8d8f: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228
- The README's older V5 cadence is not the active schedule. The V5 workflow currently has no cron.

## 3. Actual provider fallback chain and why KuCoin was selected

### 3.1 Source-code behavior

The audited main source file is:
https://github.com/hamedbenapart69-byte/Trade/blob/64f8d8fcafc1300987bd9345b3551abbdd151c83/signal_autopilot/modules/data_fetcher.py

The provider order in code is:

1. OKX
2. Bybit
3. Binance USD-M Futures
4. Bitget
5. MEXC
6. KuCoin Futures

The selector accepts the first provider returning at least 50 eligible rows. If no provider reaches 50, it selects the provider with the largest result set among those attempted. Therefore a selected KuCoin provider does not, by itself, prove that OKX returned an HTTP error. The code's per-provider candidate counts are not persisted in the final payload, so the exact row count for each earlier provider remains UNVERIFIED.

### 3.2 Run #54 evidence

- Run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228
- Commit: 64f8d8fcafc1300987bd9345b3551abbdd151c83
- Job log: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228/job/128854266168
- The separate OKX smoke request printed: OKX PASS: BTCUSDT = 75822.4.
- The pipeline summary printed provider=kucoinfutures, symbols_processed=26, signals_total=26, pipeline_status=DEGRADED.
- The final payload has data_errors={} and provider=kucoinfutures.

Conclusion: the standalone OKX BTC ticker smoke test passed, but the full scan selected KuCoin Futures. The evidence does not show an OKX 403 in this run. Do not claim that OKX was blocked or failed unless a provider-specific error log proves it.

## 4. DEGRADED diagnosis: exact trigger and measured impact

Source output:
https://github.com/hamedbenapart69-byte/Trade/blob/signals/signals.json

Run evidence:
https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228

The published payload reports:

| Field | Observed value |
|---|---:|
| symbols_requested | 100 |
| symbols_processed | 26 |
| symbols_unscanned | 74 |
| coverage_pct | 26.0 |
| coverage_status | PARTIAL |
| symbols_degraded | 0 |
| trade_signals | 15 |
| data_errors | empty object |

For the 26 processed symbols, the payload reports OHLCV=OK, funding=OK, and open_interest=OK for all 26. However, all 26 ticker timestamps use FETCH_TIME_PROXY rather than an exchange-provided timestamp.

The signal-engine code marks the pipeline DEGRADED when either a processed symbol has degraded market data or the requested universe is only partially scanned. In this payload, symbols_degraded=0 and 74 symbols are unscanned. Therefore the proven trigger is incomplete universe coverage: 26/100, not missing OHLCV/Funding/OI among the 26 processed rows.

This 26% runtime symbol-scan coverage is not LFS/NSS component coverage. No LRT/NMT engine coverage can be inferred from this legacy EMA MVP payload. The old 0.775 LRT estimate is not validated by this run.

## 5. Dashboard deployment path

### 5.1 What the repository proves

- In v5-signal-autopilot.yml, the deploy-pages job has if: false. It is disabled.
- That job's final action is actions/deploy-pages@v4, which would deploy GitHub Pages, not Cloudflare Pages.
- The active futures-signals.yml workflow publishes generated JSON/CSV to the isolated signals branch. It contains no Cloudflare Pages deployment step, Wrangler action, or Cloudflare Pages upload.
- signal_autopilot/modules/notifier.py uses DASHBOARD_URL if configured, otherwise falls back to the literal URL https://trade-3vn.pages.dev/. This explains why the URL appears in Telegram messages; it does not prove the site was deployed by this repository.
- The deploy-railway.yml workflow is separate. Its latest observed run skipped the Railway CLI install, deployment, and health-check steps because the Railway token was not available. It is not a Cloudflare deployment path.

### 5.2 What remains UNVERIFIED

- Which Cloudflare account owns trade-3vn.pages.dev.
- Whether it is a Pages project connected to GitHub, a Direct Upload project, or another Cloudflare configuration.
- The source repository, branch, commit, latest successful deployment, and production freshness.
- Whether any Cloudflare Workers scripts exist in the user's account.
- Number of Cloudflare Cron Triggers currently used.
- Whether an R2 bucket already exists.

No Cloudflare account/API credentials or Cloudflare account connector were available in this audit environment. GitHub repository access cannot reveal Cloudflare account-level project, Worker, Cron, or R2 inventory. The URL's existence is not evidence of an active, current deployment.

## 6. GitHub Actions runner evidence for public market-data sources

The read-only audit workflow and script were run on GitHub-hosted ubuntu-latest runners on branch audit/repo-truth-v1. No exchange credentials or trading endpoints were used.

Latest expanded probe:
- Run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42523754302
- Commit: b625499ec59b34057e6f9f9e97269c68da37eb57
- Job logs contain raw HTTP status, response detail, record counts, and date ranges.

Observed results:

| Source / endpoint | GitHub Runner result | Evidence-based conclusion |
|---|---|---|
| Binance USD-M funding history fapi.binance.com | HTTP 451; response says service unavailable from a restricted location | UNAVAILABLE from this runner/location |
| Binance alternate host fapi1.binance.com | HTTP 202 with empty body; invalid JSON | Not usable in this test |
| Binance daily OI history | HTTP 451 | UNAVAILABLE from this runner/location |
| Binance Futures depth | HTTP 451 | UNAVAILABLE from this runner/location |
| Bybit funding history | HTTP 403; CloudFront says access from this country is blocked | UNAVAILABLE from this runner/location |
| Bybit OI history | HTTP 403; same country-block message | UNAVAILABLE from this runner/location |
| Bybit long/short ratio | HTTP 403; same country-block message | UNAVAILABLE from this runner/location |
| OKX public order book | HTTP 200; 50 bid and 50 ask levels | REAL live snapshot at test time |
| Binance Vision spot 1h klines | HTTP 200 for sampled BTC, ETH, SOL and other symbols/months | REAL archive samples; not a complete universe audit |
| Binance Vision USD-M Futures 1h klines | HTTP 200 for sampled symbols/months | REAL archive samples; not a complete universe audit |
| Binance Vision matched spot/futures closes | BTC, ETH and SOL same-candle timestamps matched; basis computed | REAL sample basis calculation |
| Binance Vision daily fundingRate sample path | HTTP 404 NoSuchKey for the tested path | That exact archive path is unavailable; do not generalize to all archive layouts |

The audit run is a point-in-time test from the GitHub runner region. It does not prove that these endpoints are blocked from every geography or every hosting provider.

## 7. KuCoin Futures historical endpoint probes

The KuCoin probes were executed on GitHub-hosted ubuntu-latest, with no credentials.

Evidence run:
https://github.com/hamedbenapart69-byte/Trade/actions/runs/42523754302

| Data | Probe result | Interpretation |
|---|---|---|
| Futures 1h Klines, 2024-11-08 to 2024-11-10 | HTTP 200, 49 rows; first timestamp 2024-11-08 | At least a two-year-old historical sample is retrievable |
| Futures 1h Klines, 2026-11-08 | HTTP 200, 22 rows | Recent sample retrievable |
| Funding history, 2024-11-08 to 2024-11-14 | HTTP 200, code 200000, 21 rows; oldest 2024-11-08 04:00 UTC, newest 2024-11-14 20:00 UTC | At least a two-year-old funding sample is retrievable |
| Funding history, broad two-year range | HTTP 200, 100 rows; oldest returned 2026-10-06, newest 2026-11-08 | Broad query returned only 100 recent records in this request; full two-year continuity is NOT proven |
| Daily OI, broad two-year request, pageSize=100 | HTTP 200, 100 rows; oldest returned 2026-08-01, newest 2026-11-08 | Request is page-limited; this result does not establish two-year history |
| Daily OI, 2024-11-08 to 2024-11-14 | HTTP 200, zero rows | No OI rows returned for the two-year-old week |
| Daily OI, recent 70-day request | HTTP 200, 70 rows; 2026-08-31 to 2026-11-08 | Recent daily OI history works |

Important qualification: the tests prove that KuCoin can return sampled Klines and Funding records from approximately two years earlier. They do not prove complete, gap-free two-year coverage across all symbols. The 100-row OI response spans approximately 99 days, while current KuCoin documentation describes 70-day daily retention and 7-day intraday retention. This discrepancy is recorded as NEEDS_REVIEW; the old-week OI query returned zero rows.

Official KuCoin endpoint documentation:
- Klines, maximum 500 rows per request: https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines
- Public funding history: https://www.kucoin.com/docs-new/rest/futures-trading/funding-fees/get-public-funding-history
- Futures OI retention documentation: https://www.kucoin.com/docs-new/v2/rest/ua/get-futures-open-interest

### 7.1 KuCoin rate-limit correction

Do not use 30 requests / 3 seconds as a universal KuCoin public-market-data limit. Current KuCoin documentation describes resource pools, endpoint weights, and quotas that vary by account/VIP level. The public endpoint weights observed in documentation are Klines=3, funding history=5, and OI=10. The 30/3s figure appears in a 2021 announcement for a specific Futures open-order endpoint per UserId, not as a general public data API limit:
https://www.kucoin.com/announcement/adjustment-of-the-spot-and-futures-api-request-limit

The exact effective public-pool quota for the runner is not measured in this audit. Treat it as UNVERIFIED and obey response headers / current official rate-limit documentation rather than hardcoding 600 requests per minute.

## 8. ZC-1 / Zero-Cost Check

Zero-cost is a hard acceptance gate. “Free” does not mean unlimited, and a service that requires a paid plan, credit-card commitment, or free trial is rejected under the project rules.

| Service | Verified free boundary / correction | Project impact |
|---|---|---|
| GitHub Actions public standard runners | Standard runners in public repositories are free; this is not an unlimited-capacity guarantee. Standard Free concurrency is 20; a hosted job is limited to 6 hours. GitHub Free plan table lists 500 MB artifact storage and 10 GB cache storage per repository. | Do not use Actions artifacts as the long-term Parquet store. The current 360-minute job timeout equals the hosted-job ceiling. |
| Cloudflare Pages Free | 500 builds per month and 1 concurrent build, not 500 builds per minute. | A four-hour cron does not require a Pages rebuild; keep market data separate from static site deployment. |
| Cloudflare Workers Free | 100,000 requests/day, 10 ms CPU/request, 5 Cron Triggers/account. | Worker is only a fallback; do not move compute-heavy backfills into Workers. |
| Cloudflare R2 Free | 10 GB-month storage, 1 million Class A operations/month, 10 million Class B operations/month; internet egress is free. | Potential archive target, but actual bucket/account state and usage are UNVERIFIED. Do not upload until account access and hard caps are confirmed. |
| Binance public REST | Runner probes returned 451/202 as above. Official API weight/limits are endpoint-specific and can change. | Do not rely on Binance REST from this runner. |
| KuCoin public Futures | Klines weight 3, funding weight 5, OI weight 10; effective public-pool quota not measured. | Use conservative pacing and bounded pagination; do not assume 30/3s universal quota. |
| Telegram Bot | Free limits: private chat avoid more than 1 message/sec; groups max 20/min; bulk broadcast about 30/sec. | The observed run acknowledged 15 photo sends. Per-message timestamps and daily aggregate are not present, so pacing and daily usage remain UNVERIFIED. |
| Railway | Optional deployment workflow exists, but latest observed run skipped token check/deploy steps. | Not part of the approved zero-cost delivery architecture. Do not activate it. |

Official references:
- GitHub Actions billing: https://docs.github.com/en/actions/concepts/billing-and-usage
- GitHub Actions limits: https://docs.github.com/en/actions/reference/limits
- Cloudflare Pages limits: https://developers.cloudflare.com/pages/platform/limits/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Cloudflare R2 pricing: https://developers.cloudflare.com/r2/pricing/
- Telegram Bot FAQ: https://core.telegram.org/bots/faq

### 8.1 Estimated usage and safety margin

- Scheduled signal pipeline: six runs/day at the current four-hour cadence. Run #54 lasted about 2 minutes 23 seconds from workflow start to final update. A simple planning estimate is about 430 runner-minutes/month for this workflow alone (6 × 30 × 2.4 minutes). This is an estimate from one run, not a guaranteed monthly cost. Public standard-runner compute is free, but artifacts/cache and concurrency limits still apply.
- Telegram: Run #54 logged 15 successful Bot API sends with charts. At six runs/day, a naive upper-bound projection is 90 messages/day if every run repeats 15 unique sends. This is not observed daily usage. The current code has no explicit one-message-per-second pacing loop, so private-chat rate safety is not yet proven.
- R2: no bucket has been verified or created. Storage/object-size consumption cannot be estimated reliably until actual snapshot sizes are measured. Keep forward collection disabled until the account/bucket and monthly budget are verified.
- Cloudflare Pages: no deployment or build usage could be inspected. Account usage is UNVERIFIED.
- KuCoin: request volume per run is not emitted as a complete counter. API weight consumption and rate-limit headroom are UNVERIFIED.

## 9. ZC-4 gate status

| Required item | Answer | Status |
|---|---|---|
| 1. Repository public or private? | Public, confirmed by GitHub repository metadata | CONFIRMED |
| 2. Cloudflare Cron Triggers used, out of 5? | No Cloudflare account/API inventory access; repository workflows show GitHub Actions cron, not Cloudflare Cron | UNVERIFIED |
| 3. R2 bucket exists? If not, create it | Account/bucket inventory unavailable; no bucket was created | UNVERIFIED / NOT CREATED |
| 4. Telegram real usage | Run #54 logged 15 successful Bot API sends with charts; no daily aggregate or per-message timestamps; user receipt of these 15 messages is not confirmed | API_ACKNOWLEDGED=15; USER_CONFIRMED=UNVERIFIED |

R28 gate: Stage 1 is BLOCKED until Cloudflare Cron usage and R2 bucket/account state are resolved. No R2 bucket was created because no Cloudflare account authorization was available. Do not infer account state from the public pages.dev hostname.

## 10. Delivery truth

- The active scheduled workflow computes and publishes a JSON/CSV payload to the signals branch.
- Run #54 delivered a DEGRADED payload with 26/100 symbol scan coverage.
- Telegram log status was SENT_WITH_CHARTS, sent=15. This indicates successful Bot API responses from the sending code, not user-confirmed receipt on the target device.
- The dashboard's Cloudflare deployment origin and freshness remain UNVERIFIED.
- Therefore the repository has a working scheduled compute/publication path, but a fully verified web-first Cloudflare deployment path is not established.

## 11. Audit workflow budget

The public-endpoint audit workflow was executed five times on 2026-11-08 while adding and correcting endpoint probes. This exceeded the v2.3 target of at most three test-workflow runs per day. The reason was iterative probe/parser correction. No further public-endpoint audit workflow runs should be started on that day; batch remaining probes into one run on the next permitted test day.

The audit workflow/script live on the audit evidence branch and are not part of the production main workflow inventory. No code under src/engines/ was created or modified.

## 12. Gate decision

- repo_truth: EVIDENCE-BASED, with explicit UNVERIFIED items above.
- Provider selection: KuCoin Futures selected in Run #54; exact per-provider candidate counts were not persisted.
- DEGRADED: proven cause is 74 unscanned symbols (26% scan coverage).
- KuCoin two-year history: sampled Klines and Funding points from Nov 2024 were retrieved; complete continuous two-year coverage is not proven. Historical OI from the same old week returned zero rows.
- Cloudflare deployment path: UNVERIFIED.
- R2 bucket / Cloudflare Cron inventory: UNVERIFIED.
- Stage 1: BLOCKED by R28 until Cloudflare account-level ZC-4 items are answered.
- src/engines/: NOT STARTED; requires explicit user approval after the prerequisite documents and gates.
