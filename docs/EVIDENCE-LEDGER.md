# Evidence Ledger

Rule: a row is PASS only when its linked artifact directly supports the claim. A public URL alone is not proof of a complete workflow. Do not put tokens, API keys, cookies, or private customer data in evidence.

| ID | Claim / acceptance criteria | Status | Artifact(s) | Remaining work |
|---|---|---|---|---|
| EV-001 | Unit/API CI suite passes on current main | PASS (CI only) | [CI run 40805583810](https://github.com/hamedbenapart69-byte/Trade/actions/runs/40805583810); [test suite](../tests/) | This does not prove hosted E2E behavior. Reconfirm on every new commit. |
| EV-002 | Docker image builds and container health smoke test passes in CI | PASS (CI only) | [CI run 40805583810](https://github.com/hamedbenapart69-byte/Trade/actions/runs/40805583810); [CI workflow](../.github/workflows/ci.yml) | Does not prove the production deployment runs this image. |
| EV-003 | Hosted health endpoint responds | OPEN | [Production /health](https://control-plane-v2-production-8d31.up.railway.app/health) | Record timestamp, HTTP status, response body and headers from a fresh command-line check. |
| EV-004 | Railway deployed SHA equals GitHub main HEAD; production CSP exists; /health returns HTTP 200 | BLOCKED | [GitHub HEAD commit](https://github.com/hamedbenapart69-byte/Trade/commit/d6f748b545f08fb8327e0c72d75db414de31b6f5); [health endpoint](https://control-plane-v2-production-8d31.up.railway.app/health) | Current health response does not include a commit SHA. Railway GitHub-source connection previously failed with a repository-access error; authenticated Railway project operations are unavailable in this session. Need deploy evidence with SHA, `curl -I` CSP output, and `curl -sS -o /dev/null -w '%{http_code}' .../health` output. |
| EV-005 | Hosted authenticated `market.snapshot` reaches the real CoinGecko provider and persists the run | OPEN | [Online console](https://control-plane-v2-production-8d31.up.railway.app/); [CoinGecko integration source](../app/integrations/coingecko.py); [worker source](../worker.py) | Capture request/run ID, sanitized real provider response, corresponding database row(s), timestamps and HTTP result. No live hosted run is claimed yet. |
| EV-006 | Expired lease becomes `unknown` and requires reconciliation | OPEN | [Outbox tests](../tests/test_outbox.py); [worker tests](../tests/test_worker.py) | Attach the exact CI run/job and test case output that proves the claim. |
| EV-007 | Operator and worker credentials are separate and missing credentials fail closed | OPEN | [API tests](../tests/test_api.py); [worker tests](../tests/test_worker.py); [security baseline](SECURITY-BASELINE.md) | Attach exact CI run/job and test output; do not expose credential values. |
| EV-008 | Backup of hosted DB restores in an isolated target with matching row counts and integrity check | OPEN | [Backup helper](../scripts/backup_db.py); [backup tests](../tests/test_backup.py); [operations runbook](OPERATIONS.md) | Run against the real host; record backup checksum, before/after counts for runs/events/outbox, isolated restore output and `PRAGMA integrity_check=ok`. No hosted restore is claimed. |
| EV-009 | Provider usage/cost quota ledger enforces daily cap and stops work at exhaustion | OPEN | [Roadmap](ROADMAP.md) | Implementation and tests are not evidenced. Record provider-call counts, configured cap, exhaustion result and CI artifact after implementation. |
| EV-010 | Failure alert is sent to the owner through Telegram with rate limiting and a message ID | OPEN | [Roadmap](ROADMAP.md) | Implementation and live delivery are not evidenced. Record sanitized event, Telegram message ID and CI/test artifact; never store bot token or chat secrets here. |
| EV-011 | Hosting portability/migration path is documented and tested using Docker Compose | OPEN | [Migration runbook](PORTABILITY-MIGRATION.md); [Compose file](../compose.yaml); [Compose validation in CI](../.github/workflows/ci.yml) | Documentation is present, but no independent VPS provisioning, live restore or cutover test has occurred. Complete a disposable-host drill and attach sanitized output before PASS. |

## Evidence handling

- Preserve the raw output in a non-secret artifact and link it from the relevant row.
- Redact authorization headers, tokens, session cookies, private keys, and sensitive database values before uploading logs.
- If a provider or credential prevents a test, keep the row BLOCKED/OPEN and record the exact error and next required action.
- A passing unit test, CI build, reachable health URL, or written runbook must not be described as proof of a live hosted end-to-end workflow.
