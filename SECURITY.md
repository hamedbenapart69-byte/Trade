# Security policy

## Supported deployment state
This repository is an actively developed foundation. Do not expose it directly to the public internet until the production release gates in docs/ROADMAP.md and docs/OPERATIONS.md are met.

## Reporting
Do not publish secrets, tokens, personal data, or exploitable details in public issues. Rotate any credential that may have been exposed. For a private report, use GitHub's private vulnerability reporting feature if it is enabled for this repository.

## Secret handling
- Never commit real credentials, .env files, database files, or backups.
- Treat any token pasted into a chat, issue, log, or commit as exposed and revoke it.
- Keep operator and worker credentials separate.
