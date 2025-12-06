# bot/admin_handlers/reporting.py

import logging
import os
import csv
import functools
from datetime import datetime, timedelta
import asyncio
import aiofiles
from telebot import types
from sqlalchemy import select, func, and_, desc

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, WalletTransaction, ScheduledMessage, Panel
from bot.utils import _safe_edit, escape_markdown
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# ---------------------------------------------------------
# توابع کمکی (Helpers)
# ---------------------------------------------------------

def write_csv_sync(filepath, users_data):
    """عملیات سنگین CSV در ترد جداگانه."""
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['UserID', 'Username', 'Name', 'Wallet Balance', 'Active Services', 'Referral Code']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(users_data)

# ---------------------------------------------------------
# هندلرهای منو (Menu Handlers)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "admin:reports_menu")
async def handle_reports_menu(call: types.CallbackQuery, params: list = None):
    """منوی اصلی گزارش‌گیری."""
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 <b>مرکز گزارش‌گیری</b>\nلطفاً نوع گزارش را انتخاب کنید:",
        reply_markup=admin_menu.reports_menu(),
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:panel_reports"))
async def handle_panel_specific_reports_menu(call: types.CallbackQuery, params: list):
    """منوی گزارش‌های اختصاصی یک پنل."""
    panel_type = params[0] if params else 'hiddify'
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        f"📊 گزارش‌های مربوط به پنل‌های <b>{panel_type}</b>:",
        reply_markup=await admin_menu.panel_specific_reports_menu(panel_type),
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
    """نمایش دکمه‌های لیست تراکنش‌ها."""
    # فعلا هدایت به لیست پرداخت‌ها
    await handle_paginated_list(call, ["payments", "0"])

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_excel")
async def handle_report_excel(call: types.CallbackQuery):
    """خروجی اکسل کاربران."""
    uid = call.from_user.id
    await bot.answer_callback_query(call.id, "📥 ساخت فایل...")
    msg = await bot.send_message(uid, "⏳ لطفاً صبر کنید...")

    filepath = os.path.join(REPORT_DIR, f"users_{datetime.now().strftime('%H%M')}.csv")
    
    try:
        async with db.get_session() as session:
            from sqlalchemy.orm import selectinload
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
# هندلر تسک‌های زمان‌بندی شده (Missing Function Fixed)
# ---------------------------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "admin:scheduled_tasks")
async def handle_show_scheduled_tasks(call: types.CallbackQuery, params: list = None):
    """
    نمایش وضعیت کارهای زمان‌بندی شده.
    این تابع قبلاً وجود نداشت و باعث ارور می‌شد.
    """
    uid = call.from_user.id
    
    async with db.get_session() as session:
        # دریافت تعداد پیام‌های زمان‌بندی شده
        count = await session.scalar(select(func.count(ScheduledMessage.id)))
        
        # دریافت آخرین تسک‌ها
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
# هندلرهای وضعیت سیستم (Health Check)
# ---------------------------------------------------------

async def handle_health_check(call: types.CallbackQuery, params: list = None):
    """بررسی وضعیت سلامت سرورهای هیدیفای."""
    await bot.answer_callback_query(call.id, "🩺 در حال بررسی اتصال...")
    
    active_panels = await db.get_active_panels()
    hiddify_panels = [p for p in active_panels if p['panel_type'] == 'hiddify']
    
    report = "<b>وضعیت سرورهای Hiddify:</b>\n\n"
    
    for p in hiddify_panels:
        try:
            panel = await PanelFactory.get_panel(p['name'])
            stats = await panel.get_system_stats()
            status = "✅ آنلاین" if stats else "❌ آفلاین"
            usage = f"(CPU: {stats.get('cpu_usage', '?')}%)" if stats else ""
            report += f"🔹 <b>{p['name']}</b>: {status} {usage}\n"
        except Exception as e:
            report += f"🔹 <b>{p['name']}</b>: ❌ خطا\n"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:system_status_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, report, reply_markup=kb, parse_mode='HTML')

async def handle_marzban_system_stats(call: types.CallbackQuery, params: list = None):
    """بررسی وضعیت سلامت سرورهای مرزبان."""
    await bot.answer_callback_query(call.id, "🩺 در حال بررسی اتصال...")
    
    active_panels = await db.get_active_panels()
    marzban_panels = [p for p in active_panels if p['panel_type'] == 'marzban']
    
    report = "<b>وضعیت سرورهای Marzban:</b>\n\n"
    
    for p in marzban_panels:
        try:
            panel = await PanelFactory.get_panel(p['name'])
            stats = await panel.get_system_stats()
            # مرزبان معمولا دیکشنری با version, user_count و ... برمی‌گرداند
            status = "✅ آنلاین" if stats else "❌ آفلاین"
            version = f"(v{stats.get('version', '?')})" if stats else ""
            report += f"🔹 <b>{p['name']}</b>: {status} {version}\n"
        except Exception:
            report += f"🔹 <b>{p['name']}</b>: ❌ خطا\n"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:system_status_menu"))
    await _safe_edit(call.from_user.id, call.message.message_id, report, reply_markup=kb, parse_mode='HTML')

# ---------------------------------------------------------
# هندلر لیست‌های عمومی (Paginated Lists)
# ---------------------------------------------------------

async def handle_paginated_list(call: types.CallbackQuery, params: list):
    """
    هندلر عمومی برای نمایش لیست‌های طولانی.
    params[0]: نوع لیست (payments, bot_users, active_users, ...)
    params[1]: پنل (اختیاری) یا شماره صفحه
    params[2]: شماره صفحه
    """
    list_type = params[0]
    
    # پارس کردن پارامترها
    if list_type in ['panel_users', 'active_users', 'online_users', 'never_connected', 'inactive_users', 'top_consumers']:
        target_panel = params[1]
        page = int(params[2])
    elif list_type == 'by_plan':
        plan_id = int(params[1])
        page = int(params[2])
        target_panel = None
    else:
        page = int(params[1])
        target_panel = None

    PAGE_SIZE = 10
    offset = page * PAGE_SIZE
    
    items = []
    total_count = 0
    title = "لیست"

    async with db.get_session() as session:
        if list_type == 'payments':
            title = "آخرین تراکنش‌ها (واریز)"
            count_stmt = select(func.count(WalletTransaction.id)).where(WalletTransaction.type == 'charge')
            stmt = select(WalletTransaction, User).join(User).where(WalletTransaction.type == 'charge') \
                   .order_by(desc(WalletTransaction.transaction_date)).offset(offset).limit(PAGE_SIZE)
            
            total_count = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            
            rows = result.all()
            for trans, user in rows:
                date_str = trans.transaction_date.strftime("%Y-%m-%d %H:%M")
                items.append(f"👤 <code>{user.user_id}</code> | 💰 {int(trans.amount):,} | 📅 {date_str}")

        elif list_type == 'bot_users':
            title = "کاربران ربات"
            count_stmt = select(func.count(User.user_id))
            stmt = select(User).order_by(desc(User.user_id)).offset(offset).limit(PAGE_SIZE)
            
            total_count = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            
            for user in result.scalars():
                items.append(f"👤 {user.first_name} (<code>{user.user_id}</code>)")

        elif list_type == 'balances':
            title = "موجودی کیف پول‌ها"
            count_stmt = select(func.count(User.user_id)).where(User.wallet_balance > 0)
            stmt = select(User).where(User.wallet_balance > 0).order_by(desc(User.wallet_balance)).offset(offset).limit(PAGE_SIZE)
            
            total_count = await session.scalar(count_stmt)
            result = await session.execute(stmt)
            
            for user in result.scalars():
                items.append(f"💰 {int(user.wallet_balance):,} T | 👤 {user.first_name}")

    # ساخت متن نهایی
    text = f"📋 <b>{title}</b> (صفحه {page + 1})\n\n"
    text += "\n".join(items) if items else "موردی یافت نشد."
    
    # کیبورد
    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_btns = []
    
    # ساخت کالبک دیتای مناسب برای دکمه‌ها
    def make_cb(p):
        if target_panel:
            return f"admin:list:{list_type}:{target_panel}:{p}"
        elif list_type == 'by_plan':
            return f"admin:list_by_plan:{plan_id}:{p}"
        else:
            return f"admin:list:{list_type}:{p}"

    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=make_cb(page - 1)))
    if (page + 1) * PAGE_SIZE < total_count:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=make_cb(page + 1)))
        
    if nav_btns: kb.add(*nav_btns)
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:reports_menu"))

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

# ---------------------------------------------------------
# Placeholder Handlers (برای جلوگیری از ارورهای ایمپورت)
# ---------------------------------------------------------

async def handle_list_users_by_plan(call, params):
    """هندلر لیست کاربران بر اساس پلن"""
    # فراخوانی هندلر جنریک با پارامترهای مناسب
    await handle_paginated_list(call, ["by_plan", params[0], params[1]])

async def handle_list_users_no_plan(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_connected_devices_list(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_confirm_delete_transaction(call, params):
    pass 

async def handle_do_delete_transaction(call, params):
    pass