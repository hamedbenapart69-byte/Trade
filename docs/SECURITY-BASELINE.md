# Security baseline

- Operator routes require `CONTROL_API_TOKEN`; worker lease/finish routes require a distinct `WORKER_API_TOKEN`. Both must be at least 24 characters; missing configuration fails closed.
- Never reuse the operator token for a worker. The worker credential cannot approve, reject, create, queue, or reconcile runs.
- Never embed the API token in frontend code or commit it to Git.
- Bind to localhost for initial development. Do not expose publicly before HTTPS, identity/authZ, rate limits, secret management, and monitoring are implemented.
- Run inputs are untrusted data, are capped at 32 KiB per request, and are not executed as code or passed to models/tools by this starter.
- Human approval records a decision only; it does not execute the requested action.
- Idempotency keys cannot be reused for a different workflow/input pair and are not returned by the API.
- Database and environment files are ignored by Git.
- Cancellation applies only to runs awaiting approval; it does not claim an external worker was terminated.
- Backups use SQLite's backup API and run an integrity check.
- Worker execution results record provider/status metadata only; raw downstream response bodies are not persisted to reduce accidental secret/data leakage.
- HTTP access logs record request ID, method, path, status and duration only; query strings, headers, bodies, API keys and downstream response content are excluded.
- Expired worker leases transition to `unknown`, never directly back to `queued`: the worker may have performed a side effect before crashing.
- An operator must verify the destination outcome before explicitly reconciling an `unknown` item with `retry` or `fail`. Retrying without checking can duplicate external actions.
- Before production, separate worker credentials from owner/operator credentials and implement role-based authorization, a secrets manager, backup/restore tests, access audit, request-size limits, retention policy, monitoring, and security review.
