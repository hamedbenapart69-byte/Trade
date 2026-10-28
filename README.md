# AI Orchestration Foundation

Owner-controlled automation platform foundation. This repo contains an approval-gated run ledger, SQLite audit history, a durable execution outbox with transactional leasing, manual reconciliation for uncertain outcomes, backup tooling, and a guarded n8n webhook adapter.

## Web console\nA mobile-first control console is served at the root URL when the API is running. It keeps the operator token in page memory only, supports run creation, approval/rejection, queueing, audit events and outbox reconciliation. It is intended for local use only; it is not a substitute for production identity/access controls.\n\n## Implemented
- FastAPI API with health, run creation/list/lookup, audit events, approval/rejection/cancellation.
- Operational API-key guard; missing token configuration fails closed.
- Idempotency-key protection and SQLite persistence.
- Durable execution outbox: only approved runs can be queued; queue insertion is idempotent.
- Expired leases become `unknown` instead of being retried automatically; an operator must explicitly reconcile after checking downstream effects.
- SQLite backup and integrity verification.
- Optional n8n adapter, disabled by default and not wired to approval or outbox endpoints.
- GitHub Actions CI and unit tests.

## Not yet implemented
A one-shot opt-in worker is implemented with an explicit workflow allowlist and guarded n8n delivery; no worker runs automatically. No model/LangGraph integration, Playwright integration, mobile control center, production identity provider, or hosted deployment. Approval records a decision; it does not execute an action. External side effects remain disconnected.

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
Operator routes require `X-API-Key: CONTROL_API_TOKEN`; worker lease/finish routes require a separate `X-API-Key: WORKER_API_TOKEN`. Never reuse one token for both. Keep localhost binding until HTTPS, production identity/access control, secret management, rate limits and monitoring are in place. Run tests with `python -m unittest discover -s tests -v`.

## Outbox lifecycle
1. Create a run with an idempotency key.
2. Approve it through the control API or local console.
3. Queue only the approved run.
4. The one-shot worker stays disabled unless ENABLE_WORKER_EXECUTION=true; it requires a separate worker token and an explicit WORKER_ALLOWED_WORKFLOWS allowlist.
5. An expired lease becomes unknown; an operator must inspect the destination and explicitly reconcile before retrying.
6. The local console is served at /; it is not production identity management and must not be exposed publicly as-is. Only workflows registered in app/workflow_schemas.py can enter the execution queue; research.scan validates symbol, market and timeframe.

## n8n adapter
`ENABLE_N8N_EXECUTION` defaults to false. The adapter is not called by approval or outbox routes. Do not enable production side effects until an isolated worker, worker-specific credentials, downstream outcome reconciliation, and retry/dead-letter policy are implemented. See `docs/`.
