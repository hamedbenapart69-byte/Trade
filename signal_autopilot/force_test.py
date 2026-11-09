"""Explicit live Telegram delivery proof. Sends one clearly marked test message."""
from __future__ import annotations

import asyncio
import logging
import os
from telegram import Bot

LOG = logging.getLogger("trader_me.force_test")


async def _send(token: str, chat_id: str) -> tuple[int, str | None]:
    async with Bot(token=token) as bot:
        chat = await bot.get_chat(chat_id=chat_id)
        message = await bot.send_message(
            chat_id=chat_id,
            text=(
                "[TEST MODE] Trader_me Telegram delivery verification\n"
                "This is a transport test, not a trading signal.\n"
                "Stage: 1B | timeframe: 15m"
            ),
            disable_web_page_preview=True,
        )
        username = getattr(chat, "username", None)
        link = f"https://t.me/{username}/{message.message_id}" if username else None
        LOG.info("FORCE_TEST_SENT message_id=%s chat_id=%s message_link=%s",
                 message.message_id, chat.id, link or "UNAVAILABLE_PRIVATE_CHAT")
        return int(message.message_id), link


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOG.error("FORCE_TEST_ABORTED: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing")
        return 2
    try:
        message_id, link = asyncio.run(_send(token, chat_id))
    except Exception:
        LOG.exception("FORCE_TEST_FAILED")
        return 1
    print(f"FORCE_TEST_MESSAGE_ID={message_id}", flush=True)
    print(f"FORCE_TEST_MESSAGE_LINK={link or 'UNAVAILABLE_PRIVATE_CHAT'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
