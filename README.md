# AI Orchestration Foundation

Owner-controlled automation platform foundation. This repo contains an approval-gated run ledger, SQLite audit history, a durable execution outbox with transactional leasing, manual reconciliation for uncertain outcomes, backup tooling, and a guarded n8n webhook adapter.

## Implemented
- FastAPI API with health, run creation/list/lookup, audit events, approval/rejection/cancellation.
- Operational API-key guard; missing token configuration fails closed.
- Idempotency-key protection and SQLite persistence.
- Durable execution outbox: only approved runs can be queued; queue insertion is idempotent.
- Expired leases become `unknown` instead of being retried automatically; an operator must explicitly reconcile after checking downstream effects.
- SQLite backup and integrity verification.
- Optional n8n adapter, disabled by default and not wired to approval or outbox endpoints.
- GitHub Actions CI and unit tests.

## Not yet implemented
No autonomous worker, production worker-specific credentials, model/LangGraph integration, Playwright integration, mobile control center, production identity provider, or hosted deployment. Approval records a decision; it does not execute an action. External side effects remain disconnected.

## Local run
Python 3.11+ recommended.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt httpx
export CONTROL_API_TOKEN='replace-with-a-long-random-secret'
export CONTROL_DB_PATH='./data/control.db'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Operational routes require `X-API-Key`. Keep localhost binding until HTTPS, production identity/access control, secret management, rate limits and monitoring are in place. Run tests with `python -m unittest discover -s tests -v`.

## Outbox lifecycle
1. Create a run, then approve it.
2. `POST /runs/{id}/queue` persists one outbox item for that approved run.
3. A future worker calls `POST /internal/outbox/lease` and receives a bounded lease plus a one-time lease token.
4. The worker calls `POST /internal/outbox/{item_id}/finish` with the current token and outcome.
5. If a lease expires, the item becomes `unknown`. Check the destination first, then call `POST /internal/outbox/{item_id}/reconcile` with `action=retry` or `action=fail`, actor and an explanatory note. This is deliberately not an automatic retry.

These endpoints currently require the same API key. Before deploying a real worker, implement separate worker credentials and least-privilege authorization.

## n8n adapter
`ENABLE_N8N_EXECUTION` defaults to false. The adapter is not called by approval or outbox routes. Do not enable production side effects until an isolated worker, worker-specific credentials, downstream outcome reconciliation, and retry/dead-letter policy are implemented. See `docs/`.
