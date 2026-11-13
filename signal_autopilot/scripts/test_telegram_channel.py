#!/usr/bin/env python3
"""تأیید مقصد تلگرام؛ فقط کانال عمومی صحیح و ربات ادمین می‌تواند #TEST بگیرد."""
from __future__ import annotations
import asyncio, os, sys
from typing import Any
from telegram import Bot

def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()

def validate_target(configured_chat_id: str, chat: Any, member: Any, expected_title: str):
    actual_id=str(getattr(chat,"id",""))
    if not actual_id.startswith("-100"):
        return False,f"REJECTED_NOT_CHANNEL_ID chat_id={actual_id}"
    if str(getattr(chat,"type",""))!="channel":
        return False,f"REJECTED_CHAT_TYPE type={getattr(chat,'type','UNAVAILABLE')}"
    if _norm(getattr(chat,"title",""))!=_norm(expected_title):
        return False,f"REJECTED_CHANNEL_TITLE expected={expected_title!r} actual={getattr(chat,'title',None)!r}"
    if str(getattr(member,"status",""))!="administrator":
        return False,f"BOT_MUST_BE_CHANNEL_ADMIN status={getattr(member,'status','UNAVAILABLE')}"
    if getattr(member,"can_post_messages",None) is not True:
        return False,"BOT_ADMIN_CANNOT_POST_MESSAGES"
    if configured_chat_id.strip()!=actual_id:
        return False,f"CHAT_ID_RESOLUTION_MISMATCH configured={configured_chat_id!r} resolved={actual_id!r}"
    return True,(f"CHANNEL_VERIFIED chat_id={actual_id} type=channel title={chat.title!r} "
                 f"username=@{getattr(chat, 'username', None) or 'NO_PUBLIC_USERNAME'} bot_status=administrator")

async def run_check(send_test=True):
    token=os.environ.get("TELEGRAM_TOKEN","").strip()
    chat_id=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    expected=os.environ.get("TELEGRAM_EXPECTED_CHANNEL_TITLE","God signals crypto furthers").strip()
    if not token or not chat_id:
        print("TELEGRAM_CHANNEL_CHECK=FAILED reason=TELEGRAM_TOKEN_OR_CHAT_ID_MISSING")
        return 2
    async with Bot(token=token) as bot:
        me=await bot.get_me()
        print(f"BOT_ID={me.id} BOT_USERNAME=@{me.username or 'UNAVAILABLE'}")
        try: chat=await bot.get_chat(chat_id=chat_id)
        except Exception as exc:
            print(f"TELEGRAM_CHANNEL_CHECK=FAILED stage=getChat reason={type(exc).__name__}:{str(exc)[:180]}")
            return 3
        print(f"CHAT_RESOLVED chat_id={chat.id} type={chat.type} title={getattr(chat,'title',None)!r} username={getattr(chat,'username',None)!r}")
        if not str(chat.id).startswith("-100") or str(chat.type)!="channel" or not getattr(chat,"username",None):
            ok,detail=validate_target(chat_id,chat,None,expected)
            print(detail)
            return 5
        try: member=await bot.get_chat_member(chat_id=chat.id,user_id=me.id)
        except Exception as exc:
            print(f"TELEGRAM_CHANNEL_CHECK=FAILED stage=getChatMember reason={type(exc).__name__}:{str(exc)[:180]}")
            print("ACTION: ربات باید در کانال ادمین شود.")
            return 4
        ok,detail=validate_target(chat_id,chat,member,expected)
        print(detail)
        if not ok:
            if "BOT_MUST_BE_CHANNEL_ADMIN" in detail or "BOT_ADMIN_CANNOT_POST_MESSAGES" in detail:
                print("ACTION: ربات باید در کانال ادمین شود و مجوز ارسال پست داشته باشد.")
            return 5
        if send_test:
            message=await bot.send_message(
                chat_id=chat.id,
                text="#TEST\nTelegram destination verification only.\nNo trading signal and no order execution.",
                disable_web_page_preview=True,
            )
            print(f"TELEGRAM_TEST_MESSAGE=SENT chat_id={chat.id} message_id={message.message_id} link={(('https://t.me/' + chat.username + '/' + str(message.message_id)) if chat.username else 'NO_PUBLIC_PERMALINK')}")
    return 0

def main():
    return asyncio.run(run_check(send_test="--check-only" not in sys.argv[1:]))

if __name__=="__main__": raise SystemExit(main())
