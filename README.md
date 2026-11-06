# AI Orchestration Foundation

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

## Futures Signal Autopilot V5

The V5 scanner is in `app/signals.py`:
- `POST /signals/scan`
- `GET /signals/latest`
- `GET /signals/performance`
- `POST /signals/evaluate`

Discovery uses CoinGecko. Numerical 15m/1h/4h/1d futures OHLCV, prices, derivatives and optional smart-money evidence use TraderSpy's read-only market-data API. The underlying public feed identifies as Binance USDⓈ-M futures, accessed through TraderSpy. There is no direct Binance connection, exchange account, exchange API key, or order execution.

**Repository runner setup:** the free TraderSpy data-provider plan requires a read-only API key. Add it to GitHub Actions secrets as `TRADERSPY_API_KEY`. This is not an exchange key and cannot place trades. Free-plan limits are 300 API calls/day and 10/minute; a standard 30-asset scan uses about132 calls and takes around 13–15 minutes. The key is not committed to source.

The ChatGPT TraderSpy connector was live-tested for BTCUSDT in this session. The GitHub REST runner has not yet completed a live 30-asset scan because its separate API secret is not configured. See [V5 source, limits and verification status](docs/FUTURES-SIGNAL-AUTOPILOT-V5.md) and [mobile-friendly TraderSpy key setup](docs/SETUP_TRADERSPY_API_KEY.md).
