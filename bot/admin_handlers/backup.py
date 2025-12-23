# bot/admin_handlers/backup.py

import os
import logging
import asyncio
import aiofiles
import json
from datetime import datetime, date
from telebot import types
from sqlalchemy import select

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import Panel, UserUUID
from bot.services.panels import PanelFactory
from bot.utils.formatters import escape_markdown, json_serializer

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")

async def _get_panel_types():
    async with db.get_session() as session:
        stmt = select(Panel.panel_type).where(Panel.is_active == True).distinct()
        result = await session.execute(stmt)
        return result.scalars().all()

# ---------------------------------------------------------
# 1. هندلر منوی اصلی
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data == "admin:backup_menu")
async def backup_menu_handler(call: types.CallbackQuery):
    panel_types = await _get_panel_types()
    
    text = (
        "💾 *منوی پشتیبان‌گیری*\n\n"
        "⚙️ فیلتر انتخاب شده: *همه کاربران*\n"
        "لطفاً نوع پنل و نوع فیلتر کاربران را انتخاب کنید:"
    )
    
    await bot.edit_message_text(
        text,
        call.from_user.id,
        call.message.message_id,
        reply_markup=await admin_menu.backup_selection_menu(panel_types, 'all'),
        parse_mode='MarkdownV2'
    )

# ---------------------------------------------------------
# 2. هندلر تغییر فیلتر
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:backup_filter:"))
async def change_backup_filter(call: types.CallbackQuery):
    new_filter = call.data.split(":")[2]
    panel_types = await _get_panel_types()
    
    filter_texts = {
        'all': 'همه کاربران',
        'active': 'فقط کاربران فعال ✅',
        'inactive': 'فقط کاربران غیرفعال ❌'
    }
    display_text = filter_texts.get(new_filter, new_filter)
    
    text = (
        "💾 *منوی پشتیبان‌گیری*\n\n"
        f"⚙️ فیلتر انتخاب شده: *{escape_markdown(display_text)}*\n"
        "لطفاً نوع پنل و نوع فیلتر کاربران را انتخاب کنید:"
    )
    
    await bot.edit_message_text(
        text,
        call.from_user.id,
        call.message.message_id,
        reply_markup=await admin_menu.backup_selection_menu(panel_types, new_filter),
        parse_mode='MarkdownV2'
    )

# ---------------------------------------------------------
# 3. هندلر بکاپ از پنل‌ها (API Fetch)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:backup:"))
async def backup_panel_data(call: types.CallbackQuery):
    parts = call.data.split(":")
    
    if len(parts) > 2 and parts[2] == 'bot_db':
        await backup_bot_db_handler(call)
        return

    panel_type = parts[2]
    filter_mode = parts[3] if len(parts) > 3 else 'all'
    
    await bot.answer_callback_query(call.id, f"🌐 اتصال به سرورهای {panel_type}...", show_alert=False)
    await bot.send_chat_action(call.from_user.id, 'upload_document')
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"API_{panel_type}_{filter_mode}_{timestamp}.json"
    
    try:
        async with db.get_session() as session:
            stmt = select(Panel).where(Panel.panel_type == panel_type, Panel.is_active == True)
            res = await session.execute(stmt)
            panels = res.scalars().all()
            
        if not panels:
            await bot.send_message(call.from_user.id, "❌ هیچ پنل فعالی از این نوع ثبت نشده است.")
            return

        aggregated_users = []
        
        for p in panels:
            try:
                handler = await PanelFactory.get_panel(p.name)
                users = await handler.get_all_users()
                
                for u in users:
                    is_active = u.get('is_active', True)
                    
                    if filter_mode == 'active' and not is_active: continue
                    if filter_mode == 'inactive' and is_active: continue
                    
                    u['source_panel'] = p.name
                    aggregated_users.append(u)
                    
            except Exception as e:
                logger.error(f"Error fetching from {p.name}: {e}")

        if not aggregated_users:
            await bot.send_message(call.from_user.id, f"⚠️ هیچ کاربری از سرورها دریافت نشد (با فیلتر {filter_mode}).")
            return

        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(aggregated_users, ensure_ascii=False, indent=2, default=json_serializer))

        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()
            
        caption = (
            rf"☁️ *بکاپ آنلاین از پنل‌ها \(API\)*" + "\n"
            f"🔸 نوع پنل: `{escape_markdown(panel_type.capitalize())}`\n"
            f"⚙️ فیلتر: `{escape_markdown(filter_mode)}`\n"
            f"👥 تعداد کل: `{len(aggregated_users)}`"
        )

        await bot.send_document(
            chat_id=call.from_user.id,
            document=file_data,
            visible_file_name=filename,
            caption=caption,
            parse_mode='MarkdownV2'
        )
        os.remove(filename)

    except Exception as e:
        logger.error(f"API Backup error: {e}", exc_info=True)
        await bot.send_message(call.from_user.id, "❌ خطا در دریافت اطلاعات از API.")

# ---------------------------------------------------------
# 4. هندلر بکاپ دیتابیس ربات (SQL + Local JSON)
# ---------------------------------------------------------
async def backup_bot_db_handler(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "📦 شروع بکاپ‌گیری دیتابیس...", show_alert=False)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    
    if DATABASE_URL:
        await _backup_postgres_secure(call, timestamp)
    else:
        await bot.send_message(call.from_user.id, "❌ DATABASE_URL تنظیم نشده است.")
        
    await _backup_local_json(call, timestamp)

async def _backup_postgres_secure(call: types.CallbackQuery, timestamp: str):
    filename = f"DB_SQL_{timestamp}.sql"
    pg_url_clean = DATABASE_URL.replace("+asyncpg", "")
    
    try:
        cmd_args = ["pg_dump", "--dbname", pg_url_clean, "-f", filename]
        process = await asyncio.create_subprocess_exec(
            *cmd_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Postgres backup failed: {stderr.decode()}")
            await bot.send_message(call.from_user.id, "❌ خطا در تهیه فایل SQL.")
            return

        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()

        caption = rf"🐘 *بکاپ دیتابیس ربات \(SQL\)*\n📅 `{escape_markdown(timestamp)}`"
        await bot.send_document(
            chat_id=call.from_user.id, document=file_data,
            visible_file_name=filename, caption=caption, parse_mode='MarkdownV2'
        )
        os.remove(filename)
    except Exception as e:
        logger.error(f"SQL error: {e}")

async def _backup_local_json(call: types.CallbackQuery, timestamp: str):
    filename = f"DB_Users_{timestamp}.json"
    
    try:
        async with db.get_session() as session:
            stmt = select(UserUUID).order_by(UserUUID.id.desc())
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

        async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(export_data, ensure_ascii=False, indent=2, default=json_serializer))

        async with aiofiles.open(filename, 'rb') as f:
            file_data = await f.read()

        caption = (
            rf"🗂 *بکاپ کاربران دیتابیس ربات \(JSON\)*\n"
            f"👥 تعداد رکورد: `{len(export_data)}`"
        )
        
        await bot.send_document(
            chat_id=call.from_user.id, document=file_data,
            visible_file_name=filename, caption=caption, parse_mode='MarkdownV2'
        )
        os.remove(filename)

    except Exception as e:
        logger.error(f"Local JSON backup error: {e}")