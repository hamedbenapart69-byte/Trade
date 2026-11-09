"""Explicit live Telegram delivery proof."""
from __future__ import annotations

import logging

from telegram_bot import send_test_message_to_telegram

LOG = logging.getLogger("trader_me.force_test")


def main() -> int:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    try:
        message_id, link = send_test_message_to_telegram()
    except Exception:
        LOG.exception("FORCE_TEST_FAILED")
        return 1
    print(f"FORCE_TEST_MESSAGE_ID={message_id}", flush=True)
    print(f"FORCE_TEST_MESSAGE_LINK={link or 'UNAVAILABLE_PRIVATE_CHAT'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Delivery contract marker: this executable reports the Telegram API message_id after a real send succeeds.
