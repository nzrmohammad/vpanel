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
from bot.db.base import User, UserUUID, WalletTransaction, UsageSnapshot, Payment
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# مسیر ذخیره فایل‌های موقت گزارش
REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

def write_csv_sync(filepath, users_data):
    """
    این تابع عملیات نوشتن فایل CSV را به صورت همگام (Sync) انجام می‌دهد.
    ما این تابع را در یک Thread جداگانه اجرا می‌کنیم تا ربات قفل نشود.
    """
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
        fieldnames = ['UserID', 'Username', 'Name', 'Wallet Balance', 'Active Services', 'Referral Code', 'Joined Date']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        writer.writerows(users_data)

@bot.callback_query_handler(func=lambda call: call.data == "admin:reporting_menu")
async def reporting_menu_handler(call: types.CallbackQuery):
    """نمایش منوی اصلی گزارش‌گیری"""
    await bot.edit_message_text(
        "📊 <b>مرکز گزارش‌گیری</b>\n\n"
        "لطفاً نوع گزارش مورد نظر خود را انتخاب کنید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=admin_menu.reporting_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin:quick_dashboard")
async def handle_quick_dashboard(call: types.CallbackQuery):
    """داشبورد سریع شامل خلاصه وضعیت سیستم"""
    user_id = call.from_user.id
    
    # دریافت آمار به صورت زنده
    async with db.get_session() as session:
        # تعداد کاربران و سرویس‌ها
        total_users = await session.scalar(select(func.count(User.user_id)))
        active_uuids = await session.scalar(select(func.count(UserUUID.id)).where(UserUUID.is_active == True))
        
        # محاسبه فروش امروز (شروع روز)
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sales_today = await session.scalar(
            select(func.sum(func.abs(WalletTransaction.amount))).where(
                and_(
                    WalletTransaction.transaction_date >= today_start,
                    WalletTransaction.type.in_(['purchase', 'addon_purchase', 'gift_purchase'])
                )
            )
        ) or 0

    text = (
        "🚀 <b>داشبورد وضعیت سریع</b>\n"
        f"──────────────────\n"
        f"👥 <b>کل کاربران:</b> {total_users}\n"
        f"✅ <b>سرویس‌های فعال:</b> {active_uuids}\n"
        f"💰 <b>فروش امروز:</b> {int(sales_today):,} تومان\n"
        f"──────────────────\n"
        f"🕒 بروزرسانی: {datetime.now().strftime('%H:%M')}"
    )
    
    # دکمه‌های رفرش و بازگشت
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin:quick_dashboard"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:panel"))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode='HTML')    

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_general")
async def handle_report_general(call: types.CallbackQuery):
    """گزارش آماری کلی (کاربران و سرویس‌ها)"""
    user_id = call.from_user.id
    
    await bot.answer_callback_query(call.id, "🔄 در حال جمع‌آوری اطلاعات...")
    
    async with db.get_session() as session:
        # 1. آمار کاربران
        total_users = await session.scalar(select(func.count(User.user_id)))
        
        # 2. آمار سرویس‌ها
        total_uuids = await session.scalar(select(func.count(UserUUID.id)))
        active_uuids = await session.scalar(select(func.count(UserUUID.id)).where(UserUUID.is_active == True))
        
    report_text = (
        "📊 <b>گزارش آماری کلی</b>\n"
        f"──────────────────\n"
        f"👥 <b>کل کاربران ربات:</b> {total_users}\n"
        f"🎫 <b>کل کانفیگ‌های ساخته شده:</b> {total_uuids}\n"
        f"✅ <b>کانفیگ‌های فعال:</b> {active_uuids}\n"
        f"❌ <b>کانفیگ‌های منقضی/غیرفعال:</b> {total_uuids - active_uuids}\n"
        f"──────────────────\n"
        f"📅 تاریخ گزارش: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    
    await _safe_edit(user_id, call.message.message_id, report_text, reply_markup=admin_menu.back_to_reporting(), parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_financial")
async def handle_report_financial(call: types.CallbackQuery):
    """گزارش مالی (درآمد و فروش)"""
    user_id = call.from_user.id
    await bot.answer_callback_query(call.id, "💰 در حال محاسبه درآمد...")

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async with db.get_session() as session:
        # تابع کمکی برای محاسبه فروش
        async def get_sales(since_date=None):
            stmt = select(func.sum(func.abs(WalletTransaction.amount))).where(
                WalletTransaction.type.in_(['purchase', 'addon_purchase', 'gift_purchase'])
            )
            if since_date:
                stmt = stmt.where(WalletTransaction.transaction_date >= since_date)
            
            result = await session.execute(stmt)
            return result.scalar() or 0

        # تابع کمکی برای محاسبه شارژ کیف پول (پول واقعی وارد شده)
        async def get_deposits(since_date=None):
            stmt = select(func.sum(WalletTransaction.amount)).where(
                WalletTransaction.type == 'charge'
            )
            if since_date:
                stmt = stmt.where(WalletTransaction.transaction_date >= since_date)
            
            result = await session.execute(stmt)
            return result.scalar() or 0

        # محاسبه مقادیر
        sales_today = await get_sales(today_start)
        sales_month = await get_sales(month_start)
        sales_total = await get_sales(None)

        deposits_today = await get_deposits(today_start)
        deposits_month = await get_deposits(month_start)
        deposits_total = await get_deposits(None)

    report_text = (
        "💰 <b>گزارش مالی</b>\n"
        f"──────────────────\n"
        f"📥 <b>فروش سرویس (از کیف پول):</b>\n"
        f"🔹 امروز: {int(sales_today):,} تومان\n"
        f"🔹 این ماه: {int(sales_month):,} تومان\n"
        f"🔹 کل: {int(sales_total):,} تومان\n\n"
        f"💳 <b>افزایش موجودی (واریزی):</b>\n"
        f"🔸 امروز: {int(deposits_today):,} تومان\n"
        f"🔸 این ماه: {int(deposits_month):,} تومان\n"
        f"🔸 کل: {int(deposits_total):,} تومان\n"
        f"──────────────────\n"
        f"📅 تاریخ: {now.strftime('%Y-%m-%d')}"
    )

    await _safe_edit(user_id, call.message.message_id, report_text, reply_markup=admin_menu.back_to_reporting(), parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "admin:report_excel")
async def handle_report_excel(call: types.CallbackQuery):
    """تولید و ارسال فایل اکسل (CSV) کاربران"""
    user_id = call.from_user.id
    await bot.answer_callback_query(call.id, "📥 در حال تولید فایل اکسل...")
    await bot.send_message(user_id, "⏳ لطفاً صبر کنید، فایل در حال آماده‌سازی است...")

    filename = f"users_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    filepath = os.path.join(REPORT_DIR, filename)

    try:
        async with db.get_session() as session:
            # دریافت همه کاربران با اطلاعات مرتبط
            # از selectinload برای لود کردن relation ها استفاده می‌کنیم تا در دسترسی به user.uuids مشکلی نباشد
            from sqlalchemy.orm import selectinload
            stmt = select(User).options(selectinload(User.uuids)).order_by(User.user_id)
            
            result = await session.execute(stmt)
            users = result.scalars().all()

            # آماده‌سازی داده‌ها در حافظه (این بخش سریع است)
            users_data = []
            for user in users:
                active_services = len([u for u in user.uuids if u.is_active]) if user.uuids else 0
                
                users_data.append({
                    'UserID': user.user_id,
                    'Username': user.username or 'None',
                    'Name': f"{user.first_name or ''} {user.last_name or ''}".strip(),
                    'Wallet Balance': user.wallet_balance,
                    'Active Services': active_services,
                    'Referral Code': user.referral_code,
                    'Joined Date': 'N/A' 
                })

        # اجرای عملیات سنگین نوشتن فایل در یک Executor (ترد جداگانه)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, 
            functools.partial(write_csv_sync, filepath, users_data)
        )

        # ارسال فایل با استفاده از aiofiles برای خواندن
        async with aiofiles.open(filepath, 'rb') as f:
            file_data = await f.read()
            
        await bot.send_document(
            user_id,
            document=file_data,
            visible_file_name=filename,
            caption="📂 <b>لیست کامل کاربران</b>\nفرمت: CSV (قابل باز شدن در اکسل)",
            parse_mode='HTML'
        )
        
        # حذف فایل موقت پس از ارسال
        os.remove(filepath)

    except Exception as e:
        logger.error(f"Error generating excel report: {e}", exc_info=True)
        await bot.send_message(user_id, "❌ خطا در تولید فایل گزارش.")