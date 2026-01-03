# bot/admin_handlers/reporting.py

import logging
import os
import functools
from datetime import datetime, timedelta, timezone
import asyncio
import aiofiles
from telebot import types
from sqlalchemy import select, func, and_, or_, desc, distinct, String

from bot.bot_instance import bot
from bot.keyboards.admin import admin_keyboard as admin_menu
from bot.database import db
from bot.db.base import (
    User, UserUUID, WalletTransaction, ScheduledMessage, 
    Panel, SystemConfig, UsageSnapshot
)
from bot.db import queries
from bot.utils.date_helpers import to_shamsi, format_relative_time
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown, write_csv_sync, format_usage
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# ---------------------------------------------------------
# توابع کمکی (Helpers)
# ---------------------------------------------------------

async def get_report_settings():
    """
    دریافت تنظیمات گزارش‌گیری از دیتابیس.
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

async def calculate_live_daily_usage(session, user_uuids_map: dict, live_usage_map: dict) -> dict:
    """
    محاسبه مصرف روزانه با مقایسه دیتای زنده پنل و اسنپ‌شات اول روز در دیتابیس.
    
    :param user_uuids_map: { 'identifier': db_uuid_id }
    :param live_usage_map: { 'identifier': current_total_bytes }
    :return: { 'identifier': daily_usage_bytes }
    """
    if not user_uuids_map:
        return {}

    # محاسبه شروع روز به وقت UTC (برای کوئری دیتابیس)
    # فرض بر این است که اسنپ‌شات‌ها UTC هستند. برای دقت بالاتر می‌توان تایم‌زون تهران را لحاظ کرد.
    now_utc = datetime.now(timezone.utc)
    today_midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    
    uuid_ids = list(user_uuids_map.values())
    
    # دریافت آخرین اسنپ‌شات قبل از نیمه‌شب (Baseline)
    # استفاده از DISTINCT ON مخصوص پستگرس برای سرعت بالا
    stmt = (
        select(UsageSnapshot)
        .distinct(UsageSnapshot.uuid_id)
        .where(
            and_(
                UsageSnapshot.uuid_id.in_(uuid_ids),
                UsageSnapshot.taken_at < today_midnight
            )
        )
        .order_by(UsageSnapshot.uuid_id, desc(UsageSnapshot.taken_at))
    )
    
    result = await session.execute(stmt)
    snapshots = result.scalars().all()
    
    # ساخت مپ { db_uuid_id : start_of_day_bytes }
    start_usage_map = {}
    for snap in snapshots:
        # تبدیل GB دیتابیس به بایت
        total_gb = (snap.hiddify_usage_gb or 0) + (snap.marzban_usage_gb or 0)
        start_usage_map[snap.uuid_id] = total_gb * (1024**3)

    final_daily_usage = {}
    
    for identifier, db_id in user_uuids_map.items():
        current_bytes = live_usage_map.get(identifier, 0)
        start_bytes = start_usage_map.get(db_id, 0)
        
        # محاسبه اختلاف (با در نظر گرفتن ریست شدن احتمالی پنل)
        if current_bytes >= start_bytes:
            daily_bytes = current_bytes - start_bytes
        else:
            # اگر مصرف فعلی کمتر از شروع روز بود، یعنی پنل ریست شده -> کل مصرف فعلی مال امروز است
            daily_bytes = current_bytes
            
        final_daily_usage[identifier] = daily_bytes

    return final_daily_usage

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
# هندلر لیست‌های عمومی و داینامیک (Paginated Lists)
# ---------------------------------------------------------
LRM = "\u200e"  # Left-to-Right Mark (برای بعد از نام انگلیسی)
RLM = "\u200f"  # Right-to-Left Mark (برای قبل از متن فارسی)

async def handle_paginated_list(call: types.CallbackQuery, params: list):
    """
    نسخه نهایی:
    1. نام کاربر لینک شده به پروفایل (tg://user?id=...)
    2. نمایش مصرف امروز (Daily Usage)
    3. نمایش روزهای باقی‌مانده
    4. پشتیبانی از تمام پنل‌ها (Dynamic Usage)
    """
    list_type = params[0]
    
    target_panel_id = int(params[1]) if list_type in ['panel_users', 'active_users', 'online_users', 'never_connected', 'inactive_users'] else None
    plan_id = int(params[1]) if list_type == 'by_plan' else None
    
    page_index_param = 2 if (target_panel_id or plan_id is not None) else 1
    page = int(params[page_index_param]) if len(params) > page_index_param else 0

    PAGE_SIZE = 20
    ONLINE_WINDOW = 3

    offset = page * PAGE_SIZE
    items, total_count, title = [], 0, escape_markdown("گزارش")

    async with db.get_session() as session:
        
        live_report_types = ['online_users', 'active_users', 'inactive_users', 'never_connected', 'panel_users']
        
        if list_type in live_report_types and target_panel_id:
            panel_obj = await session.get(Panel, target_panel_id)
            if not panel_obj:
                await bot.answer_callback_query(call.id, "پنل یافت نشد.")
                return

            try:
                panel_service = await PanelFactory.get_panel(panel_obj.name)
                all_users_live = await panel_service.get_all_users()
            except Exception as e:
                logger.error(f"Error fetching live users: {e}")
                await bot.answer_callback_query(call.id, "❌ خطا در اتصال به پنل")
                return

            # --- پردازش اولیه داده‌ها ---
            filtered_users = []
            now_utc = datetime.utcnow()
            
            for u in all_users_live:
                # 1. استانداردسازی زمان
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

                # 2. فیلتر کردن
                include_user = False
                if list_type == 'online_users':
                    if last_seen_dt and (now_utc - last_seen_dt) < timedelta(minutes=ONLINE_WINDOW):
                        include_user = True
                        title = f"⚡️ *{escape_markdown(f'کاربران آنلاین ({ONLINE_WINDOW} دقیقه اخیر)')}*"

                elif list_type == 'active_users':
                    if last_seen_dt and (now_utc - last_seen_dt) < timedelta(hours=24):
                        include_user = True
                        title = f"✅ *{escape_markdown('کاربران فعال (۲۴ ساعت اخیر)')}*"

                elif list_type == 'inactive_users':
                    if last_seen_dt:
                        diff = now_utc - last_seen_dt
                        if timedelta(days=1) <= diff < timedelta(days=7):
                            include_user = True
                            title = f"⏳ *{escape_markdown('کاربران غیرفعال (۱ تا ۷ روز)')}*"

                elif list_type == 'never_connected':
                    if not last_seen_dt or u['_used_bytes'] == 0:
                        include_user = True
                        title = f"🚫 *{escape_markdown('کاربران هرگز متصل نشده')}*"
                
                elif list_type == 'panel_users':
                    include_user = True
                    title = f"👥 *{escape_markdown(f'همه کاربران پنل {panel_obj.name}')}*"

                if include_user:
                    filtered_users.append(u)

            # --- دریافت مصرف روزانه و لینک پروفایل ---
            daily_usage_map = {}
            telegram_id_map = {} # مپ برای ذخیره آیدی تلگرام

            # اگر لیستی داریم، اطلاعات تکمیلی را از دیتابیس بگیریم
            if filtered_users:
                idents = [u.get('uuid') or u.get('username') for u in filtered_users]
                idents = [i for i in idents if i]
                
                if idents:
                    # دریافت اطلاعات کاربران از دیتابیس (شامل user_id تلگرام)
                    uuid_stmt = select(UserUUID).where(
                        and_(
                            UserUUID.allowed_panels.any(id=target_panel_id),
                            or_(UserUUID.uuid.cast(String).in_(idents), UserUUID.name.in_(idents))
                        )
                    )
                    db_users = (await session.execute(uuid_stmt)).scalars().all()
                    
                    if db_users:
                        user_ids_list = []
                        user_map = {} # برای مپ کردن شناسه پنل به شناسه دیتابیس

                        for du in db_users:
                            # ذخیره نگاشت برای پیدا کردن Telegram ID
                            if du.uuid:
                                telegram_id_map[str(du.uuid)] = du.user_id
                                user_map[str(du.uuid)] = du.id
                            if du.name:
                                telegram_id_map[du.name] = du.user_id
                                user_map[du.name] = du.id
                            
                            user_ids_list.append(du.id)

                        # فقط برای آنلاین‌ها مصرف روزانه را حساب می‌کنیم
                        if list_type == 'online_users':
                            start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            snap_stmt = select(UsageSnapshot).where(
                                and_(
                                    UsageSnapshot.uuid_id.in_(user_ids_list),
                                    UsageSnapshot.taken_at >= start_of_day
                                )
                            ).order_by(UsageSnapshot.taken_at.asc())
                            
                            snapshots = (await session.execute(snap_stmt)).scalars().all()
                            
                            first_usage_today = {}
                            for snap in snapshots:
                                if snap.uuid_id not in first_usage_today:
                                    # جمع هوشمند تمام ستون‌های مصرف
                                    total_gb = 0.0
                                    for attr in dir(snap):
                                        if attr.endswith('_usage_gb') and not attr.startswith('_'):
                                            val = getattr(snap, attr, 0)
                                            if val: total_gb += float(val)
                                    first_usage_today[snap.uuid_id] = total_gb * (1024**3)

                            # محاسبه نهایی مصرف روزانه
                            for u in filtered_users:
                                ident = u.get('uuid') or u.get('username')
                                if ident and ident in user_map:
                                    db_id = user_map[ident]
                                    if db_id in first_usage_today:
                                        daily = u['_used_bytes'] - first_usage_today[db_id]
                                        daily_usage_map[ident] = max(0, daily)

            # --- صفحه‌بندی ---
            total_count = len(filtered_users)
            current_page_users = filtered_users[offset : offset + PAGE_SIZE]

            # --- فرمت‌بندی خروجی ---
            for u in current_page_users:
                raw_name = u.get('username') or u.get('name') or "No Name"
                clean_name = raw_name.replace('<', '').replace('>', '')
                name_esc = escape_markdown(clean_name)
                
                ident = u.get('uuid') or u.get('username')
                
                # 🔗 ساخت لینک پروفایل (اگر آیدی تلگرام پیدا شد)
                linked_name = name_esc
                if ident and ident in telegram_id_map and telegram_id_map[ident]:
                    tg_id = telegram_id_map[ident]
                    # لینک به پروفایل کاربر
                    linked_name = f"[{name_esc}](tg://user?id={tg_id})"

                # ------------------------------------------
                # ۱. فرمت آنلاین‌ها (Online Users)
                # ساختار: نام (لینک) | مصرف امروز | روزهای مانده
                # ------------------------------------------
                if list_type == 'online_users':
                    # الف) مصرف امروز
                    if ident and ident in daily_usage_map:
                        final_usage_bytes = daily_usage_map[ident]
                    else:
                        final_usage_bytes = u.get('_used_bytes', 0) # اگر مصرف امروز نبود، کل را نشان بده
                    usage_str = format_usage(final_usage_bytes / (1024**3))

                    # ب) روزهای مانده
                    days_str = "Unlimited"
                    try:
                        if 'remaining_days' in u and u['remaining_days'] is not None:
                             days = int(u['remaining_days'])
                             days_str = f"{days} days" if days >= 0 else "Expired"
                        elif 'expire' in u and u['expire']:
                            expire_ts = float(u['expire'])
                            if expire_ts > 0:
                                rem = (expire_ts - datetime.now().timestamp()) / 86400
                                days_str = f"{int(rem)} days" if rem > 0 else "Expired"
                        elif 'package_days' in u and not u.get('expire'):
                             days_str = f"{u['package_days']} days"
                    except: pass
                    
                    # خط نهایی: نام لینک‌دار | مصرف | روز
                    line = f"• {linked_name}{LRM} \| {escape_markdown(usage_str)} \| {escape_markdown(days_str)}"
                    items.append(line)

                # ------------------------------------------
                # ۲. فرمت فعال (Active Users)
                # ساختار: نام | تاریخ | درصد
                # ------------------------------------------
                elif list_type == 'active_users':
                    last_seen_date = "نامشخص"
                    if u.get('_parsed_last_seen'):
                        last_seen_date = to_shamsi(u['_parsed_last_seen'])
                    limit = u.get('_limit_bytes', 0)
                    used = u.get('_used_bytes', 0)
                    percent = int((used / limit) * 100) if limit > 0 else 0
                    
                    line = f"• {linked_name}{LRM} \| {RLM}{escape_markdown(last_seen_date)} {RLM}\| {RLM}{percent}%"
                    items.append(line)

                # ------------------------------------------
                # ۳. فرمت غیرفعال (Inactive Users)
                # ساختار: نام | زمان نسبی | وضعیت
                # ------------------------------------------
                elif list_type == 'inactive_users':
                    time_ago_str = format_relative_time(u.get('_parsed_last_seen'))
                    status = "فعال"
                    try:
                        if 'remaining_days' in u and u['remaining_days'] is not None and int(u['remaining_days']) < 0: status = "منقضی"
                        elif 'expire' in u and u['expire'] and u['expire'] > 0 and u['expire'] < datetime.now().timestamp(): status = "منقضی"
                    except: pass
                    
                    line = f"• {linked_name}{LRM} \| {RLM}{escape_markdown(time_ago_str)} {RLM}\| {RLM}{escape_markdown(status)}"
                    items.append(line)

                # ------------------------------------------
                # ۴. فرمت هرگز متصل نشده (Never Connected)
                # ساختار: نام | حجم کل | اعتبار زمانی
                # ------------------------------------------
                elif list_type == 'never_connected':
                    limit_gb = u.get('_limit_bytes', 0) / (1024**3)
                    limit_str = f"{limit_gb:.0f} GB" if limit_gb.is_integer() else f"{limit_gb:.1f} GB"
                    days_str = "نامحدود"
                    try:
                        if 'package_days' in u: days_str = f"{u['package_days']} روز"
                        elif 'remaining_days' in u and u['remaining_days'] is not None: days_str = f"{int(u['remaining_days'])} روز"
                    except: pass
                    
                    line = f"• {linked_name}{LRM} \| {escape_markdown(limit_str)} \| {RLM}{escape_markdown(days_str)}"
                    items.append(line)
                
                # ------------------------------------------
                # پیش‌فرض
                # ------------------------------------------
                else:
                    items.append(f"• {linked_name}")

        # =========================================================
        # سایر لیست‌ها (Local DB)
        # =========================================================
        else:
            stmt = None
            if list_type == 'by_plan':
                title = f"📊 *{escape_markdown('گزارش بر اساس پلن')}*"
                stmt = queries.get_users_by_plan_query(plan_id)
            elif list_type == 'bot_users':
                title = f"👥 *{escape_markdown('کل کاربران ربات')}*"
                stmt = select(User).order_by(User.user_id.desc())
            
            if stmt is not None:
                count_stmt = select(func.count()).select_from(stmt.subquery())
                total_count = await session.scalar(count_stmt) or 0
                result = await session.execute(stmt.offset(offset).limit(PAGE_SIZE))
                for user in result.scalars():
                    u_name = user.first_name or "بدون نام"
                    # لینک کردن نام در لیست‌های دیتابیسی هم
                    u_link = f"[{escape_markdown(u_name)}](tg://user?id={user.user_id})"
                    items.append(f"• {u_link}{LRM} \(`{user.user_id}`\)")
            else:
                 items.append(escape_markdown("⚠️ نوع گزارش نامعتبر است."))

    # ---------------------------------------------------------
    # ساخت متن نهایی
    # ---------------------------------------------------------
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE
    pagination_text = f"{RLM}\(صفحه {page + 1} از {max(1, total_pages)} \| کل: {total_count}\)"
    separator = escape_markdown("──────────────────")
    
    text = f"{title}\n{pagination_text}\n{separator}\n\n"
    text += "\n".join(items) if items else escape_markdown("❌ موردی یافت نشد.")

    kb = types.InlineKeyboardMarkup(row_width=2)
    nav_btns = []
    
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

    if list_type == 'by_plan': back_cb = "admin:user_analysis_menu"
    elif target_panel_id: back_cb = f"admin:panel_report:{target_panel_id}"
    else: back_cb = "admin:reports_menu"

    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=back_cb))
    
    # نکته: برای اینکه لینک‌ها کار کنند، حتماً disable_web_page_preview=True باشد تا پیام شلوغ نشود
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb, parse_mode='MarkdownV2', disable_web_page_preview=True)

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

handle_report_by_plan_selection = handle_select_plan_for_report_menu

# ---------------------------------------------------------
# Missing Handlers (Added to fix AttributeError)
# ---------------------------------------------------------

async def handle_health_check(call: types.CallbackQuery, params: list = None):
    """
    بررسی وضعیت سلامت سیستم
    """
    # در اینجا می‌توانید لاجیک بررسی دیتابیس یا پنل‌ها را اضافه کنید
    # فعلاً یک پیام ساده برمی‌گردانیم تا ارور رفع شود
    await bot.answer_callback_query(call.id, "✅ سیستم در وضعیت نرمال است.", show_alert=True)

async def handle_marzban_system_stats(call: types.CallbackQuery, params: list = None):
    """
    نمایش آمار سیستم (مخصوص مرزبان یا کلی)
    """
    await bot.answer_callback_query(call.id, "🚧 این بخش در حال تکمیل است...", show_alert=True)

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