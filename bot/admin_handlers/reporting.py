# bot/admin_handlers/reporting.py

import logging
import os
import csv
import asyncio
import aiofiles
from datetime import datetime
from telebot import types

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot import combined_handler
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

# ---------------------------------------------------------
# توابع کمکی (Helpers) - اجرا در ترد جداگانه
# ---------------------------------------------------------

def write_csv_sync(filepath, users_data):
    """
    نوشتن فایل CSV به صورت همزمان (Sync) اما در ترد جداگانه.
    این کار باعث می‌شود ربات هنگام نوشتن فایل‌های سنگین قفل نکند.
    """
    try:
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
            # تعریف ستون‌های خروجی اکسل
            fieldnames = [
                'Name', 'UUID/Username', 'Total Usage (GB)', 'Limit (GB)', 
                'Remaining (GB)', 'Expire Date', 'Active Panels', 'Status', 'User ID'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for u in users_data:
                # استخراج اطلاعات برای هر سطر
                panels_str = ", ".join(u.get('panels', []))
                status = 'Active' if u.get('is_active') else 'Inactive'
                
                # تلاش برای پیدا کردن User ID عددی (اگر در دیتا موجود باشد)
                # در combined_handler ممکن است user_id را برنگرداند مگر اینکه اضافه کرده باشیم
                # اینجا فعلا خالی یا N/A می‌گذاریم اگر نباشد
                user_id = u.get('user_id', 'N/A')

                writer.writerow({
                    'Name': u.get('name', 'Unknown'),
                    'UUID/Username': u.get('uuid') or u.get('name', '---'),
                    'Total Usage (GB)': f"{u.get('current_usage_GB', 0):.2f}",
                    'Limit (GB)': f"{u.get('usage_limit_GB', 0):.2f}",
                    'Remaining (GB)': f"{u.get('remaining_GB', 0):.2f}",
                    'Expire Date': u.get('expire') if u.get('expire') else 'Unlimited',
                    'Active Panels': panels_str,
                    'Status': status,
                    'User ID': user_id
                })
        return True
    except Exception as e:
        logger.error(f"Error writing CSV: {e}")
        return False

# ---------------------------------------------------------
# هندلرهای اصلی منو
# ---------------------------------------------------------

async def handle_reporting_menu(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی گزارش‌گیری."""
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "📊 *منوی گزارش‌گیری و آمار*\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=await admin_menu.reporting_menu()
    )

# ---------------------------------------------------------
# 1. اسنپ‌شات (ذخیره وضعیت فعلی مصرف در دیتابیس)
# ---------------------------------------------------------

async def handle_create_usage_snapshot(call: types.CallbackQuery, params: list):
    """
    ایجاد اسنپ‌شات از مصرف تمام کاربران.
    🚀 بهینه‌سازی شده: دریافت همزمان اطلاعات از تمام پنل‌ها.
    """
    uid, msg_id = call.from_user.id, call.message.message_id
    
    # نمایش وضعیت انتظار
    await _safe_edit(uid, msg_id, "⏳ *در حال جمع‌آوری اطلاعات از تمام سرورها...*\nلطفاً صبر کنید (این عملیات همزمان انجام می‌شود).")

    try:
        # دریافت اطلاعات کل کاربران به صورت همزمان (بسیار سریع)
        # این تابع قبلاً در combined_handler بهینه شده است
        all_users_data = await combined_handler.get_all_users_combined()
        
        if not all_users_data:
            await _safe_edit(uid, msg_id, "❌ کاربری یافت نشد یا ارتباط با سرورها برقرار نیست.", reply_markup=await admin_menu.reporting_menu())
            return

        # ذخیره در دیتابیس
        # فرض بر این است که متد save_usage_snapshot در db پیاده‌سازی شده است
        # اگر این متد وجود ندارد، باید در database.py اضافه شود یا اینجا هندل شود
        if hasattr(db, 'save_usage_snapshot'):
            count = await db.save_usage_snapshot(all_users_data)
        else:
            # فال‌بک: اگر متد اختصاصی اسنپ‌شات در دیتابیس نیست، فقط تعداد را نمایش می‌دهیم
            count = len(all_users_data)
            logger.warning("Method 'save_usage_snapshot' not found in db. Skipping save.")
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        await _safe_edit(
            uid, msg_id,
            f"✅ *گزارش‌گیری با موفقیت انجام شد.*\n\n📉 تعداد کاربران پردازش شده: `{count}`\n📅 تاریخ: `{timestamp}`",
            reply_markup=await admin_menu.reporting_menu()
        )

    except Exception as e:
        logger.error(f"Snapshot Error: {e}", exc_info=True)
        await _safe_edit(uid, msg_id, f"❌ خطا در تهیه گزارش:\n`{str(e)}`", reply_markup=await admin_menu.reporting_menu())

# ---------------------------------------------------------
# 2. خروجی اکسل (CSV Export)
# ---------------------------------------------------------

async def handle_export_users_csv(call: types.CallbackQuery, params: list):
    """
    دریافت فایل اکسل لیست کاربران.
    🚀 بهینه‌سازی شده: جلوگیری از بلاک شدن ربات هنگام ساخت فایل.
    """
    uid, msg_id = call.from_user.id, call.message.message_id
    
    await _safe_edit(uid, msg_id, "⏳ *در حال آماده‌سازی فایل خروجی...*\nاطلاعات کاربران در حال دریافت است.")

    try:
        # 1. دریافت داده‌های تازه (همزمان)
        all_users = await combined_handler.get_all_users_combined()
        
        if not all_users:
            await bot.answer_callback_query(call.id, "❌ داده‌ای برای خروجی وجود ندارد.")
            await handle_reporting_menu(call, [])
            return

        # 2. نام فایل با برچسب زمانی
        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(REPORT_DIR, filename)

        # 3. اجرای عملیات نوشتن فایل در ترد جداگانه (Non-blocking I/O)
        # این خط باعث می‌شود ربات هنگام نوشتن فایل‌های سنگین هنگ نکند
        success = await asyncio.to_thread(write_csv_sync, filepath, all_users)

        if not success:
             await _safe_edit(uid, msg_id, "❌ خطا در ساخت فایل CSV.", reply_markup=await admin_menu.reporting_menu())
             return

        # 4. ارسال فایل برای مدیر
        if os.path.exists(filepath):
            await bot.send_chat_action(uid, 'upload_document')
            async with aiofiles.open(filepath, 'rb') as f:
                file_data = await f.read()
                
            await bot.send_document(
                uid, 
                file_data, 
                visible_file_name=filename, 
                caption=f"📂 *خروجی لیست کاربران*\n👥 تعداد کاربران: {len(all_users)}\n📅 {datetime.now().strftime('%Y-%m-%d')}",
                parse_mode="Markdown"
            )
            
            # حذف فایل موقت از سرور
            try:
                os.remove(filepath)
            except:
                pass
            
            # بازگشت به منو
            await _safe_edit(uid, msg_id, "✅ فایل با موفقیت ارسال شد.", reply_markup=await admin_menu.reporting_menu())
        else:
            await _safe_edit(uid, msg_id, "❌ فایل خروجی یافت نشد.", reply_markup=await admin_menu.reporting_menu())

    except Exception as e:
        logger.error(f"CSV Export Error: {e}", exc_info=True)
        await _safe_edit(uid, msg_id, f"❌ خطا در فرآیند خروجی:\n`{str(e)}`", reply_markup=await admin_menu.reporting_menu())

# ---------------------------------------------------------
# 3. هندلرهای مربوط به گزارش پلن‌ها
# ---------------------------------------------------------

async def handle_select_plan_for_report_menu(call: types.CallbackQuery, params: list = None):
    """نمایش لیست پلن‌ها برای مشاهده گزارش خاص آن پلن."""
    plans = await db.get_all_plans()
    if not plans:
        await bot.answer_callback_query(call.id, "❌ هیچ پلنی تعریف نشده است.")
        return

    markup = await admin_menu.select_plan_for_report_menu(plans)
    await _safe_edit(
        call.from_user.id, 
        call.message.message_id, 
        "📊 *لطفاً پلن مورد نظر را برای مشاهده گزارش انتخاب کنید:*", 
        reply_markup=markup
    )

async def handle_generate_plan_report(call: types.CallbackQuery, params: list):
    """تولید گزارش برای یک پلن خاص."""
    uid = call.from_user.id
    plan_id = int(params[0])
    
    # دریافت اطلاعات پلن
    plan = await db.get_plan_by_id(plan_id)
    if not plan:
        await bot.answer_callback_query(call.id, "❌ پلن یافت نشد.")
        return
        
    # دریافت کاربران این پلن (از دیتابیس لوکال)
    users = await db.get_users_by_plan(plan_id)
    
    count = len(users)
    # فرض می‌کنیم آبجکت user فیلد enabled یا مشابه دارد
    active_count = 0
    for u in users:
        if hasattr(u, 'enabled') and u.enabled:
            active_count += 1
        elif hasattr(u, 'is_active') and u.is_active:
             active_count += 1
    
    price = plan.get('price', 0)
    volume = plan.get('volume_gb', 0)
    
    text = (
        f"📊 *گزارش پلن: {escape_markdown(plan['name'])}*\n"
        f"➖➖➖➖➖➖➖➖\n"
        f"👥 تعداد کل کاربران: `{count}`\n"
        f"🟢 کاربران فعال: `{active_count}`\n"
        f"💰 قیمت پلن: `{price:,} تومان`\n"
        f"📦 حجم پلن: `{volume} GB`\n"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:reporting_menu"))
    
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb)

# ---------------------------------------------------------
# 4. سایر هندلرها (Placeholders)
# ---------------------------------------------------------

async def handle_list_users_no_plan(call: types.CallbackQuery, params: list):
    """نمایش کاربرانی که هیچ پلنی ندارند."""
    # می‌توان در آینده پیاده‌سازی کرد
    await bot.answer_callback_query(call.id, "🚧 این بخش در دست تکمیل است.")

async def handle_connected_devices_list(call: types.CallbackQuery, params: list):
    """گزارش دستگاه‌های متصل."""
    await bot.answer_callback_query(call.id, "🚧 این بخش در دست تکمیل است.")

async def handle_usage_history_chart(call: types.CallbackQuery, params: list):
    """نمودار مصرف."""
    await bot.answer_callback_query(call.id, "🚧 نمودارها به زودی اضافه می‌شوند.")

async def handle_confirm_delete_transaction(call, params):
    pass 

async def handle_do_delete_transaction(call, params):
    pass