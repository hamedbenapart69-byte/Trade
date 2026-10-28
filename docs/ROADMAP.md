# Roadmap

## Milestone 0 — control-plane foundation
- [x] Approval-gated run ledger, API token guard, idempotency, audit events
- [x] Local backup and integrity check
- [x] CI workflow definition
- [x] n8n adapter with explicit opt-in, timeout and mocked tests

## Milestone 1 — execution reliability
- [ ] Transactional outbox and durable worker lease
- [ ] Explicit states: queued, dispatching, submitted, succeeded, failed, unknown, cancel_requested
- [ ] Persist external execution identifiers and reconcile uncertain outcomes
- [ ] Test crash/restart, duplicate delivery, stale leases, authentication failure, timeout and callback replay

## Milestone 2 — agent runtime
- [ ] Add LangGraph only for stateful reasoning tasks
- [ ] Structured outputs, per-run budgets, tool allowlist and approval gates
- [ ] Prompt-injection tests and independent result validation

## Milestone 3 — daily UI and deployment
- [ ] Responsive mobile control center and real authentication/authorization
- [ ] Verify hosting availability from user's actual network
- [ ] Configure secrets, HTTPS, logs, alerts, backups and restore tests
- [ ] Run end-to-end tests against an explicitly authorized test integration

Never mark a milestone complete without a commit, reproducible test evidence, and environment verification where applicable.
