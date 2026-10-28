# Roadmap

## Completed and CI-verified
- [x] Approval-gated run ledger and audit trail
- [x] SQLite persistence and idempotent run creation
- [x] Durable outbox and bounded leases
- [x] Expired leases transition to unknown; explicit reconciliation required
- [x] Separate operator and worker API credentials
- [x] Opt-in one-shot worker with explicit workflow allowlist
- [x] Mobile-first local control console: create, inspect, approve/reject, queue and reconcile
- [x] SQLite backup helper with integrity verification
- [x] Automated API/unit tests and container build/health smoke test in CI
- [x] n8n adapter fails closed and does not retry automatically
- [x] Decision report records official license/pricing references and unresolved assumptions

## Remaining release gates
1. [ ] Add per-workflow JSON schemas and payload-size limits before any external dispatch.
2. [ ] Add real local HTTP integration tests for n8n adapter and worker failure paths.
3. [ ] Verify backup restore into a clean database and document the restore drill.
4. [ ] Add structured logs, metrics, cost/quota tracking and secret-redaction tests.
5. [ ] Test a real isolated n8n receiver only after its owner authorizes the test endpoint.
6. [ ] Add production-grade user identity, role-based access, CSRF/origin controls, rate limits and secret management before public hosting.
7. [ ] Choose hosting based on actual pricing, persistent storage, TLS, backup and connectivity checks; verify from the user's device/network.
8. [ ] Add model/agent runtime and browser automation only after schemas, budgets, tool allowlists and evaluation tests exist.

## Explicitly not complete
No public deployment, actual n8n instance/webhook, external model, browser automation, real-device verification, production identity provider, end-to-end real external workflow or restore drill has been verified. Do not expose this API publicly yet.
