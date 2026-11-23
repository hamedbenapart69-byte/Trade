# Telegram Signal Sender

A strategy-independent delivery adapter. Any engine can create a JSON document
matching the example contract and invoke the sender without importing strategy
code.

## Run

Set environment variables (never commit them):

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Then run:

    python telegram_sender.py --signal examples/telegram_signal.example.json

The JSON chart field must point to an existing PNG/JPEG file or an HTTPS image
URL. The sender sends one Telegram sendPhoto message with a nine-section
caption. Telegram's photo caption limit is 1,024 characters; oversized captions
are rejected before sending.

## Contract

Required fields: signal_id, symbol, direction, timeframe, chart.

Recommended fields: status, generated_at, hypothesis, entry, stop_loss,
targets, risk_reward, confidence, calibration_status, invalidation.
levels.entry and levels.stop_loss are also accepted.

signal_id must be stable and unique for one logical signal. The payload is
hashed and stored with the ID in SQLite. A reused ID with changed payload is
rejected.

## Idempotency boundary

SQLite reservations prevent concurrent duplicate sends and suppress IDs already
marked SENDING, SENT, or UNKNOWN. Definite Telegram API rejections are marked
FAILED and may be retried. Network timeouts or lost responses become UNKNOWN
and are not retried automatically because Telegram may already have accepted
the message.

Telegram Bot API does not provide an idempotency key for sendPhoto; therefore
exactly-once delivery cannot be mathematically guaranteed across a process crash
between Telegram acceptance and local state update. Keep the SQLite database on
persistent storage. In ephemeral CI runners, mount/restore/persist this database
between runs before using the sender for production delivery.

The sender does not connect to exchange accounts, store exchange credentials,
or execute orders. It uses Python standard-library modules only.
