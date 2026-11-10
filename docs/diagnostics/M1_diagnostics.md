# M1 Diagnostics — Telegram runtime probe

## Scope and evidence
- Repository: hamedbenapart69-byte/Trade
- Temporary probe workflow commit: 3e65c6c754a7c93715b4bc9e90433fd747905ba0
- Workflow run: https://github.com/hamedbenapart69-byte/Trade/actions/runs/42781075932
- Job ID: 129711006841
- Workflow deletion commit: 5af2715e310d143af6485012e72941eadebc205f
- Deletion verified: GitHub Contents API returned HTTP 404 for `.github/workflows/telegram_probe.yml`; recursive Git tree at deletion commit did not contain that path.

## Failure prediction / blast radius
Blast radius was limited to one temporary workflow, its three named Actions secrets, and Telegram destination chats. No signal-generation code or pipeline data was modified.

Predicted failure modes and observed evidence:
1. Invalid token — did not occur. Telegram `getMe` succeeded and returned bot `@GodTradingSignals_bot`, bot id `9277556863`.
2. Bot lacks admin rights — current destination returned `bot_status=member`, `bot_admin=false`. The response had `title=None`; chat type was not logged, so it is not proven to be a channel. Despite non-admin status, sending a message succeeded.
3. Wrong current Chat ID — not observed as an API failure: `getChat`, `getChatMember`, and `sendMessage` succeeded. The numeric ID is masked by GitHub Actions because it is a secret, so the exact numeric value is UNAVAILABLE in the log.
4. Rate limit — not observed in this one-message probe; no TelegramError was emitted. This does not prove rate limits will never occur.
5. GitHub Actions network blocked from Telegram API — did not occur for this run: `getMe` and `sendMessage` both succeeded from the hosted runner.

## Runtime output
- `PROBE_BOT: @GodTradingSignals_bot id=9277556863`
- `PROBE_CURRENT: title=None id=*** bot_status=member bot_admin=false`
- `PROBE_CURRENT_SEND: OK message_id=388`
- `PROBE_AUDIENCE: TELEGRAM_AUDIENCE_CHANNEL_ID=UNAVAILABLE`
- Workflow conclusion: success.

The probe script sent text in the form `PROBE CURRENT <UTC ISO timestamp>`. The exact timestamp was not printed in the job log and cannot be reconstructed exactly from the available evidence. No exact message body is claimed beyond that emitted template.

## Secret-name inventory limitation
Attempted GET:
`https://api.github.com/repos/hamedbenapart69-byte/Trade/actions/secrets`
The connected GitHub fetch tool rejected this sensitive endpoint with HTTP 400: `GitHub Fetch URL is not an allowed public GitHub repository or search endpoint.` Therefore a complete secret-name listing is UNAVAILABLE. Secret values were never retrieved or printed.

What the workflow proves:
- `TELEGRAM_TOKEN` was present and valid at runtime.
- `TELEGRAM_CHAT_ID` was present and accepted by Telegram.
- `TELEGRAM_AUDIENCE_CHANNEL_ID` was empty/unavailable in the workflow environment. This does not distinguish a missing secret from an explicitly empty secret.

## Root-cause assessment
The current destination is reachable and accepts messages, but its metadata does not establish that it is a channel: Telegram returned `title=None` and `bot_status=member`. It is therefore unsafe to report it as an admin-managed channel. The audience destination is not configured in the workflow environment, so dual-channel delivery is not currently verifiable.

## Rollback and cleanup
The temporary workflow was deleted in commit `5af2715e310d143af6485012e72941eadebc205f`. Verification:
- Contents lookup: HTTP 404 Not Found.
- Recursive Git tree: `telegram_probe.yml` absent.

## Post-probe self-check
1. No signal engine, LFS, NSS, thresholds, or test files changed.
2. Probe used actual GitHub Actions secrets; the bot identity and successful send are live API evidence, not mocks.
3. One successful send does not establish long-term delivery reliability or rate-limit behavior.
4. Chat ID redaction prevents disclosure of the exact numeric ID in the logs.
5. Audience channel cannot be identified or tested because its environment variable was empty.
6. No message retry or duplicate send was performed; the only confirmed message is message_id 388.

## Remaining watch items
- Confirm the actual type and identity of the current destination before describing it as a channel.
- Configure `TELEGRAM_AUDIENCE_CHANNEL_ID` in repository Actions secrets before dual-channel delivery.
- Add durable message_id persistence only after the delivery path is modified and tested.
- Secret inventory remains UNAVAILABLE through the current GitHub connector.
