"""آزمون‌های اعتبارسنجی مقصد تلگرام."""
import importlib.util, unittest, os
from unittest.mock import AsyncMock, patch
from pathlib import Path
from types import SimpleNamespace
from telegram_bot import _verified_channel
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"test_telegram_channel.py"
SPEC=importlib.util.spec_from_file_location("telegram_channel_check",SCRIPT)
MODULE=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
validate_target=MODULE.validate_target

def chat(chat_id=-1001234567890,chat_type="channel",title="God signals crypto furthers",username="god_signals_crypto"):
    return SimpleNamespace(id=chat_id,type=chat_type,title=title,username=username)
def admin(status="administrator",can_post_messages=True):
    return SimpleNamespace(status=status,can_post_messages=can_post_messages)

class TelegramChannelTests(unittest.TestCase):
    def test_accepts_verified_public_channel(self):
        ok,detail=validate_target("-1001234567890",chat(),admin(),"God signals crypto furthers")
        self.assertTrue(ok); self.assertIn("CHANNEL_VERIFIED",detail)
    def test_rejects_private_dm(self):
        ok,detail=validate_target("123456789",chat(123456789,"private"),admin(),"God signals crypto furthers")
        self.assertFalse(ok); self.assertIn("REJECTED_NOT_CHANNEL_ID",detail)
    def test_rejects_group(self):
        ok,detail=validate_target("-1001234567890",chat(chat_type="supergroup"),admin(),"God signals crypto furthers")
        self.assertFalse(ok); self.assertIn("REJECTED_CHAT_TYPE",detail)
    def test_requires_admin(self):
        ok,detail=validate_target("-1001234567890",chat(),admin("member"),"God signals crypto furthers")
        self.assertFalse(ok); self.assertIn("BOT_MUST_BE_CHANNEL_ADMIN",detail)
    def test_requires_post_permission(self):
        ok,detail=validate_target("-1001234567890",chat(),admin(can_post_messages=False),"God signals crypto furthers")
        self.assertFalse(ok); self.assertIn("BOT_ADMIN_CANNOT_POST_MESSAGES",detail)
    def test_channel_without_public_username_is_still_a_channel(self):
        ok,detail=validate_target("-1001234567890",chat(username=None),admin(),"God signals crypto furthers")
        self.assertTrue(ok); self.assertIn("CHANNEL_VERIFIED",detail)
    def test_requires_exact_public_channel_title(self):
        ok,detail=validate_target("-1001234567890",chat(title="Different"),admin(),"God signals crypto furthers")
        self.assertFalse(ok); self.assertIn("REJECTED_CHANNEL_TITLE",detail)



class ProductionTelegramGuardTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self, target=None, member=None):
        target = target or chat(username=None)
        member = member or admin()
        return SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=9277556863, username="GodTradingSignals_bot")),
            get_chat=AsyncMock(return_value=target),
            get_chat_member=AsyncMock(return_value=member),
        )

    async def test_production_guard_accepts_verified_private_channel(self):
        bot = self.make_bot(chat(username=None))
        with patch.dict(os.environ, {"TELEGRAM_EXPECTED_CHANNEL_TITLE": "God signals crypto furthers"}):
            resolved, identity = await _verified_channel(bot, "-1001234567890")
        self.assertEqual(resolved.id, -1001234567890)
        self.assertIsNone(resolved.username)
        bot.get_chat_member.assert_awaited_once_with(chat_id=resolved.id, user_id=identity.id)

    async def test_production_guard_rejects_chat_id_mismatch(self):
        bot = self.make_bot(chat(chat_id=-1009999999999, username=None))
        with self.assertRaisesRegex(RuntimeError, "CHAT_ID_RESOLUTION_MISMATCH"):
            await _verified_channel(bot, "-1001234567890")

    async def test_production_guard_rejects_non_channel(self):
        bot = self.make_bot(chat(chat_type="supergroup", username=None))
        with self.assertRaisesRegex(RuntimeError, "REJECTED_CHAT_TYPE"):
            await _verified_channel(bot, "-1001234567890")

    async def test_production_guard_rejects_wrong_title(self):
        bot = self.make_bot(chat(title="Wrong channel", username=None))
        with self.assertRaisesRegex(RuntimeError, "TITLE_MISMATCH"):
            await _verified_channel(bot, "-1001234567890")

    async def test_production_guard_requires_admin(self):
        bot = self.make_bot(chat(username=None), admin(status="member"))
        with self.assertRaisesRegex(RuntimeError, "NOT_CHANNEL_ADMIN"):
            await _verified_channel(bot, "-1001234567890")

    async def test_production_guard_requires_post_permission(self):
        bot = self.make_bot(chat(username=None), admin(can_post_messages=False))
        with self.assertRaisesRegex(RuntimeError, "CANNOT_POST_MESSAGES"):
            await _verified_channel(bot, "-1001234567890")


if __name__=="__main__": unittest.main(verbosity=2)
