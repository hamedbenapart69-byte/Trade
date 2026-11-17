# ADR-004 — Reliable Telegram Delivery

**Status:** PROPOSED — C++ L3 implementation present; live acceptance pending  
**Scope:** Telegram outbound reports, inbound commands and durable receipts

## Context
Telegram is the sole required user-facing channel. A successful HTTP request, local message construction or CI pass is not proof that a report reached the authorized chat.

## Decision
C++ L3 owns Telegram message construction, outbound delivery, inbound polling, retries, idempotency and receipt persistence. Python must not send Telegram messages.

### Outbound transactional outbox
1. Validate the immutable L2 artifact and its SHA-256 digest.
2. Construct messages only from permitted C10 states. Stage 1 must reject BUY_NOW and SELL_NOW because strategy and release gates are not yet authoritative in this slice.
3. Persist a stable logical message identity and payload fingerprint before sending.
4. Persist attempt count, status, HTTP status, Telegram message_id, error and update time.
5. Persist the final state after the response.

Allowed states:
- PENDING
- SENDING
- DELIVERED
- RETRYABLE_FAILURE
- PERMANENT_FAILURE
- DELIVERY_UNKNOWN

Retries are bounded and use backoff. HTTP 429 and server errors are retryable. Invalid requests are permanent failures. A timeout or malformed response after a possible send is DELIVERY_UNKNOWN and must not be blindly resent.

### Inbound updates
- Poll getUpdates from C++.
- Accept commands only from the configured authorized chat.
- Maintain a monotonic last_update_id and a durable processed-update ledger.
- Deduplicate update_id values.
- Unknown commands and unauthorized messages are recorded and ignored.
- Persist reply intent before sending a reply.

### Delivery semantics
Exactly-once Telegram delivery is not claimed. When Telegram may have accepted a message but the response was lost, the system records DELIVERY_UNKNOWN and requires reconciliation. Idempotency prevents duplicate logical sends where the persisted state proves the previous outcome.

## Current implementation
- C++ outbound and inbound executables exist.
- Durable JSON outbox/inbound state, retry bounds, message_id capture, authorized-chat filtering and update deduplication exist.
- Unit tests cover status classification, bounded retry, ambiguous states and command allowlist.
- Live outbound message_id and controlled inbound update evidence remain pending.
- State persistence on the signals branch is wired in the delivery workflow but has not been verified by a real L3 run.

## Acceptance
1. A real outbound report returns Telegram message_id and persisted DELIVERED state.
2. A timeout produces DELIVERY_UNKNOWN, not a false success.
3. Restart/replay does not duplicate a proven DELIVERED message.
4. A controlled authorized-chat update is processed once; replaying the same update_id does not repeat the effect.
5. Unauthorized chat updates produce no reply.
6. Outbox and inbound state survive runner termination and a subsequent run.

## Prohibitions
- No email or dashboard as a required signal channel.
- No message marked DELIVERED without Telegram API evidence.
- No exactly-once guarantee without proof.
- No actionable trade state from an unvalidated Stage 1 artifact.
