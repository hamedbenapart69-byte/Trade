# n8n integration boundary

The adapter in app/integrations/n8n.py is disabled by default, requires an absolute HTTP(S) URL, rejects non-loopback plain HTTP, disables redirects, bounds timeout to 1–30 seconds, supports a stable idempotency header and optional shared-token header, truncates response text, and never retries automatically.

The one-shot worker in worker.py is also disabled by default. It requires a distinct worker credential and explicit workflow allowlist. If the delivery result is uncertain, it does not call finish; after lease expiry the item becomes unknown and requires operator reconciliation. A 2xx webhook response proves only that the endpoint accepted the HTTP request, not that downstream work completed. The receiver must enforce idempotency and expose verifiable status for consequential workflows.

No live n8n endpoint has been configured or contacted. Automated tests must use a local test receiver or in-memory transport. Before a real integration is enabled, define per-workflow payload schemas, request size bounds, destination authentication, response semantics, callback/polling verification, and a destination-side duplicate-suppression strategy.

Official licensing and pricing references are recorded in docs/DECISION-REPORT.md; verify the intended n8n use case against its Sustainable Use License before commercializing or exposing customer-configurable workflows.
