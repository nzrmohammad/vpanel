# bot/admin_handlers/backup.py

import os
import logging
import asyncio
import aiofiles
from datetime import datetime
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import admin_menu

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

@bot.callback_query_handler(func=lambda call: call.data == "admin:backup_menu")
async def backup_menu_handler(call: types.CallbackQuery):
    await bot.edit_message_text(
        "💾 <b>منوی پشتیبان‌گیری</b>",
        call.from_user.id,
        call.message.message_id,
        reply_markup=admin_menu.backup_selection_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin:backup:bot_db")
async def backup_bot_db(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "📦 در حال تهیه بکاپ...")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    # فقط بکاپ پستگرس (طبق درخواست قبلی شما)
    if DATABASE_URL:
        await backup_postgres_secure(call, timestamp)
    else:
        await bot.send_message(call.from_user.id, "❌ کانکشن استرینگ دیتابیس یافت نشد.")

async def backup_postgres_secure(call: types.CallbackQuery, timestamp: str):
    """بکاپ‌گیری امن از Postgres بدون استفاده از Shell=True"""
    filename = f"pg_backup_{timestamp}.sql"
    
    # اصلاح URL برای استفاده در pg_dump
    # اگر از درایور asyncpg استفاده شده، باید برای pg_dump تمیز شود
    pg_url_clean = DATABASE_URL.replace("+asyncpg", "")
    
    try:
        # --- تغییر مهم: استفاده از لیست آرگومان‌ها به جای رشته متنی ---
        # این روش امن است و اجازه تزریق دستور را نمی‌دهد
        cmd_args = ["pg_dump", "--dbname", pg_url_clean, "-f", filename]
        
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"Postgres backup failed: {error_msg}")
            await bot.send_message(call.from_user.id, f"❌ خطا در بکاپ‌گیری:\n{error_msg}")
            return

        # ارسال فایل
        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()

        await bot.send_document(
            chat_id=call.from_user.id,
            document=file_data,
            visible_file_name=filename,
            caption=f"🐘 <b>بکاپ امن PostgreSQL</b>\n📅 {timestamp}",
            parse_mode='HTML'
        )
        
        # حذف فایل
        os.remove(filename)

    except FileNotFoundError:
        await bot.send_message(call.from_user.id, "❌ دستور pg_dump در سرور پیدا نشد. لطفاً postgresql-client را نصب کنید.")
    except Exception as e:
        logger.error(f"Error in backup: {e}", exc_info=True)
        await bot.send_message(call.from_user.id, "❌ خطای سیستمی.")