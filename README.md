# AI Orchestration Foundation

> Scope note: this repository also contains a separate orchestration/control-plane foundation. The approved Trader_me signal product is permanently Telegram-only. All web dashboards, including legacy GitHub Pages and Cloudflare Pages surfaces, are archived and unmaintained; no web dashboard deployment is in scope. The legacy V5 workflow is not the approved signal engine.


Owner-controlled automation platform in repository [Trade](https://github.com/hamedbenapart69-byte/Trade). The current release is a tested foundation, not yet a production-hosted autonomous AI platform.

## Implemented

- FastAPI control API with health, run creation/list/lookup, audit events, approval/rejection/cancellation.
- SQLite persistence, idempotency-key protection and audit history.
- Durable execution outbox with transactional enqueue and bounded leases.
- Expired leases become `unknown`; retry requires explicit operator reconciliation.
- Separate operator and worker credentials; missing credentials fail closed.
- Mobile-first local console served at `/`: operational KPIs, run history, approve/reject, queue, event inspection and unknown-outcome reconciliation.
- Registered workflow schema boundary. `research.scan` validates symbol, market and timeframe; unregistered workflows cannot be queued.
- 32 KiB input limit and no persistence of downstream response bodies.
- Opt-in one-shot worker with explicit allowlist; no background execution loop and no automatic retry after uncertain delivery.
- Guarded n8n webhook adapter, local HTTP integration tests, backup verification and GitHub Actions CI.

## Verified evidence

CI: [latest workflow runs](https://github.com/hamedbenapart69-byte/Trade/actions). CI runs unit/API tests, builds the Docker image and smoke-tests the container health endpoint. Tests include an approved research run reaching a local HTTP receiver and persisting completion.

Deployed preview: https://control-plane-v2-production-8d31.up.railway.app/ (Railway, persistent 500 MB volume, TLS, one replica). Health endpoint and deployment are verified. The live CoinGecko public API endpoint was independently reachable; unit tests use a mocked HTTP client. A full authenticated browser-triggered run through the hosted queue has not yet been verified. No live n8n instance, hosted model, external browser automation, identity provider or real-device mobile access has been verified.

## Local run

Requires Python 3.12 recommended and dependencies from requirements.txt.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CONTROL_API_TOKEN='use-a-random-secret-at-least-24-characters'
export WORKER_API_TOKEN='use-a-different-random-secret-at-least-24-characters'
export CONTROL_DB_PATH='./data/control.db'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/` on the same device. Enter the operator token in the console. The page keeps it in memory only; it does not write the token to browser storage.

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Outbox lifecycle

1. Create a run with an `Idempotency-Key`.
2. Approve it through the API or local console.
3. Queue only an approved run with a registered workflow schema.
4. The one-shot worker remains disabled unless `ENABLE_WORKER_EXECUTION=true`; it requires the distinct worker token and explicit `WORKER_ALLOWED_WORKFLOWS` allowlist.
5. An expired lease becomes `unknown`. Inspect the destination before an operator explicitly reconciles it to retry or fail.
6. A 2xx webhook response means the receiver accepted an HTTP request, not that downstream work necessarily completed.

## n8n adapter

`ENABLE_N8N_EXECUTION=false` by default. The adapter rejects non-loopback plain HTTP, disables redirects, bounds timeouts and does not retry automatically. No live n8n endpoint has been configured or contacted. See `docs/N8N-INTEGRATION.md`.

## Deployment and security

Compose binds the API to `127.0.0.1:8000` and persists SQLite in a named volume. The current public Railway URL is an owner-operated preview, not a hardened production release. Operational API routes require an API key; the root console and health endpoint are public. Before storing sensitive data or treating this as production, add identity/role authorization, rate limiting and origin protections, external backup/restore verification, alerting, and a real-device access test. The one-shot worker is enabled only for the read-only market.snapshot allowlist; n8n execution remains disabled. See `docs/SECURITY-BASELINE.md` and `docs/ROADMAP.md`.

## Research and architecture

See `docs/DECISION-REPORT.md` for a weighted preliminary comparison of n8n, Activepieces, Windmill, a custom control plane and Cloudflare. Scores are engineering judgment rather than benchmark measurements. License, price, quotas and access from the target network must be rechecked before choosing a hosted provider.

## Legacy Futures Signal Autopilot V5 (ARCHIVED / UNMAINTAINED)

V5 is retained as a legacy manual-diagnostics workflow; it is not the currently scheduled Futures Signals Pipeline. Its documented CoinGecko + OKX architecture describes the V5 implementation, not necessarily the provider selected by the active pipeline. The latest successful scheduled Futures Signals Pipeline run (2026-11-08, run [42520941228](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228), commit `64f8d8fc`) reported `provider=kucoinfutures` and `pipeline_status=DEGRADED`. That same run's separate OKX BTC ticker smoke test passed. The runtime provider-selection reason remains under audit.

- Market discovery: CoinGecko top 100 by market cap, intersected with OKX live linear USDT perpetual contracts; candidates are ranked by CoinGecko 24-hour volume. The extended scan selects up to 100 eligible assets (30 primary shortlist plus up to 70 expanded discovery assets).
- Futures data: OKX public read-only instruments, ticker, completed OHLCV (15m/1h/4h/1d), funding, mark/index, open interest and global account ratio. No exchange account, private API credential, order endpoint or execution route is used.
- Legacy web dashboard: ARCHIVED / UNMAINTAINED. The GitHub Pages deployment job remains disabled (`if: false`). The Cloudflare Pages URL `https://trade-3vn.pages.dev/` is outside the approved product scope; its current availability and freshness are not guaranteed.
- V5 workflow: manual dispatch only at [V5 Futures Signal Autopilot](https://github.com/hamedbenapart69-byte/Trade/actions/workflows/v5-signal-autopilot.yml); it has no cron. The active scheduled workflow is [Futures Signals Pipeline](https://github.com/hamedbenapart69-byte/Trade/actions/workflows/futures-signals.yml), whose current YAML cron is `7 */4 * * *` (every four hours at minute 7 UTC). The latest successful scheduled run is [42520941228](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42520941228).
- Immediate decisions: BUY_NOW / SELL_NOW only. Conditional decisions are shown separately. WAIT, REJECT and INSUFFICIENT_DATA never appear as executable entries. Zero qualifying signals is a valid output; thresholds are not lowered to fill the table.
- Risk policy: USD 200 reference capital, maximum planned loss USD 4 before fees/slippage/funding/execution gaps, leverage no greater than 5x or the venue's published maximum (whichever is lower), stop distance 0.5%-3%, and reward/risk at least 2. Position sizing and reward/risk start from unrounded V5 prices; tick/lot rounding is then applied and the actual rounded stop distance, planned loss, leverage and quantity constraints are revalidated.
- The dashboard is a read-only signal publisher. It does not connect to an exchange account or place, modify, or cancel orders. Paper observations are public-OHLCV tracking, not executed-trade performance.
- OKX is the source venue for contract sizing. Do not copy its quantity directly to another exchange without rechecking contract multiplier, tick/lot rules, price, fees and margin requirements. Direct OKX account eligibility and API reachability from Iran have not been verified; cloud-runner access does not establish local account eligibility.
- Active OKX adapter does not supply smart-money or on-chain wallet evidence. Missing evidence is not fabricated and receives no points.

See [V5 source, limits and verification status](docs/FUTURES-SIGNAL-AUTOPILOT-V5.md) and [operational runbook](docs/v5-signal-autopilot.md).


## Approved signal product contract (v2.5)

- Delivery: Telegram only, permanently unless the user explicitly changes the decision.
- Required signal structure: nine sections (header, chart image, concise Persian rationale, Ichimoku status, trade levels, calibration/coverage, costs/EV, conditional risk flags, footer).
- Analysis target: LFS/NSS + Ichimoku M10 + engine-specific triggers; Ichimoku is a filter for LRT and confirmation for NMT, never a standalone signal generator.
- Tier A requires per-symbol coverage, calibration, positive net EV, walk-forward evidence, and all risk gates. Aggregate universe scan coverage is tracked separately as system health.
- System state is typed: `HEALTHY`, `DATA_DEGRADED`, `BUG_STATE`, `VALIDATION_FAILED`. `BUG_STATE` blocks all signal publication.
- The current EMA20/EMA50 + ATR14 code is legacy MVP and must not be represented as the completed v2.5 analytical engine.
