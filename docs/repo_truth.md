# Repo Truth — Audit Baseline

- Audit date: 2026-11-09
- Audited branch: `main`
- Audited commit: `64f8d8fcafc1300987bd9345b3551abbdd151c83`
- Purpose: establish observed repository/runtime facts before data audit A/B/C.
- Evidence policy: workflow YAML and successful run metadata/logs outrank README descriptions. Missing runtime evidence is marked `UNVERIFIED`.

## 1. Workflows actually active

### 1.1 Futures Signals Pipeline — active scheduled workflow

- File: [`.github/workflows/futures-signals.yml`](https://github.com/hamedbenapart69-byte/Trade/blob/64f8d8fcafc1300987bd9345b3551abbdd151c83/.github/workflows/futures-signals.yml)
- File blob SHA at audited main: `0fd86c77b35e281f61e143cec971ede68d0b6dbf`
- Triggers in YAML: `schedule`, `pull_request` to `main`, `workflow_dispatch`, and `push` to `stage1-webfirst-v2-clean` / `main` for specified paths.
- Latest successful scheduled execution observed: [Run 42520941228](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228)
- Event: `schedule`; conclusion: `success`; created: `2026-11-08T20:35:52Z`; commit: `64f8d8fcafc1300987bd9345b3551abbdd151c83`.
- Job logs: [signals job 128854266168](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228/job/128854266168)
- The run completed the signal job, payload validation, JavaScript syntax validation and publication to the isolated `signals` branch. The full historical collection step was skipped because the archive-complete gate was already satisfied.
- The run's final log reports `pipeline_status=DEGRADED`, `provider=kucoinfutures`, `symbols_processed=26`, `signals_total=26`, and `telegram.status=SENT_WITH_CHARTS`, `sent=15`.
- The same run's separate OKX smoke test printed `OKX PASS: BTCUSDT = 75822.4`. This proves that the OKX BTC ticker request succeeded in that run; it does **not** prove OKX was the selected provider for the full scan.

### 1.2 Other workflow files and observed triggers

- `ci.yml`: `push` and `pull_request`; no cron in the file.
- `deploy-railway.yml`: `workflow_run` after CI completion on `main`; not a Cloudflare Pages deploy.
- `mvp-validation.yml`: pull-request path filters and manual dispatch; no schedule.
- `stage1-history.yml`: path-filtered push to `stage1-webfirst-v2-clean`; no schedule.
- `additional-public-futures-probe.yml`, `okx-live-smoke.yml`, `okx-market-fields-probe.yml`, `public-market-endpoint-probe.yml`, `v5-live-validation.yml`, `v5-okx-live-scan.yml`: manual dispatch only.
- `universe-validation.yml`: path-filtered push to `fix/crypto-usdt-perpetual-universe`; no schedule.
- `v5-signal-autopilot.yml`: explicitly labeled legacy/manual diagnostics; manual dispatch only.
- This list is based on the workflow files present under `.github/workflows/` on the audited commit. Workflow existence does not prove a currently enabled repository-level Actions setting; successful run evidence is cited above for the active Futures Signals Pipeline.

## 2. Current cron and its source of control

- Source of truth: `.github/workflows/futures-signals.yml` on audited commit.
- Exact cron: `7 */4 * * *`.
- Meaning: every four hours at minute 7 UTC.
- Runtime evidence: Run 42520941228 was created with event `schedule` and completed successfully.
- The README still describes an older V5 cadence of minutes 07, 22, 37 and 52 every hour. That description is stale for the active Futures Signals Pipeline and must not be used to infer its schedule.
- The V5 legacy workflow has no cron and is manual-only.

## 3. Dashboard deployment and the two different hosting systems

- In `.github/workflows/v5-signal-autopilot.yml`, the `deploy-pages` job has `if: false`. This disables that job. Its final deployment action is `actions/deploy-pages@v4`, which is GitHub Pages deployment, not Cloudflare Pages.
- The active `futures-signals.yml` publishes generated data files to the isolated `signals` branch. It contains no Cloudflare Pages deployment action or Cloudflare Pages URL.
- The repository README currently points to a GitHub Pages URL for the V5 dashboard. The user separately supplied the Cloudflare Pages URL `https://trade-3vn.pages.dev/`.
- Why `trade-3vn.pages.dev` exists, which Cloudflare Pages project/source repository owns it, and whether it currently serves fresh content: **UNVERIFIED**. No Cloudflare account/project deployment record or live Pages deployment log was available through the inspected repository workflows. An independently configured Cloudflare Pages project or manual deployment is a possible explanation, but is not established evidence.
- Therefore the disabled GitHub Pages job does not, by itself, explain or disprove the existence of the Cloudflare URL.

## 4. Provider actually used by the latest successful scheduled run

- Selected provider reported by the pipeline itself: `kucoinfutures`.
- OKX smoke test: successful for BTC/USDT perpetual ticker in the same run.
- Overall pipeline status: `DEGRADED`.
- Symbols processed: 26.
- Telegram delivery: log reports 15 messages sent with charts.
- Conclusion: for this run, the selected end-to-end provider was KuCoin Futures, while the independent OKX smoke test passed. Do not describe this run as an OKX-powered full scan.
- Why provider selection resolved to KuCoin Futures rather than OKX, and the exact adapter fallback order at runtime: **UNVERIFIED pending code-path audit and provider-specific log inspection**.

## 5. Reality / assumptions / limitations

### Observed facts
- Repository visibility returned by GitHub metadata: `public`.
- Main branch HEAD at audit time: `64f8d8fcafc1300987bd9345b3551abbdd151c83`.
- The Futures Signals Pipeline has a four-hour schedule in YAML and a successful scheduled run.
- The latest successful scheduled run selected `kucoinfutures`, was degraded, and logged Telegram chart delivery.
- The legacy V5 GitHub Pages deploy job is disabled with `if: false`.

### Assumptions not promoted to facts
- The Cloudflare Pages URL may belong to an independently configured Cloudflare Pages project. This remains an inference until Cloudflare deployment metadata or a verifiable deployment log is obtained.
- A successful OKX ticker smoke test does not establish that all OKX market-data endpoints, symbols, or timeframes are available.

### Limitations
- No Cloudflare account connector/project deployment record was available in this audit.
- GitHub repository evidence cannot establish whether the Cloudflare Pages site is currently fresh or which external source is connected.
- The exact provider-selection reason and adapter fallback sequence require source-code tracing and runtime logs; not inferred from README text.

## 6. Audit gate

This document records repository truth only. It does not implement or change any engine, data adapter, workflow schedule, deployment, trading behavior, or secret. Data audit A, edge hypothesis B, and cost model C remain separate deliverables and require their own evidence. No code under `src/engines/` is authorized before all four documents are delivered and approved.
