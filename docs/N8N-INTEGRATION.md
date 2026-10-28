# n8n integration boundary

The `app/integrations/n8n.py` adapter is disabled by default, refuses external plain HTTP, disables redirects, bounds timeout to 1–30 seconds, supports a stable idempotency header and optional shared-token header, truncates response text, and never retries automatically. Tests use an in-memory HTTP mock only.

The API approval route does not dispatch to n8n. There is no durable outbox, worker queue, dead-letter queue, reconciliation, execution-ID persistence, or signed callback receiver. A successful webhook HTTP response does not prove downstream completion; the receiver must enforce idempotency itself.

Next milestone: explicit queued/dispatching/submitted/succeeded/failed/unknown states; transactional outbox; worker leases; reconciliation of uncertain outcomes; authenticated replay-protected callback or polling; crash/restart, duplicate delivery, stale lease, auth failure, timeout, and downstream failure tests. Keep outbound execution disabled in CI and development.
