# Roadmap

## Foundation complete
- [x] Approval-gated run ledger and audit trail
- [x] SQLite persistence and idempotent run creation
- [x] Durable outbox with bounded leases
- [x] Fail-safe handling of expired leases: `unknown` plus explicit operator reconciliation
- [x] Backup integrity check and CI tests
- [x] Guarded, disabled-by-default n8n adapter

## Next milestones
1. Split owner/operator and worker authentication; enforce least privilege.
2. Build a worker process with explicit workflow allowlist, per-workflow schemas, execution IDs, bounded payloads and safe shutdown.
3. Add isolated test receiver and integration tests before connecting n8n; no retry after unknown outcome without destination reconciliation.
4. Add durable dead-letter inspection, metrics, structured logs, and alerting.
5. Add restore drills and database migration tests.
6. Build a mobile-first control center only after authentication and authorization are production-grade.
7. Deploy behind HTTPS with secret management, rate limits, backups, monitoring and rollback; verify access from the user's real network/device.
8. Add agent/model integrations only behind explicit tool allowlists and approval gates.

## Not production-ready yet
No real external execution, model, browser, n8n workflow, identity provider, mobile UI, or deployment has been verified. Do not expose the current API publicly.
