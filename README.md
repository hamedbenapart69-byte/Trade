# AI Orchestration Foundation

Portable, testable starting point for an owner-controlled AI automation platform. This repository intentionally begins with a deterministic execution ledger and approval boundary; it does not pretend that a workflow engine, model provider, browser integration, or production deployment is already connected.

## Implemented
- FastAPI API: health, run creation/list/lookup, audit events, approve/reject/cancel.
- SQLite run persistence and idempotency protection; audit events.
- API-key protection for operational routes; missing token configuration fails closed.
- SQLite backup helper with integrity check.
- Dockerfile and local-only Compose binding.
- Optional n8n webhook adapter (not wired to approval routes), with guarded opt-in and mocked tests.
- GitHub Actions CI workflow.

## Not yet implemented or verified
No durable outbox/worker, retry/dead-letter queue, reconciliation, execution-ID persistence, LangGraph/model integration, Playwright integration, daily-use UI, production identity provider, or deployment. Approval records a decision; it does not execute an action. Outbound effects remain disconnected.

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

Operational routes require `X-API-Key: <CONTROL_API_TOKEN>`. Keep the service on localhost until HTTPS, production identity/access control, secret management, rate limits and monitoring are in place. Run tests with `python -m unittest discover -s tests -v`.

## n8n adapter
`ENABLE_N8N_EXECUTION` defaults to false. For isolated test workflows only, configure `N8N_WEBHOOK_URL`, optional `N8N_WEBHOOK_TOKEN`, and `N8N_TIMEOUT_SECONDS`. The receiver must validate authentication and idempotency. Do not enable production side effects until a durable outbox, explicit execution authorization and outcome reconciliation are implemented.

See `docs/` for the decision report, roadmap, security baseline and integration boundary. Never commit real credentials or operational data.
