# Operations runbook

## First local start

1. Copy .env.example to .env.
2. Replace CONTROL_API_TOKEN and WORKER_API_TOKEN with two different random values. Generate each with:
   python -c "import secrets; print(secrets.token_urlsafe(32))"
3. Keep ENABLE_WORKER_EXECUTION=false and ENABLE_N8N_EXECUTION=false until a real destination is configured and authorized.
4. Start: docker compose up -d --build
5. Open http://127.0.0.1:8000 on the same computer. This localhost binding is intentional; it is not reachable from the public internet or another device by default.
6. Check: docker compose ps and docker compose logs --tail=100 control-plane.

## Backup

The helper creates a consistent SQLite backup using SQLite's backup API and verifies PRAGMA integrity_check.

```bash
docker compose exec -T control-plane python scripts/backup_db.py /var/lib/control/backup.db
docker cp "$(docker compose ps -q control-plane)":/var/lib/control/backup.db ./control-backup.db
```

Store the backup outside the server/container as well. A backup in the same volume is not disaster recovery.

## Restore

Stop the service before replacing the active database. Keep an additional copy of the current database before restoring.

```bash
docker compose stop control-plane
docker compose run --rm -v "$PWD:/restore:ro" --entrypoint sh control-plane -c 'python -c "import sqlite3,sys; c=sqlite3.connect(\"/restore/control-backup.db\"); print(c.execute(\"PRAGMA integrity_check\").fetchone()[0]); c.close()" && cp /restore/control-backup.db /var/lib/control/control.db'
docker compose up -d control-plane
docker compose logs --tail=100 control-plane
```

The restore command assumes the backup file is named control-backup.db in the current directory. Verify the console, run history, audit events, and outbox state after restoring. Do not restore a backup over a live database.

## Worker and external delivery

The worker is a one-shot command, not an always-running daemon. It remains disabled unless ENABLE_WORKER_EXECUTION=true and WORKER_ALLOWED_WORKFLOWS explicitly lists a registered workflow. Run it only from a trusted environment with the worker token and after the destination has been tested:

```bash
python worker.py
```

N8N execution separately requires ENABLE_N8N_EXECUTION=true, N8N_WEBHOOK_URL and destination authentication. A timeout leaves the item uncertain; do not retry until the destination outcome is checked.

## Public hosting gate

Do not expose this service directly. Before hosting, implement production identity and role-based authorization, rate limiting and origin controls, TLS, secret management, persistent storage, external backup storage, monitoring, and a real-device connectivity test. No hosting provider or public deployment has been verified yet.
