# Security baseline

- Operational routes require a configured API token of at least 24 characters; missing configuration fails closed.
- Never embed the API token in frontend code or commit it to Git.
- Bind to localhost for initial development. Do not expose publicly before HTTPS, identity/authZ, rate limits, secret management, and monitoring are implemented.
- Run inputs are untrusted data and are not executed as code or passed to models/tools by this starter.
- Human approval records a decision only; it does not execute the requested action.
- Idempotency keys cannot be reused for a different workflow/input pair and are not returned by the API.
- Database and environment files are ignored by Git.
- Cancellation applies only to runs awaiting approval; it does not claim an external worker was terminated.
- Backups use SQLite's backup API and run an integrity check.
- Production needs a secrets manager, backups/restore tests, access audit, request-size limits, retention policy, and security review.
