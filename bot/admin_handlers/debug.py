# bot/admin_handlers/debug.py

import logging
from telebot import types
from bot.config import ADMIN_IDS
from bot.utils import escape_markdown
from bot.database import db

logger = logging.getLogger(__name__)

def register_debug_handlers(bot, scheduler):
    """ثبت هندلرهای مربوط به دیباگ و تست"""

    @bot.message_handler(commands=['test'], func=lambda message: message.from_user.id in ADMIN_IDS)
    async def run_all_scheduler_tests(message: types.Message):
        admin_id = message.from_user.id
        test_report = ["*⚙️ تست کامل سیستم زمان‌بندی ربات*"]
        msg = await bot.send_message(admin_id, "⏳ لطفاً صبر کنید، در حال اجرای تمام تست‌ها...", parse_mode="Markdown")

        async def run_single_test(title, function, *args, **kwargs):
            try:
                if not scheduler:
                    raise Exception("Scheduler not initialized.")
                
                # اجرای تابع (چه async باشد چه sync)
                if asyncio.iscoroutinefunction(function):
                    await function(*args, **kwargs)
                else:
                    function(*args, **kwargs)
                    
                test_report.append(f"✅ {title}: موفق")
            except Exception as e:
                test_report.append(f"❌ {title}: ناموفق\n   `خطا: {str(e)}`")
                logger.error(f"Error during '/test' for '{title}': {e}", exc_info=True)

        # اجرای تست‌ها
        import asyncio
        # مثال: await run_single_test("گزارش شبانه", scheduler._nightly_report, target_user_id=admin_id)
        # توجه: متدهای scheduler باید در دسترس باشند.
        
        await bot.edit_message_text("\n".join(test_report), chat_id=admin_id, message_id=msg.message_id, parse_mode="Markdown")

    @bot.message_handler(commands=['addpoints'], func=lambda message: message.from_user.id in ADMIN_IDS)
    async def add_points_command(message: types.Message):
        admin_id = message.from_user.id
        try:
            parts = message.text.split()
            if len(parts) < 2:
                await bot.reply_to(message, "فرمت: `/addpoints [USER_ID] AMOUNT`", parse_mode="MarkdownV2")
                return

            if len(parts) == 2:
                target_user_id = admin_id
                amount = int(parts[1])
            else:
                target_user_id = int(parts[1])
                amount = int(parts[2])

            await db.add_achievement_points(target_user_id, amount)
            await bot.send_message(admin_id, f"✅ *{amount}* امتیاز به `{target_user_id}` اضافه شد.", parse_mode="MarkdownV2")

        except Exception as e:
            await bot.send_message(admin_id, f"❌ خطا: `{escape_markdown(str(e))}`", parse_mode="MarkdownV2")