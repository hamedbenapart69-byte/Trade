# Roadmap

## Milestone 0 — control-plane foundation
- [x] Approval-gated run ledger, API token guard, idempotency and audit events
- [x] Backup and integrity check
- [x] n8n adapter with explicit opt-in and mocked tests
- [x] Durable SQLite outbox with transactional queue insertion, lease expiry recovery, and stale-token protection

## Milestone 1 — execution reliability
- [ ] Separate worker identity/credentials and least-privilege authorization
- [ ] Backoff schedule, max-attempt policy visibility, dead-letter inspection and operator replay
- [ ] Worker process, idempotent provider delivery and downstream status reconciliation
- [ ] Test crash/restart, concurrent lease contention, callback replay, and uncertain timeouts

## Milestone 2 — agent runtime
- [ ] Add LangGraph only for stateful reasoning tasks
- [ ] Structured outputs, per-run budgets, tool allowlist, approval gates and prompt-injection tests

## Milestone 3 — daily UI and deployment
- [ ] Responsive mobile control center and real identity/authentication
- [ ] Verify hosting availability from the user's actual network
- [ ] HTTPS, secrets, logs, alerts, backups/restore and authorized end-to-end tests

Never mark a milestone complete without a commit, reproducible test evidence and environment verification where applicable.
