# bot/admin_handlers/reporting.py

import logging
import os
import functools
from datetime import datetime, timedelta
import asyncio
import aiofiles
from telebot import types
from sqlalchemy import select, func, and_, or_, desc

from bot.bot_instance import bot
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.database import db
from bot.db.base import (
    User, UserUUID, WalletTransaction, ScheduledMessage, 
    Panel, SystemConfig
)
from bot.db import queries
from bot.db.usage import calculate_daily_usage  # ✅ ایمپورت لاجیک محاسبه مصرف
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown, write_csv_sync, format_usage  # ✅ ایمپورت توابع کمکی
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# ---------------------------------------------------------
# تنظیمات داینامیک (Settings Helper)
# ---------------------------------------------------------

async def get_report_settings():
    """
    دریافت تنظیمات گزارش‌گیری از دیتابیس.
    اگر مقادیر در دیتابیس نباشند، از پیش‌فرض‌های ۱۵ و ۳ استفاده می‌کند.
    """
    defaults = {
        "report_page_size": 15,
        "report_online_window": 3
    }
    
    async with db.get_session() as session:
        stmt = select(SystemConfig).where(SystemConfig.key.in_(defaults.keys()))
        results = await session.execute(stmt)
        configs = {row.key: row.value for row in results.scalars()}

    return {
        key: int(configs.get(key, default_val)) 
        for key, default_val in defaults.items()
    }

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
        # استفاده از تابع کمکی منتقل شده به utils
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
# هندلر لیست‌های عمومی و داینامیک (Paginated Lists)
# ---------------------------------------------------------

async def handle_paginated_list(call: types.CallbackQuery, params: list):
    """
    نمایش لیست‌های صفحه‌بندی شده.
    شامل قابلیت دریافت اطلاعات زنده کاربران آنلاین و تنظیمات داینامیک.
    """
    list_type = params[0]
    
    # تعیین پارامترهای پنل یا پلن
    target_panel_id = int(params[1]) if list_type in ['panel_users', 'active_users', 'online_users', 'never_connected', 'inactive_users'] else None
    plan_id = int(params[1]) if list_type == 'by_plan' else None
    page = int(params[2]) if (target_panel_id or plan_id is not None) else int(params[1])

    # ⚙️ 1. دریافت تنظیمات داینامیک از دیتابیس
    settings = await get_report_settings()
    PAGE_SIZE = settings['report_page_size']
    ONLINE_WINDOW = settings['report_online_window']

    offset = page * PAGE_SIZE
    items, total_count, title = [], 0, "گزارش"

    async with db.get_session() as session:
        # =========================================================
        # 🟢 بخش کاربران آنلاین (Live Data + Daily Usage)
        # =========================================================
        if list_type == 'online_users':
            panel_obj = await session.get(Panel, target_panel_id)
            title = f"⚡️ <b>کاربران آنلاین ({ONLINE_WINDOW} دقیقه اخیر)</b>\nپنل: {panel_obj.name}"
            
            # الف) دریافت لیست زنده همه کاربران از پنل
            try:
                panel_service = await PanelFactory.get_panel(panel_obj.name)
                all_users_live = await panel_service.get_all_users()
            except Exception as e:
                logger.error(f"Error fetching live users: {e}")
                all_users_live = []
            
            # ب) فیلتر کردن کاربرانی که در بازه زمانی تعیین شده فعال بوده‌اند
            online_filtered = []
            now_utc = datetime.utcnow()
            
            for u in all_users_live:
                last_seen_raw = u.get('online_at') or u.get('last_online') or u.get('last_connection')
                if not last_seen_raw: continue

                try:
                    last_seen_dt = None
                    if isinstance(last_seen_raw, (int, float)):
                        last_seen_dt = datetime.utcfromtimestamp(float(last_seen_raw))
                    elif isinstance(last_seen_raw, str):
                        clean_time = last_seen_raw.replace('Z', '').split('.')[0]
                        last_seen_dt = datetime.fromisoformat(clean_time)

                    if last_seen_dt and (now_utc - last_seen_dt) < timedelta(minutes=ONLINE_WINDOW):
                        online_filtered.append(u)
                except Exception:
                    pass

            total_count = len(online_filtered)
            
            # ج) جدا کردن کاربران صفحه جاری
            current_page_users = online_filtered[offset : offset + PAGE_SIZE]

            # د) آماده‌سازی داده‌ها برای محاسبه مصرف روزانه (مپ کردن نام کاربر پنل به شناسه دیتابیس)
            identifiers = [u.get('uuid') or u.get('username') for u in current_page_users]
            identifiers = [i for i in identifiers if i]

            user_uuids_map = {} # { identifier_str : db_id }
            live_usage_map = {} # { identifier_str : current_bytes }

            if identifiers:
                stmt = select(UserUUID.id, UserUUID.uuid, UserUUID.name).where(
                    and_(
                        UserUUID.allowed_panels.any(id=target_panel_id),
                        or_(
                            UserUUID.uuid.cast(str).in_(identifiers),
                            UserUUID.name.in_(identifiers)
                        )
                    )
                )
                db_results = await session.execute(stmt)
                for row in db_results:
                    if row.uuid: user_uuids_map[str(row.uuid)] = row.id
                    if row.name: user_uuids_map[row.name] = row.id

            # ه) استخراج مصرف لحظه‌ای کاربران صفحه جاری
            for u in current_page_users:
                ident = u.get('uuid') or u.get('username')
                if not ident: continue
                
                # دریافت مصرف کل (بسته به نوع پنل فیلد متفاوت است)
                total_bytes = u.get('used_traffic') or (u.get('current_usage_GB', 0) * 1024**3)
                live_usage_map[ident] = total_bytes
            
            # و) فراخوانی تابع خارجی برای محاسبه مصرف روزانه
            daily_usage_data = await calculate_daily_usage(session, user_uuids_map, live_usage_map)

            # ز) ساخت خروجی متنی نهایی
            for u in current_page_users:
                name = u.get('username') or u.get('name') or "No Name"
                ident = u.get('uuid') or u.get('username')
                
                # 1. مصرف روزانه
                daily_bytes = daily_usage_data.get(ident, 0)
                usage_str = format_usage(daily_bytes / (1024**3)) # تبدیل به GB

                # 2. روزهای باقی‌مانده
                days_str = "?"
                if 'expire' in u and u['expire']: # Marzban
                    rem = (datetime.fromtimestamp(u['expire']) - datetime.now()).days
                    days_str = f"{max(0, rem)} days"
                elif 'package_days' in u: # Hiddify
                    days_str = f"{u['package_days']} days"
                else:
                    days_str = "∞ days"

                items.append(f"• {name} | {usage_str} | {days_str}")

        # =========================================================
        # ⚪️ سایر لیست‌ها (Active, Inactive, ...)
        # =========================================================
        else:
            if list_type == 'active_users':
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
                title = "لیست کاربران"
                stmt = select(User)

            # شمارش کل
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total_count = await session.scalar(count_stmt) or 0
            
            # دریافت داده‌ها
            result = await session.execute(stmt.offset(offset).limit(PAGE_SIZE))
            
            for user in result.scalars():
                u_name = user.first_name or "بدون نام"
                items.append(f"• {u_name} (<code>{user.user_id}</code>)")

    # ---------------------------------------------------------
    # 3. ساخت متن و دکمه‌های نهایی
    # ---------------------------------------------------------
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
    text = f"{title}\n(Page {page + 1}/{max(1, total_pages)} | Total: {total_count})\n{'─' * 20}\n\n"
    text += "\n".join(items) if items else "❌ موردی یافت نشد."

    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_btns = []
    
    # ساخت کالبک دیتا
    def get_cb(p):
        prefix = f"admin:list:{list_type}"
        if target_panel_id: return f"{prefix}:{target_panel_id}:{p}"
        if list_type == 'by_plan': return f"admin:list_by_plan:{plan_id}:{p}"
        return f"{prefix}:{p}"

    if page > 0:
        nav_btns.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=get_cb(page - 1)))
    if (page + 1) * PAGE_SIZE < total_count:
        nav_btns.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=get_cb(page + 1)))

    if nav_btns: kb.add(*nav_btns)

    # دکمه بازگشت هوشمند
    if list_type == 'by_plan':
        back_cb = "admin:user_analysis_menu"
    elif target_panel_id:
        back_cb = f"admin:panel_report:{target_panel_id}"
    else:
        back_cb = "admin:reports_menu"

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')

# ---------------------------------------------------------
# Missing / Placeholder Handlers
# ---------------------------------------------------------

async def handle_select_plan_for_report_menu(call: types.CallbackQuery, params: list = None):
    """منوی انتخاب پلن."""
    plans = await db.get_all_plans()
    markup = await admin_menu.select_plan_for_report_menu(plans)
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 <b>گزارش بر اساس پلن</b>\n\nلطفاً پلن مورد نظر را انتخاب کنید:",
        reply_markup=markup,
        parse_mode='HTML'
    )

# Alias for Router Compatibility
handle_report_by_plan_selection = handle_select_plan_for_report_menu

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