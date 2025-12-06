# bot/admin_handlers/backup.py

import os
import logging
import asyncio
import aiofiles
import json
from datetime import datetime
from telebot import types
from sqlalchemy import select

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import Panel, UserUUID

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

@bot.callback_query_handler(func=lambda call: call.data == "admin:backup_menu")
async def backup_menu_handler(call: types.CallbackQuery):
    """نمایش منوی انتخاب نوع بکاپ"""
    await bot.edit_message_text(
        "💾 <b>منوی پشتیبان‌گیری</b>\n\nلطفاً نوع داده‌ای که می‌خواهید بکاپ بگیرید را انتخاب کنید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=admin_menu.backup_selection_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin:backup:bot_db")
async def backup_bot_db(call: types.CallbackQuery):
    """بکاپ‌گیری کامل از دیتابیس Postgres"""
    await bot.answer_callback_query(call.id, "📦 در حال تهیه بکاپ دیتابیس...", show_alert=False)
    await bot.send_chat_action(call.from_user.id, 'upload_document')
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    if DATABASE_URL:
        await _backup_postgres_secure(call, timestamp)
    else:
        await bot.send_message(call.from_user.id, "❌ کانکشن استرینگ دیتابیس (DATABASE_URL) تنظیم نشده است.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:backup:"))
async def backup_panel_data(call: types.CallbackQuery):
    """بکاپ‌گیری از داده‌های مربوط به پنل‌ها (خروجی JSON)"""
    panel_type = call.data.split(":")[2]  # hiddify or marzban
    
    await bot.answer_callback_query(call.id, f"📦 در حال استخراج داده‌های {panel_type}...", show_alert=False)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"{panel_type}_users_backup_{timestamp}.json"
    
    try:
        async with db.get_session() as session:
            # دریافت کاربرانی که در پنل‌های این نوع هستند
            stmt = (
                select(UserUUID)
                .join(UserUUID.allowed_panels)
                .where(Panel.panel_type == panel_type)
            )
            result = await session.execute(stmt)
            users = result.scalars().all()
            
            export_data = []
            for u in users:
                export_data.append({
                    "uuid": str(u.uuid),
                    "name": u.name,
                    "is_active": u.is_active,
                    "created_at": str(u.created_at),
                    "is_vip": u.is_vip
                })
        
        if not export_data:
            await bot.send_message(call.from_user.id, f"⚠️ هیچ کاربری برای پنل‌های {panel_type} یافت نشد.")
            return

        # نوشتن فایل JSON
        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(export_data, ensure_ascii=False, indent=2))

        # ارسال فایل
        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()
            
        await bot.send_document(
            chat_id=call.from_user.id,
            document=file_data,
            visible_file_name=filename,
            caption=f"🗂 <b>بکاپ کاربران {panel_type.capitalize()}</b>\n📅 {timestamp}\n👥 تعداد: {len(export_data)}",
            parse_mode='HTML'
        )
        
        # حذف فایل موقت
        os.remove(filename)

    except Exception as e:
        logger.error(f"Panel backup error: {e}", exc_info=True)
        await bot.send_message(call.from_user.id, "❌ خطای سیستمی در تهیه بکاپ پنل.")

async def _backup_postgres_secure(call: types.CallbackQuery, timestamp: str):
    """اجرای pg_dump به صورت امن و Async"""
    filename = f"pg_backup_{timestamp}.sql"
    # حذف درایور asyncpg از URL برای استفاده در ابزار CLI
    pg_url_clean = DATABASE_URL.replace("+asyncpg", "")
    
    try:
        # استفاده از لیست آرگومان‌ها برای امنیت بیشتر
        cmd_args = ["pg_dump", "--dbname", pg_url_clean, "-f", filename]
        
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"Postgres backup failed: {error_msg}")
            await bot.send_message(call.from_user.id, f"❌ خطا در اجرای pg_dump:\n{error_msg}")
            return

        # ارسال فایل
        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()

        await bot.send_document(
            chat_id=call.from_user.id,
            document=file_data,
            visible_file_name=filename,
            caption=f"🐘 <b>بکاپ کامل دیتابیس (SQL)</b>\n📅 {timestamp}",
            parse_mode='HTML'
        )
        
        os.remove(filename)

    except FileNotFoundError:
        await bot.send_message(call.from_user.id, "❌ ابزار `pg_dump` روی سرور نصب نیست.")
    except Exception as e:
        logger.error(f"Backup critical error: {e}", exc_info=True)
        await bot.send_message(call.from_user.id, "❌ خطای ناشناخته در بکاپ‌گیری.")