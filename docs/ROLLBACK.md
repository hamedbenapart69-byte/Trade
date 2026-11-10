# Rollback Plan — Trade

## Snapshot and recovery references

- Repository: `hamedbenapart69-byte/Trade`
- Default branch at audit start: `main`
- Baseline commit (full SHA): `af4a6e77b6ca2b0e78ecca7a48eb15b1a46ae688`
- Baseline snapshot branch: `baseline-pre-v9-tightening`
- Working branch: `stabilization/v9-hardening`
- The requested Git tag `baseline-pre-v9-tightening` was **not created**: the connected GitHub actions expose branch creation and ref updates, but no tag-creation operation. The baseline branch is a fallback pointer, not a Git tag.
- At audit time GitHub reports `main.protected=false`. Do not merge or push to `main` until protection is configured and verified.

## Preferred recovery: revert a bad merge

1. Identify the bad merge commit SHA and the affected PR.
2. For a normal merge commit, create a recovery branch from current `main` and run:
   `git revert -m 1 <merge_commit_sha>`
3. For a squash/rebase merge, revert the actual resulting commit(s) without `-m 1`.
4. Run the full required CI and inspect the resulting diff.
5. Open a PR to `main`; merge only after checks pass and a human review is recorded.

Do not assume every PR merge uses the same merge strategy. Inspect the commit graph first.

## Emergency reset to the baseline

Preferred safe method:
- Create a recovery branch from `baseline-pre-v9-tightening`.
- Open a PR that restores the desired baseline state, preserving the current main history.

The destructive alternative is a hard reset and force push:
```bash
git fetch origin
git switch main
git reset --hard af4a6e77b6ca2b0e78ecca7a48eb15b1a46ae688
git push --force-with-lease origin main
```
This is **not an ordinary rollback procedure**. It rewrites shared history, may be rejected by branch protection, and can discard other people's commits. Do not execute it unless the repository owner explicitly authorizes the emergency, confirms the exact target SHA, and coordinates all collaborators. Never use plain `--force`.

## Reverting a failed PR after merge

- Record the PR number, merge method, merge commit SHA, and CI run.
- Prefer GitHub's revert-PR action when available, or create a recovery branch and use `git revert`.
- For a merge commit use `git revert -m 1 <merge_sha>`; for squash commits use `git revert <squash_sha>`.
- Resolve conflicts manually, run tests, then submit a revert PR.
- Never delete the original PR or erase its failed validation evidence.

## Access control ownership

Only the repository owner / organization administrators can change collaborator permissions and repository rules:
- Add collaborators through GitHub repository Settings → Collaborators and teams.
- Grant the minimum required role: Read, Triage, Write, Maintain, or Admin.
- Remove access through the same settings page.
- Keep Admin limited to trusted owners. Do not grant Admin merely to bypass branch protection.
- Require PR review and status checks on `main`; enforce rules for administrators; disable force pushes and branch deletion.

## Incident response

### Main branch broken
1. Stop merges and deployments.
2. Identify the last known-good SHA and the triggering PR.
3. Revert via a PR; use emergency reset only under the explicit owner approval described above.
4. Verify CI and inspect the live dashboard before resuming schedules.

### CI failure or false-green suspicion
1. Treat the run as untrusted; do not merge based on workflow conclusion alone.
2. Inspect every job and step conclusion, including skipped and continue-on-error steps.
3. Confirm the test runner collected and executed a nonzero number of tests.
4. Re-run only after the root cause is understood; preserve the original run and logs.

### Telegram delivery failure
1. Keep the signal payload published with delivery status marked degraded/unavailable.
2. Verify bot token presence without printing its value, chat ID, bot membership and channel permissions.
3. Send a controlled test only to an explicitly configured destination.
4. Do not claim delivery from a green pipeline; require Telegram API message IDs.

### Activepieces failure
1. Do not let an Activepieces flow override the canonical GitHub pipeline.
2. Preserve the last known-good run and error details.
3. Disable only the failing flow if it causes repeated errors or duplicate notifications.
4. Restore after a controlled test; do not delete run history.

## Safety invariants

- Public market data only; no exchange account credentials or trading API keys.
- Manual trading only; no order placement.
- No merge to `main` before branch protection is active and verified.
- No deployment claim without a verified deployment and health check.
- No strategy-performance claim without valid chronological OOS evidence.
