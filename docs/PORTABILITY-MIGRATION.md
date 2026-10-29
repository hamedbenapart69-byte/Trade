# Portability and Hosting Migration Runbook

Status: **planned and documented; not yet tested on an independently provisioned VPS**. See [EV-011](EVIDENCE-LEDGER.md#ev-011-hosting-portabilitymigration-path-is-documented-and-tested-using-docker-compose).

## Goal and portability boundary

Keep the application deployable without a Railway-specific runtime. The repository's Dockerfile, `compose.yaml`, SQLite database, and backup helper are the portability baseline. Avoid depending on a provider-specific database or persistent-volume feature. Do not claim a free VPS is guaranteed forever: free-tier eligibility, regional capacity, account verification, quotas, and policy can change.

## Candidate order

1. **Oracle Cloud Always Free VM**, if an eligible account can provision a supported VM in a suitable region. This is a candidate, not a guarantee of availability or permanent entitlement. Confirm current official limits and terms before migration.
2. **Other free VM offers** only after verifying current official terms, resource limits, persistence, outbound networking, account verification, and whether the VM can be retained without paid conversion.
3. **Low-cost VPS fallback** if no reliable free VM can be provisioned. Set an explicit monthly cap and alert before creating paid resources.

A free application host is not equivalent to an always-on VPS. Do not rely on a sleeping/free web service for a persistent worker or database unless its current documented behavior meets the requirements.

## Prerequisites

- Linux VM with Docker Engine and the Docker Compose plugin.
- SSH access using a dedicated key; firewall allows SSH only from trusted source IPs where feasible.
- A DNS name and TLS reverse proxy before public browser access.
- Sufficient disk for the live SQLite DB, one local backup, and one downloaded/off-host backup.
- Two independent high-entropy secrets for `CONTROL_API_TOKEN` and `WORKER_API_TOKEN`; keep them in a root-readable environment file or secret manager, never in Git.
- Confirm outbound HTTPS access to the required public provider from the intended host/network.

## First deployment drill (do not cut over production yet)

1. Provision a disposable VM and record provider, region, instance type, creation time, and applicable free-tier terms.
2. Install Docker/Compose from the OS vendor's supported repository. Clone the repository at an explicit immutable commit SHA.
3. Create a protected environment file outside the repository, set distinct tokens, and keep `ENABLE_WORKER_EXECUTION=false` and `ENABLE_N8N_EXECUTION=false` during initial validation.
4. Start the stack with `docker compose up -d --build`; verify `docker compose ps`, logs, and HTTP 200 from `/health`.
5. Confirm the API port remains bound to loopback as in `compose.yaml`. Configure TLS/reverse proxy and firewall separately before exposing the console; do not publish port 8000 directly.
6. Create a synthetic test run, inspect run/event/outbox behavior, and then remove only the synthetic test data through an explicitly reviewed procedure.
7. Run `python scripts/backup_db.py /var/lib/control/backup.db` in the container; copy the backup off the VM; record SHA-256 and `PRAGMA integrity_check`.
8. Restore that backup into an isolated disposable Compose project/volume. Compare counts for each actual table (including runs, events, and outbox where those tables exist), inspect application-level reads, and record before/after counts plus command output. Never restore over a live DB during the drill.
9. Reboot the disposable VM. Verify the container restarts, health returns, and test data persists. Verify that the external backup remains downloadable independently of the VM.
10. Store sanitized logs, exact commit SHA, Compose version, backup checksum, HTTP status, database counts, and restore output as CI or release artifacts. Update EV-011 only after all required checks pass.

## Cutover and rollback

1. Keep Railway available during the rehearsal; do not delete its volume or service.
2. Freeze writes to the old instance before taking the final consistent SQLite backup.
3. Verify the final backup checksum and restore it into the new host. Compare table counts and application reads before switching DNS or operator access.
4. Switch access only after TLS, authentication, firewall, backup, and restart checks pass. Enable the read-only market worker only after provider connectivity and idempotency behavior have been tested.
5. Monitor health, error logs, disk usage, provider quota, and backup completion. Retain the old deployment until the new instance has passed a defined observation window.
6. Roll back by disabling writes/workers on the new host and returning operator access to the old instance. Avoid running two writable instances against separate SQLite databases; that would fork state.
7. Keep at least one encrypted backup outside the VM and test restoring it periodically.

## Acceptance evidence for EV-011

- Public or privately accessible CI/release artifact with the tested commit SHA.
- Sanitized output proving Compose start, health HTTP 200, reboot persistence, backup checksum and integrity check.
- Isolated restore output with before/after counts for runs/events/outbox and application-level read check.
- Confirmation that no secret values were committed or included in logs.
- Explicit note of provider free-tier terms and the date those terms were checked.

Until those artifacts exist, EV-011 remains OPEN. A document or `docker compose config` passing in CI is not a live VPS migration test.
