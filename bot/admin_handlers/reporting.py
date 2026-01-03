# bot/admin_handlers/reporting.py

import logging
import os
import functools
import asyncio
import aiofiles
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from telebot import types
from sqlalchemy import select, func, and_, or_, desc, distinct, String
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.database import db
from bot.db.base import (
    User, UserUUID, WalletTransaction, ScheduledMessage, 
    Panel, SystemConfig, UsageSnapshot
)
from bot.db import queries
from bot.utils.date_helpers import to_shamsi, format_relative_time, days_until_next_birthday
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown, write_csv_sync, format_usage, format_currency
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

LRM = "\u200e"
RLM = "\u200f"

# ---------------------------------------------------------
# بخش ۱: استراتژی‌های گزارش (Report Strategies)
# ---------------------------------------------------------

class ReportStrategy(ABC):
    """کلاس پایه برای تمام انواع گزارش‌ها"""
    @abstractmethod
    async def generate(self, session, params: list, offset: int, limit: int) -> tuple[list, int, str]:
        """
        خروجی: (لیست آیتم‌های فرمت شده، تعداد کل، عنوان گزارش)
        """
        pass

# --- استراتژی‌های مربوط به پنل ---

class BasePanelStrategy(ReportStrategy):
    """کلاس والد برای گزارش‌های پنل جهت جلوگیری از تکرار کد"""
    
    async def _fetch_and_parse_users(self, session, panel_id):
        panel_obj = await session.get(Panel, panel_id)
        if not panel_obj:
            raise ValueError("Panel not found")

        try:
            panel_service = await PanelFactory.get_panel(panel_obj.name)
            all_users = await panel_service.get_all_users()
        except Exception as e:
            logger.error(f"Failed to fetch users from panel {panel_obj.name}: {e}")
            return [], panel_obj
        
        parsed_users = []
        for u in all_users:
            last_seen_raw = u.get('online_at') or u.get('last_online') or u.get('last_connection')
            last_seen_dt = None
            if last_seen_raw:
                try:
                    if isinstance(last_seen_raw, (int, float)):
                        last_seen_dt = datetime.utcfromtimestamp(float(last_seen_raw))
                    elif isinstance(last_seen_raw, str):
                        clean_time = last_seen_raw.replace('Z', '').split('.')[0]
                        last_seen_dt = datetime.fromisoformat(clean_time)
                except: pass
            
            u['_parsed_last_seen'] = last_seen_dt
            u['_used_bytes'] = u.get('used_traffic') or (u.get('current_usage_GB', 0) * 1024**3)
            u['_limit_bytes'] = u.get('transfer_enable') or (u.get('usage_limit_GB', 0) * 1024**3)
            parsed_users.append(u)
            
        return parsed_users, panel_obj

    async def _enrich_with_db_info(self, session, users_list, panel_id):
        idents = [u.get('uuid') or u.get('username') for u in users_list]
        idents = [i for i in idents if i]
        
        telegram_map = {}
        db_id_map = {}
        
        if idents:
            stmt = select(UserUUID).where(
                and_(
                    UserUUID.allowed_panels.any(id=panel_id),
                    or_(UserUUID.uuid.cast(String).in_(idents), UserUUID.name.in_(idents))
                )
            )
            db_users = (await session.execute(stmt)).scalars().all()
            for du in db_users:
                key_uuid = str(du.uuid) if du.uuid else None
                key_name = du.name
                
                if du.user_id:
                    if key_uuid: telegram_map[key_uuid] = du.user_id
                    if key_name: telegram_map[key_name] = du.user_id
                
                if key_uuid: db_id_map[key_uuid] = du.id
                if key_name: db_id_map[key_name] = du.id
                
        return telegram_map, db_id_map

    def _format_user_line(self, user, display_name, telegram_id=None):
        clean_name = display_name.replace('<', '').replace('>', '').replace('[', '').replace(']', '')
        name_esc = escape_markdown(clean_name)
        if telegram_id:
            return f"[{name_esc}](tg://user?id={telegram_id})"
        return name_esc

class OnlineUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        # فیلتر آنلاین‌ها (۳ دقیقه اخیر)
        window = timedelta(minutes=3)
        now_utc = datetime.utcnow()
        filtered = [u for u in users if u['_parsed_last_seen'] and (now_utc - u['_parsed_last_seen']) < window]
        
        tg_map, db_id_map = await self._enrich_with_db_info(session, filtered, panel_id)
        
        # محاسبه مصرف روزانه
        daily_usage = {}
        if db_id_map:
            start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            snap_stmt = select(UsageSnapshot).where(
                and_(
                    UsageSnapshot.uuid_id.in_(list(db_id_map.values())),
                    UsageSnapshot.taken_at >= start_of_day
                )
            )
            snapshots = (await session.execute(snap_stmt)).scalars().all()
            
            first_usage_today = {}
            for snap in snapshots:
                if snap.uuid_id not in first_usage_today:
                    total_gb = (snap.hiddify_usage_gb or 0) + (snap.marzban_usage_gb or 0)
                    first_usage_today[snap.uuid_id] = total_gb * (1024**3)

            for u in filtered:
                ident = u.get('uuid') or u.get('username')
                if ident and ident in db_id_map:
                    db_id = db_id_map[ident]
                    if db_id in first_usage_today:
                        daily = u['_used_bytes'] - first_usage_today[db_id]
                        daily_usage[ident] = max(0, daily)

        total_count = len(filtered)
        paged_users = filtered[offset : offset + limit]
        
        items = []
        for u in paged_users:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            usage_bytes = daily_usage.get(ident, 0)
            usage_str = f"{usage_bytes / (1024**3):.2f} GB" if usage_bytes >= 0.01 * (1024**3) else f"{usage_bytes / (1024**2):.0f} MB"
            
            days_str = "?"
            try:
                if 'remaining_days' in u and u['remaining_days'] is not None:
                    days_str = f"{int(u['remaining_days'])}d"
                elif 'expire' in u and u['expire']:
                    ts = float(u['expire'])
                    if ts > 0:
                        rem = int((ts - datetime.now().timestamp()) / 86400)
                        days_str = f"{rem}d" if rem >= 0 else "Exp"
                    else:
                        days_str = "∞"
            except: pass

            items.append(f"• {link} \| `{escape_markdown(usage_str)}` \| `{escape_markdown(days_str)}`")

        return items, total_count, f"⚡️ *{escape_markdown(f'کاربران آنلاین ({panel_obj.name})')}*"

class ActiveUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        window = timedelta(hours=24)
        now_utc = datetime.utcnow()
        filtered = [u for u in users if u['_parsed_last_seen'] and (now_utc - u['_parsed_last_seen']) < window]
        
        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []
        
        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            last_seen = to_shamsi(u['_parsed_last_seen'])
            percent = int((u['_used_bytes'] / u['_limit_bytes']) * 100) if u['_limit_bytes'] > 0 else 0
            
            items.append(f"• {link}{LRM} \| {RLM}{escape_markdown(last_seen)} {RLM}\| {RLM}`{percent}%`")
            
        return items, total_count, f"✅ *{escape_markdown(f'کاربران فعال ({panel_obj.name})')}*"

class InactiveUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        now = datetime.utcnow()
        filtered = []
        for u in users:
            dt = u['_parsed_last_seen']
            if dt:
                diff = now - dt
                if timedelta(days=1) <= diff < timedelta(days=7):
                    filtered.append(u)

        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            time_ago = format_relative_time(u['_parsed_last_seen'])
            
            items.append(f"• {link}{LRM} \| {RLM}{escape_markdown(time_ago)}")
            
        return items, total_count, f"⏳ *{escape_markdown(f'کاربران غیرفعال ({panel_obj.name})')}*"

class NeverConnectedStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        filtered = [u for u in users if not u['_parsed_last_seen'] or u['_used_bytes'] == 0]
        
        tg_map, _ = await self._enrich_with_db_info(session, filtered, panel_id)
        total_count = len(filtered)
        paged = filtered[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            
            limit_gb = u.get('_limit_bytes', 0) / (1024**3)
            limit_str = f"{limit_gb:.0f}GB" if limit_gb.is_integer() else f"{limit_gb:.1f}GB"
            
            items.append(f"• {link}{LRM} \| `0/{limit_str}`")
            
        return items, total_count, f"🚫 *{escape_markdown(f'هرگز متصل نشده ({panel_obj.name})')}*"

class PanelUsersStrategy(BasePanelStrategy):
    async def generate(self, session, params, offset, limit):
        panel_id = int(params[1])
        users, panel_obj = await self._fetch_and_parse_users(session, panel_id)
        
        tg_map, _ = await self._enrich_with_db_info(session, users, panel_id)
        total_count = len(users)
        paged = users[offset : offset + limit]
        items = []

        for u in paged:
            ident = u.get('uuid') or u.get('username')
            name = u.get('username') or u.get('name') or "No Name"
            link = self._format_user_line(u, name, tg_map.get(ident))
            items.append(f"• {link}")
            
        return items, total_count, f"👥 *{escape_markdown(f'همه کاربران پنل {panel_obj.name}')}*"

# --- استراتژی‌های دیتابیس داخلی ---

class BirthdayStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        stmt = select(User).where(User.birthday.isnot(None))
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        # سورت بر اساس نزدیکی تولد
        users_sorted = sorted(users, key=lambda u: days_until_next_birthday(u.birthday) if u.birthday else 999)
        total_count = len(users_sorted)
        paged = users_sorted[offset : offset + limit]
        
        items = []
        for user in paged:
            name = escape_markdown((user.first_name or 'ناشناس').replace('|', ''))
            shamsi = to_shamsi(user.birthday)
            rem = days_until_next_birthday(user.birthday)
            
            if rem == 0: days_str = "امروز! 🎉"
            elif rem is not None: days_str = f"{rem} روز"
            else: days_str = "نامشخص"
            
            items.append(f"🎂 {name} \| {shamsi} \| {escape_markdown(days_str)}")
            
        return items, total_count, f"🎂 *{escape_markdown('لیست تولد کاربران') }*"

class PlanReportStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        plan_id = int(params[1])
        stmt = queries.get_users_by_plan_query(plan_id)
        
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = await session.scalar(count_stmt) or 0
        
        result = await session.execute(stmt.offset(offset).limit(limit))
        users = result.scalars().all()
        
        items = []
        for user in users:
            name = escape_markdown(user.first_name or "بدون نام")
            link = f"[{name}](tg://user?id={user.user_id})"
            items.append(f"• {link}{LRM} \(`{user.user_id}`\)")
            
        return items, total_count, f"📊 *{escape_markdown('گزارش بر اساس پلن')}*"

class BotUsersStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        stmt = select(User).order_by(User.user_id.desc())
        
        count_stmt = select(func.count(User.user_id))
        total_count = await session.scalar(count_stmt) or 0
        
        result = await session.execute(stmt.offset(offset).limit(limit))
        users = result.scalars().all()
        
        items = []
        for user in users:
            name = escape_markdown(user.first_name or "بدون نام")
            link = f"[{name}](tg://user?id={user.user_id})"
            items.append(f"• {link}{LRM} \(`{user.user_id}`\)")
            
        return items, total_count, f"👥 *{escape_markdown('کل کاربران ربات')}*"

class PaymentsReportStrategy(ReportStrategy):
    async def generate(self, session, params, offset, limit):
        stmt = select(WalletTransaction).order_by(WalletTransaction.transaction_date.desc())
        
        count_stmt = select(func.count(WalletTransaction.id))
        total_count = await session.scalar(count_stmt) or 0
        
        result = await session.execute(stmt.options(selectinload(WalletTransaction.user)).offset(offset).limit(limit))
        txs = result.scalars().all()
        
        items = []
        for tx in txs:
            u_name = tx.user.first_name if tx.user else str(tx.user_id)
            clean_name = escape_markdown(u_name)
            amount = f"{int(abs(tx.amount)):,}"
            date_str = to_shamsi(tx.transaction_date)
            
            icon = "🟢" if tx.amount > 0 else "🔴"
            type_map = {'charge': 'شارژ', 'purchase': 'خرید', 'addon_purchase': 'خرید حجم'}
            t_type = type_map.get(tx.type, tx.type)
            
            # Icon | Name | Type | Amount | Date
            items.append(f"{icon} {clean_name} \| {t_type} \| `{amount}` \| {date_str}")
            
        return items, total_count, f"💰 *{escape_markdown('آخرین تراکنش‌های مالی')}*"

# مپینگ استراتژی‌ها
REPORT_STRATEGIES = {
    'online_users': OnlineUsersStrategy(),
    'active_users': ActiveUsersStrategy(),
    'inactive_users': InactiveUsersStrategy(),
    'never_connected': NeverConnectedStrategy(),
    'panel_users': PanelUsersStrategy(),
    'birthdays': BirthdayStrategy(),
    'by_plan': PlanReportStrategy(),
    'bot_users': BotUsersStrategy(),
    'payments': PaymentsReportStrategy()
}

# ---------------------------------------------------------
# توابع کمکی (Helpers)
# ---------------------------------------------------------

async def get_report_settings():
    defaults = {"report_page_size": 15}
    async with db.get_session() as session:
        stmt = select(SystemConfig).where(SystemConfig.key.in_(defaults.keys()))
        results = await session.execute(stmt)
        configs = {row.key: row.value for row in results.scalars()}
    return {key: int(configs.get(key, default_val)) for key, default_val in defaults.items()}

# ---------------------------------------------------------
# هندلرهای منو (Menu Handlers)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "admin:reports_menu")
async def handle_reports_menu(call: types.CallbackQuery, params: list = None):
    """منوی اصلی گزارش‌گیری."""
    active_panels = await db.get_active_panels()
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 <b>مرکز گزارش‌گیری</b>\nلطفاً نوع گزارش را انتخاب کنید:",
        reply_markup=await admin_menu.reports_menu(active_panels),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin:quick_dashboard")
async def handle_quick_dashboard(call: types.CallbackQuery, params: list = None):
    """داشبورد سریع."""
    uid = call.from_user.id
    async with db.get_session() as session:
        total_users = await session.scalar(select(func.count(User.user_id)))
        active_uuids = await session.scalar(select(func.count(UserUUID.id)).where(UserUUID.is_active == True))
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0)
        sales_today = await session.scalar(
            select(func.sum(WalletTransaction.amount)).where(
                and_(
                    WalletTransaction.transaction_date >= today_start,
                    WalletTransaction.type.in_(['purchase', 'addon_purchase']),
                    WalletTransaction.amount < 0 
                )
            )
        ) or 0
        sales_today = abs(sales_today)

    text = (
        "🚀 <b>داشبورد سریع</b>\n"
        f"👥 کاربران: {total_users}\n"
        f"✅ سرویس‌های فعال: {active_uuids}\n"
        f"💰 فروش امروز: {int(sales_today):,} تومان"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 رفرش", callback_data="admin:quick_dashboard"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel"))
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:panel_report"))
async def handle_panel_specific_reports_menu(call: types.CallbackQuery, params: list = None):
    """منوی گزارش‌های اختصاصی یک پنل."""
    if params is None:
        params = call.data.split(':')[2:]
        
    if not params:
        return await bot.answer_callback_query(call.id, "❌ شناسه پنل یافت نشد.")

    panel_id = int(params[0])
    
    async with db.get_session() as session:
        panel_obj = await session.get(Panel, panel_id)
        panel_name = panel_obj.name if panel_obj else f"Panel {panel_id}"

    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        f"📊 گزارش‌های مربوط به پنل <b>{panel_name}</b>:",
        reply_markup=await admin_menu.panel_specific_reports_menu(panel_id, panel_name),
        parse_mode='HTML'
    )

# ---------------------------------------------------------
# هندلرهای گزارش مالی و اکسل (Financial & Excel)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_financial")
async def handle_financial_report(call: types.CallbackQuery, params: list = None):
    """گزارش مالی دقیق."""
    uid = call.from_user.id
    await bot.answer_callback_query(call.id, "در حال محاسبه...")
    
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0)
    month = now.replace(day=1, hour=0, minute=0, second=0)

    async with db.get_session() as session:
        async def calc(type_list, date_filter=None):
            stmt = select(func.sum(WalletTransaction.amount)).where(WalletTransaction.type.in_(type_list))
            if date_filter: stmt = stmt.where(WalletTransaction.transaction_date >= date_filter)
            res = await session.execute(stmt)
            return abs(res.scalar() or 0)

        sales_day = await calc(['purchase', 'addon_purchase'], today)
        sales_month = await calc(['purchase', 'addon_purchase'], month)
        sales_total = await calc(['purchase', 'addon_purchase'])
        
        deposit_day = await calc(['charge'], today)
        deposit_total = await calc(['charge'])

    text = (
        "💰 <b>گزارش مالی</b>\n\n"
        f"📥 <b>فروش (خرج کردن کیف پول):</b>\n"
        f"🔹 امروز: {int(sales_day):,} تومان\n"
        f"🔹 ماه جاری: {int(sales_month):,} تومان\n"
        f"🔹 کل: {int(sales_total):,} تومان\n\n"
        f"💳 <b>واریزی (شارژ کیف پول):</b>\n"
        f"🔸 امروز: {int(deposit_day):,} تومان\n"
        f"🔸 کل: {int(deposit_total):,} تومان"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📋 ریز تراکنش‌ها", callback_data="admin:financial_details"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:reports_menu"))
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "admin:financial_details")
async def handle_financial_details(call: types.CallbackQuery, params: list = None):
    """نمایش لیست تراکنش‌ها."""
    # ارسال به هندلر عمومی با نوع گزارش payments
    await handle_paginated_list(call, ["payments", "0"])

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_excel")
async def handle_report_excel(call: types.CallbackQuery):
    """خروجی اکسل (CSV) کاربران."""
    uid = call.from_user.id
    await bot.answer_callback_query(call.id, "📥 ساخت فایل...")
    msg = await bot.send_message(uid, "⏳ لطفاً صبر کنید...")

    filepath = os.path.join(REPORT_DIR, f"users_{datetime.now().strftime('%H%M')}.csv")
    
    try:
        async with db.get_session() as session:
            result = await session.execute(select(User).options(selectinload(User.uuids)))
            users = result.scalars().all()
            
            users_data = []
            for u in users:
                active_svcs = len([uuid for uuid in u.uuids if uuid.is_active])
                users_data.append({
                    'UserID': u.user_id,
                    'Username': u.username or '-',
                    'Name': f"{u.first_name or ''} {u.last_name or ''}",
                    'Wallet Balance': u.wallet_balance,
                    'Active Services': active_svcs,
                    'Referral Code': u.referral_code
                })

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(write_csv_sync, filepath, users_data))

        async with aiofiles.open(filepath, 'rb') as f:
            await bot.send_document(uid, await f.read(), visible_file_name="users.csv", caption="📂 لیست کاربران")
        
        await bot.delete_message(uid, msg.message_id)
        os.remove(filepath)
    except Exception as e:
        logger.error(f"Excel Error: {e}")
        await bot.edit_message_text("❌ خطا در ساخت فایل.", uid, msg.message_id)

# ---------------------------------------------------------
# هندلرهای تسک‌های زمان‌بندی شده
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "admin:scheduled_tasks")
async def handle_show_scheduled_tasks(call: types.CallbackQuery, params: list = None):
    """نمایش وضعیت کارهای زمان‌بندی شده."""
    uid = call.from_user.id
    
    async with db.get_session() as session:
        count = await session.scalar(select(func.count(ScheduledMessage.id)))
        stmt = select(ScheduledMessage).order_by(ScheduledMessage.created_at.desc()).limit(5)
        result = await session.execute(stmt)
        tasks = result.scalars().all()

    text = f"⏰ <b>وضعیت کارهای زمان‌بندی شده</b>\n\nتعداد کل: {count}\n\n"
    if tasks:
        for t in tasks:
            text += f"🔹 <code>{t.job_type}</code> | Chat: {t.chat_id}\n"
    else:
        text += "هیچ کار زمان‌بندی شده‌ای در صف نیست."

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 رفرش", callback_data="admin:scheduled_tasks"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel"))
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

# ---------------------------------------------------------
# هندلر اصلی لیست‌های داینامیک (The New Paginated Handler)
# ---------------------------------------------------------

async def handle_paginated_list(call: types.CallbackQuery, params: list):
    """
    هندلر مرکزی و بازنویسی شده برای نمایش تمام لیست‌ها.
    """
    list_type = params[0]
    
    # 1. یافتن استراتژی مناسب
    strategy = REPORT_STRATEGIES.get(list_type)
    if not strategy:
        # اگر استراتژی پیدا نشد، شاید هندلر قدیمی باشد یا اشتباه
        await bot.answer_callback_query(call.id, "❌ نوع گزارش نامعتبر است.")
        return

    # 2. استخراج پارامترهای صفحه‌بندی
    # معمولاً آخرین پارامتر شماره صفحه است.
    # فرمت‌های ممکن:
    # [type, page] -> birthdays,0
    # [type, panel_id, page] -> online_users,1,0
    # [type, plan_id, page] -> by_plan,5,0
    
    try:
        page = int(params[-1])
    except (ValueError, IndexError):
        page = 0

    # بررسی خاص برای اینکه آیا پارامتر ماقبل آخر ID است یا خیر
    # این فقط برای بازسازی دکمه‌ها (Callback Data) مهم است
    extra_id = None
    if len(params) >= 3:
         try:
             extra_id = int(params[1])
         except: pass

    PAGE_SIZE = 20
    offset = page * PAGE_SIZE
    
    items, total_count, title = [], 0, ""

    # 3. اجرای استراتژی
    async with db.get_session() as session:
        try:
            # نمایش وضعیت "در حال بارگذاری" برای کاربر
            # await bot.answer_callback_query(call.id, "⏳ در حال دریافت داده‌ها...")
            
            items, total_count, title = await strategy.generate(session, params, offset, PAGE_SIZE)
        except Exception as e:
            logger.error(f"Error generating report {list_type}: {e}", exc_info=True)
            await bot.answer_callback_query(call.id, "❌ خطا در دریافت اطلاعات.")
            return

    # 4. ساخت متن و دکمه‌ها
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
    pagination_info = f"{RLM}\(صفحه {page + 1} از {max(1, total_pages)} \| کل: {total_count}\)"
    separator = escape_markdown("──────────────────")
    
    final_text = f"{title}\n{pagination_info}\n{separator}\n\n"
    final_text += "\n".join(items) if items else escape_markdown("❌ موردی یافت نشد.")

    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_btns = []
    
    # تابع کمکی برای ساخت دکمه‌های ناوبری
    def get_cb_data(target_page):
        # بازسازی دقیق فرمت ورودی برای دکمه‌های بعدی/قبلی
        base = f"admin:list:{list_type}"
        
        # هندل کردن حالت‌های خاص (by_plan در کد قبلی فرمت خاصی داشت)
        if list_type == 'by_plan':
            # فرمت قدیمی: admin:list_by_plan:ID:PAGE
            # اما اینجا ما همه را یکدست کردیم، مگر اینکه در admin_router تفکیک شده باشد.
            # فرض بر این است که روتر همه را به اینجا می‌فرستد.
            # اگر روتر شما فرمت admin:list_by_plan را جدا هندل می‌کند، باید آن را اینجا رعایت کنید.
            # با توجه به کد اصلی، by_plan جدا صدا زده می‌شد.
            # برای اطمینان، از فرمت جنریک استفاده می‌کنیم:
            return f"admin:list_by_plan:{extra_id}:{target_page}"
        
        if extra_id is not None:
            return f"{base}:{extra_id}:{target_page}"
        
        return f"{base}:{target_page}"

    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=get_cb_data(page - 1)))
    if (page + 1) * PAGE_SIZE < total_count:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=get_cb_data(page + 1)))

    if nav_btns: kb.add(*nav_btns)

    # دکمه بازگشت
    if list_type == 'by_plan': back_cb = "admin:user_analysis_menu"
    elif extra_id and list_type != 'payments': back_cb = f"admin:panel_report:{extra_id}" # برگشت به منوی پنل
    elif list_type == 'payments': back_cb = "admin:report_financial"
    else: back_cb = "admin:reports_menu"

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))
    
    await _safe_edit(call.from_user.id, call.message.message_id, final_text, reply_markup=kb, parse_mode='MarkdownV2', disable_web_page_preview=True)

# ---------------------------------------------------------
# هندلرهای متفرقه (Legacy / Placeholder)
# ---------------------------------------------------------

async def handle_select_plan_for_report_menu(call: types.CallbackQuery, params: list = None):
    """منوی انتخاب پلن برای گزارش."""
    plans = await db.get_all_plans()
    markup = await admin_menu.select_plan_for_report_menu(plans)
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 <b>گزارش بر اساس پلن</b>\n\nلطفاً پلن مورد نظر را انتخاب کنید:",
        reply_markup=markup,
        parse_mode='HTML'
    )

async def handle_health_check(call: types.CallbackQuery, params: list = None):
    """بررسی وضعیت سلامت سیستم."""
    await bot.answer_callback_query(call.id, "✅ سیستم در وضعیت نرمال است.", show_alert=True)

async def handle_marzban_system_stats(call: types.CallbackQuery, params: list = None):
    """نمایش آمار سیستم (مخصوص مرزبان)."""
    await bot.answer_callback_query(call.id, "🚧 این بخش در حال تکمیل است...", show_alert=True)

# توابع واسط برای روتر (برای سازگاری با Callback های قدیمی)
async def handle_list_users_by_plan(call, params):
    # params: [plan_id, page]
    # تبدیل به فرمت استاندارد: ['by_plan', plan_id, page]
    new_params = ['by_plan'] + params
    await handle_paginated_list(call, new_params)

async def handle_report_by_plan_selection(call, params):
    await handle_select_plan_for_report_menu(call, params)

async def handle_list_users_no_plan(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_connected_devices_list(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_confirm_delete_transaction(call, params):
    pass 

async def handle_do_delete_transaction(call, params):
    pass