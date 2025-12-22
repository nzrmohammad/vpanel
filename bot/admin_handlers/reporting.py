# bot/admin_handlers/reporting.py

import logging
import os
import csv
import functools
from datetime import datetime, timedelta
import asyncio
import aiofiles
from telebot import types
from sqlalchemy import select, func, and_, or_, desc

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, WalletTransaction, ScheduledMessage, Panel, UsageSnapshot, Plan
from bot.db import queries
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
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
    # اگر params ارسال نشده بود (فراخوانی مستقیم توسط تلگرام)، آن را استخراج کن
    if params is None:
        params = call.data.split(':')[2:]
        
    if not params:
        return await bot.answer_callback_query(call.id, "❌ شناسه پنل یافت نشد.")

    panel_id = int(params[0])
    
    # دریافت نام پنل برای نمایش در متن پیام
    async with db.get_session() as session:
        from bot.db.base import Panel
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
# هندلر تسک‌های زمان‌بندی شده
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
    نمایش لیست‌های صفحه‌بندی شده (کاربران آنلاین، فعال، غیرفعال و ...).
    """
    list_type = params[0]
    
    # تعیین پارامترهای پنل یا پلن
    target_panel_id = int(params[1]) if list_type in ['panel_users', 'active_users', 'online_users', 'never_connected', 'inactive_users'] else None
    plan_id = int(params[1]) if list_type == 'by_plan' else None
    
    # تعیین شماره صفحه
    page = int(params[2]) if (target_panel_id or plan_id is not None) else int(params[1])

    PAGE_SIZE = 34
    offset = page * PAGE_SIZE
    items, total_count, title = [], 0, "گزارش"

    async with db.get_session() as session:
        # ---------------------------------------------------------
        # ۱. انتخاب کوئری مناسب بر اساس نوع لیست
        # ---------------------------------------------------------
        if list_type == 'online_users':
            panel_obj = await session.get(Panel, target_panel_id)
            title = f"📡 آنلاین‌های لحظه‌ای (۱۰ دقیقه): {panel_obj.name}"
            
            # دریافت لیست همه کاربران از API پنل
            try:
                panel_service = await PanelFactory.get_panel(panel_obj.name)
                online_data = await panel_service.get_all_users()
            except Exception as e:
                logger.error(f"Error fetching users from panel: {e}")
                online_data = []
            
            online_ids = []
            
            # تنظیم بازه زمانی (۱۰ دقیقه اخیر)
            limit_minutes = 10
            now_utc = datetime.utcnow()
            
            for u in online_data:
                # تلاش برای یافتن فیلد زمان اتصال (نام فیلد در پنل‌های مختلف متفاوت است)
                # Marzban: 'online_at', Hiddify/Others: 'last_connection', 'last_seen', 'last_online'
                last_seen_raw = u.get('online_at') or u.get('last_online') or u.get('last_connection')
                
                if last_seen_raw:
                    try:
                        last_seen_dt = None
                        
                        # حالت ۱: اگر زمان به صورت Timestamp (عدد) باشد
                        if isinstance(last_seen_raw, (int, float)):
                            last_seen_dt = datetime.utcfromtimestamp(float(last_seen_raw))
                            
                        # حالت ۲: اگر زمان به صورت رشته (ISO Format) باشد (مثل مرزبان)
                        elif isinstance(last_seen_raw, str):
                            # تمیز کردن رشته زمان (حذف Z و میلی‌ثانیه اضافی)
                            clean_time = last_seen_raw.replace('Z', '')
                            if '.' in clean_time:
                                clean_time = clean_time.split('.')[0]
                            last_seen_dt = datetime.fromisoformat(clean_time)

                        # مقایسه زمان
                        if last_seen_dt:
                            # اگر اختلاف زمان کمتر از حد مجاز باشد (کاربر آنلاین است)
                            if (now_utc - last_seen_dt) < timedelta(minutes=limit_minutes):
                                online_ids.append(u.get('username') or u.get('uuid'))
                                
                    except Exception:
                        pass # در صورت فرمت نامعتبر، نادیده بگیر

            # دریافت کوئری دیتابیس برای این لیست از شناسه‌ها
            stmt = queries.get_online_users_query(target_panel_id, online_ids)
            
        elif list_type == 'active_users':
            title = "✅ فعال (۲۴س) پنل"
            stmt = queries.get_active_users_query(target_panel_id)
        elif list_type == 'inactive_users':
            title = "⏳ غیرفعال‌های پنل"
            stmt = queries.get_inactive_users_query(target_panel_id)
        elif list_type == 'never_connected':
            title = "🚫 هرگز متصل نشده"
            stmt = queries.get_never_connected_query(target_panel_id)
        elif list_type == 'by_plan':
            title = "📊 گزارش بر اساس پلن"
            stmt = queries.get_users_by_plan_query(plan_id)
        elif list_type == 'bot_users':
            title = "👥 کل کاربران ربات"
            stmt = select(User).order_by(User.user_id.desc())
        else:
            # پیش‌فرض
            title = "لیست کاربران"
            stmt = select(User)

        # ---------------------------------------------------------
        # ۲. اجرای کوئری با پجینیشن
        # ---------------------------------------------------------
        # شمارش کل نتایج برای محاسبه صفحات
        total_count = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        
        # دریافت داده‌های صفحه جاری
        result = await session.execute(stmt.offset(offset).limit(PAGE_SIZE))
        
        for user in result.scalars():
            u_name = user.first_name or "بدون نام"
            u_user = f" (@{user.username})" if user.username else ""
            # نمایش آیدی عددی و نام
            items.append(f"• {u_name}{u_user} [<code>{user.user_id}</code>] |")

    # ---------------------------------------------------------
    # ۳. ساخت متن خروجی و دکمه‌ها
    # ---------------------------------------------------------
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
    text = f"<b>{title}</b>\n(صفحه {page + 1} از {max(1, total_pages)} | کل: {total_count})\n\n"
    text += "\n".join(items) if items else "❌ موردی یافت نشد."

    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_btns = []
    
    # تابع کمکی برای ساخت کالبک دکمه‌ها
    def get_cb(p):
        if target_panel_id: return f"admin:list:{list_type}:{target_panel_id}:{p}"
        if list_type == 'by_plan': return f"admin:list_by_plan:{plan_id}:{p}"
        return f"admin:list:{list_type}:{p}"

    # دکمه قبلی
    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=get_cb(page - 1)))
    # دکمه بعدی
    if (page + 1) * PAGE_SIZE < total_count:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=get_cb(page + 1)))

    if nav_btns: kb.add(*nav_btns)

    # دکمه بازگشت هوشمند
    if list_type == 'by_plan':
        back_cb = "admin:user_analysis_menu" # منوی انتخاب پلن
    elif target_panel_id:
        back_cb = f"admin:panel_report:{target_panel_id}" # منوی گزارش پنل
    else:
        back_cb = "admin:reports_menu" # منوی اصلی گزارشات

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

# ---------------------------------------------------------
# Placeholder Handlers
# ---------------------------------------------------------

async def handle_list_users_by_plan(call, params):
    await handle_paginated_list(call, ["by_plan", params[0], params[1]])

async def handle_list_users_no_plan(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_connected_devices_list(call, params):
    await bot.answer_callback_query(call.id, "این بخش هنوز فعال نیست.")

async def handle_confirm_delete_transaction(call, params):
    pass 

async def handle_do_delete_transaction(call, params):
    pass

# ---------------------------------------------------------
# Missing Handlers (اضافه شده برای رفع خطا)
# ---------------------------------------------------------

async def handle_select_plan_for_report_menu(call: types.CallbackQuery, params: list = None):
    """
    نمایش منوی انتخاب پلن برای گزارش‌گیری.
    این تابع توسط navigation.py و admin_router فراخوانی می‌شود.
    """
    # دریافت لیست پلن‌ها از دیتابیس
    plans = await db.get_all_plans()
    
    # ساخت کیبورد انتخاب پلن
    markup = await admin_menu.select_plan_for_report_menu(plans)
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 <b>گزارش بر اساس پلن</b>\n\nلطفاً پلن مورد نظر را برای مشاهده آمار انتخاب کنید:",
        reply_markup=markup,
        parse_mode='HTML'
    )

# ایجاد نام مستعار برای سازگاری با admin_router.py
# در router با این نام صدا زده شده است: report_by_plan_select
handle_report_by_plan_selection = handle_select_plan_for_report_menu