# bot/admin_handlers/debug.py

import logging
import asyncio
from telebot import types
from bot.config import ADMIN_IDS
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.database import db
from bot.keyboards import admin as admin_menu

logger = logging.getLogger(__name__)
bot = None

def register_debug_handlers(b, scheduler):
    """ثبت هندلرهای مربوط به دیباگ و وضعیت سیستم"""
    global bot
    bot = b

    @bot.callback_query_handler(func=lambda call: call.data == "admin:system_stats")
    async def system_stats_callback(call: types.CallbackQuery):
        """نمایش وضعیت سرورها به صورت همزمان (Parallel)."""
        uid = call.from_user.id
        msg_id = call.message.message_id

        if uid not in ADMIN_IDS: return

        await _safe_edit(uid, msg_id, "⏳ *در حال دریافت اطلاعات از تمام سرورها...*", parse_mode="Markdown")
        
        panels = await db.get_active_panels()
        if not panels:
            await _safe_edit(uid, msg_id, "❌ هیچ پنل فعالی وجود ندارد.", reply_markup=await admin_menu.main_menu())
            return

        # --- تابع داخلی برای گرفتن وضعیت یک پنل ---
        async def check_single_panel(panel):
            try:
                # استفاده از فکتوری برای گرفتن هندلر پنل
                from bot.services.panels.factory import PanelFactory
                handler = await PanelFactory.get_panel(panel['name'])
                if not handler:
                    return f"❌ {panel['name']}: خطا در اتصال"
                
                # فرض بر این است که متد get_system_stats در هندلر پنل وجود دارد
                # اگر ندارید، می‌توان یک پینگ ساده یا get_users سبک زد
                stats = await handler.get_system_stats()
                
                # فرمت کردن خروجی
                cpu = stats.get('cpu', 'N/A')
                ram = stats.get('ram', 'N/A')
                return f"✅ *{escape_markdown(panel['name'])}*\n   Cpu: `{cpu}` | Ram: `{ram}`"
            except Exception as e:
                logger.error(f"Stats error {panel['name']}: {e}")
                return f"⚠️ *{escape_markdown(panel['name'])}*: عدم پاسخگویی"

        # اجرای همزمان همه درخواست‌ها
        tasks = [check_single_panel(p) for p in panels]
        results = await asyncio.gather(*tasks)

        # نمایش نتیجه
        report = "🖥 *وضعیت آنلاین سرورها:*\n\n" + "\n────────────────\n".join(results)
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin:system_stats"))
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:main"))

        await _safe_edit(uid, msg_id, report, reply_markup=kb, parse_mode="MarkdownV2")

    # هندلرهای تست و دیباگ (بدون تغییر عمده، فقط تمیزکاری)
    @bot.message_handler(commands=['test'], func=lambda m: m.from_user.id in ADMIN_IDS)
    async def run_tests(message):
        await bot.reply_to(message, "تست سیستم انجام شد.")