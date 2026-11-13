#!/usr/bin/env python3
"""تأیید کانال تلگرام با ثبت پاسخ دقیق getChatMember؛ ارسال فقط پس از PASS."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from telegram import Bot


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _json_line(label: str, payload: Any) -> None:
    print(label + "=" + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def validate_target(configured_chat_id: str, chat: Any, member: Any, expected_title: str):
    actual_id = str(getattr(chat, "id", ""))
    if not actual_id.startswith("-100"):
        return False, f"REJECTED_NOT_CHANNEL_ID chat_id={actual_id}"
    if str(getattr(chat, "type", "")) != "channel":
        return False, f"REJECTED_CHAT_TYPE type={getattr(chat, 'type', 'UNAVAILABLE')}"
    if _norm(getattr(chat, "title", "")) != _norm(expected_title):
        return False, (
            f"REJECTED_CHANNEL_TITLE expected={expected_title!r} "
            f"actual={getattr(chat, 'title', None)!r}"
        )
    if member is None:
        return False, "BOT_ADMIN_STATUS_UNAVAILABLE"
    status = str(getattr(member, "status", "UNAVAILABLE"))
    if status != "administrator":
        return False, f"BOT_MUST_BE_CHANNEL_ADMIN status={status}"
    if getattr(member, "can_post_messages", None) is not True:
        return False, "BOT_ADMIN_CANNOT_POST_MESSAGES"
    if configured_chat_id.strip() != actual_id:
        return False, f"CHAT_ID_RESOLUTION_MISMATCH configured={configured_chat_id!r} resolved={actual_id!r}"
    return True, (
        f"CHANNEL_VERIFIED chat_id={actual_id} type=channel title={chat.title!r} "
        f"username=@{getattr(chat, 'username', None) or 'NO_PUBLIC_USERNAME'} "
        "bot_status=administrator can_post_messages=true"
    )


async def run_check(send_test: bool = True) -> int:
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    expected = os.environ.get(
        "TELEGRAM_EXPECTED_CHANNEL_TITLE", "God signals crypto furthers"
    ).strip()
    if not token or not chat_id:
        print("TELEGRAM_CHANNEL_CHECK=FAILED reason=TELEGRAM_TOKEN_OR_CHAT_ID_MISSING")
        return 2

    async with Bot(token=token) as bot:
        try:
            me = await bot.get_me()
        except Exception as exc:
            _json_line("GET_ME_ERROR_JSON", {
                "exception_type": type(exc).__name__,
                "description": str(exc),
            })
            return 3

        print(f"BOT_TOKEN_IDENTITY id={me.id} username=@{me.username or 'UNAVAILABLE'}")

        try:
            chat = await bot.get_chat(chat_id=chat_id)
        except Exception as exc:
            _json_line("GET_CHAT_ERROR_JSON", {
                "exception_type": type(exc).__name__,
                "description": str(exc),
            })
            print(f"TELEGRAM_CHANNEL_CHECK=FAILED stage=getChat error={type(exc).__name__}")
            return 3

        print(
            f"CHAT_RESOLVED chat_id={chat.id} type={chat.type} "
            f"title={getattr(chat, 'title', None)!r} "
            f"username={getattr(chat, 'username', None)!r}"
        )

        if not str(chat.id).startswith("-100") or str(chat.type) != "channel":
            ok, detail = validate_target(chat_id, chat, None, expected)
            print(detail)
            return 5

        try:
            member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
            # نسخهٔ JSON شیء برگشتی از پاسخ Bot API؛ شامل status و can_post_messages.
            _json_line("GET_CHAT_MEMBER_RESPONSE_JSON", member.to_dict())
        except Exception as exc:
            error_payload = {
                "exception_type": type(exc).__name__,
                "error_code": getattr(exc, "code", None),
                "description": getattr(exc, "message", str(exc)),
            }
            _json_line("GET_CHAT_MEMBER_ERROR_JSON", error_payload)
            error_text = str(getattr(exc, "message", str(exc))).casefold()
            if "user not found" in error_text:
                print(
                    "ERROR: The bot token may belong to a different bot than the one "
                    "added as admin. Check bot usernames."
                )
            else:
                print(
                    "ERROR: Telegram getChatMember failed. Confirm this exact bot "
                    "is a channel administrator and retry after Telegram updates."
                )
            return 4

        ok, detail = validate_target(chat_id, chat, member, expected)
        print(detail)
        if not ok:
            if "BOT_MUST_BE_CHANNEL_ADMIN" in detail:
                print(
                    "ACTION: Add the bot identified above (same numeric bot ID) "
                    "as a channel administrator."
                )
            elif "BOT_ADMIN_CANNOT_POST_MESSAGES" in detail:
                print("ACTION: Enable the channel administrator permission 'Post Messages'.")
            return 5

        if send_test:
            message = await bot.send_message(
                chat_id=chat.id,
                text=(
                    "#TEST\nTelegram destination verification only.\n"
                    "No trading signal and no order execution."
                ),
                disable_web_page_preview=True,
            )
            username = getattr(chat, "username", None)
            link = (
                f"https://t.me/{username}/{message.message_id}"
                if username else "NO_PUBLIC_PERMALINK"
            )
            print(
                f"TELEGRAM_TEST_MESSAGE=SENT chat_id={chat.id} "
                f"message_id={message.message_id} link={link}"
            )
        else:
            print("TELEGRAM_TEST_MESSAGE=SKIPPED check_only=true")
    return 0


def main() -> int:
    return asyncio.run(run_check(send_test="--check-only" not in sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
