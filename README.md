# AI Orchestration Foundation

Owner-controlled automation platform foundation. This repo contains an approval-gated run ledger, SQLite audit history, an idempotent durable outbox with transactional leasing, backup tooling, and a guarded n8n webhook adapter. The outbox is infrastructure only: no worker is currently wired to execute external actions.

## Implemented
- FastAPI API with health, run creation/list/lookup, audit events, approval/rejection/cancellation.
- Operational API-key guard; missing token configuration fails closed.
- Idempotency-key protection and SQLite persistence.
- Durable execution outbox: only approved runs can be queued; queue insertion is idempotent; worker leases are transactional and expire; stale lease tokens cannot finish jobs.
- SQLite backup and integrity verification.
- Optional n8n adapter, disabled by default and not wired to approval or outbox endpoints.
- GitHub Actions CI and unit tests.

## Not yet implemented
No autonomous worker, retry policy beyond lease recovery, dead-letter inspection UI, downstream outcome reconciliation, LangGraph/model integration, Playwright integration, mobile control center, production identity provider, or hosted deployment. Outbox lease completion is a worker contract; it is not proof that a real external action ran. Keep side effects disconnected until a worker, execution authorization, reconciliation and security review are complete.

## Local run
Python 3.11+ recommended.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CONTROL_API_TOKEN='replace-with-a-long-random-secret'
export CONTROL_DB_PATH='./data/control.db'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Operational routes require `X-API-Key`. Keep localhost binding until HTTPS, production identity/access control, secret management, rate limits and monitoring are in place. Run tests with `python -m unittest discover -s tests -v`.

## Outbox lifecycle
1. Create a run, then approve it.
2. `POST /runs/{id}/queue` persists one outbox item for that approved run.
3. A future worker calls `POST /internal/outbox/lease` and receives a bounded lease plus a one-time lease token.
4. The worker calls `POST /internal/outbox/{item_id}/finish` with the current token and outcome. Stale tokens are rejected.

These endpoints currently require the same API key; before a real worker is deployed, separate worker credentials and least-privilege authorization must be implemented. The lease contract does not itself deliver to n8n.

## n8n adapter
`ENABLE_N8N_EXECUTION` defaults to false. The adapter is not called by `/approve` or the outbox. Before production side effects, implement an isolated worker, worker-specific credentials, durable outcome reconciliation, and retry/dead-letter policy. See `docs/`.
