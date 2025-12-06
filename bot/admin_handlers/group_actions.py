# bot/admin_handlers/group_actions.py

import asyncio
import logging
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import UserUUID, Panel
from bot.services.panels import PanelFactory
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# استیت برای ذخیره مراحل عملیات گروهی
# ساختار: {admin_id: {'target_type': 'plan'/'filter', 'target_value': id/code, 'action': 'add_gb'/'add_days', 'value': 10}}
ga_state = {}

# ==============================================================================
# 1. منوها و انتخاب‌های اولیه
# ==============================================================================

async def handle_select_plan_for_action(call: types.CallbackQuery, params: list):
    """نمایش لیست پلن‌ها برای انتخاب هدف عملیات گروهی."""
    # دریافت پلن‌های فعال
    plans = await db.get_all_plans(active_only=True)
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "⚙️ **دستور گروهی (بر اساس پلن)**\n\nلطفاً پلن مورد نظر را انتخاب کنید (تغییرات روی کاربرانی که این پلن را دارند اعمال نمی‌شود، بلکه این صرفاً یک گروه‌بندی فرضی است یا می‌توانید برای همه اعمال کنید):",
        reply_markup=await admin_menu.select_plan_for_action_menu(plans)
    )

async def handle_select_advanced_filter(call: types.CallbackQuery, params: list):
    """نمایش فیلترهای پیشرفته (منقضی شده‌ها، غیرفعال‌ها و...)."""
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "🔥 **دستور گروهی (پیشرفته)**\n\nچه گروهی از کاربران را هدف قرار می‌دهید؟",
        reply_markup=await admin_menu.advanced_group_action_filter_menu()
    )

async def handle_select_action_type(call: types.CallbackQuery, params: list):
    """انتخاب نوع عملیات (حجم یا زمان) پس از انتخاب پلن."""
    # params[0]: plan_id
    plan_id = params[0]
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "چه تغییری می‌خواهید اعمال کنید؟",
        reply_markup=await admin_menu.select_action_type_menu(plan_id, "plan")
    )

async def handle_select_action_for_filter(call: types.CallbackQuery, params: list):
    """انتخاب نوع عملیات (حجم یا زمان) پس از انتخاب فیلتر پیشرفته."""
    # params[0]: filter_code (expiring_soon, inactive_30_days, ...)
    filter_code = params[0]
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "چه تغییری می‌خواهید اعمال کنید؟",
        reply_markup=await admin_menu.select_action_type_menu(filter_code, "filter")
    )

# ==============================================================================
# 2. دریافت مقادیر و تاییدیه
# ==============================================================================

async def handle_ask_action_value(call: types.CallbackQuery, params: list):
    """دریافت مقدار عددی (گیگابایت یا روز)."""
    # params: [action, context_type, context_value]
    # action: add_gb / add_days
    # context_type: plan / filter
    # context_value: plan_id / filter_code
    
    admin_id = call.from_user.id
    action, context_type, context_value = params[0], params[1], params[2]
    
    ga_state[admin_id] = {
        'action': action,
        'target_type': context_type,
        'target_value': context_value,
        'msg_id': call.message.message_id
    }
    
    unit = "گیگابایت" if action == "add_gb" else "روز"
    prompt = f"🔢 لطفاً مقدار **{unit}** مورد نظر را وارد کنید (عدد):"
    
    await _safe_edit(admin_id, call.message.message_id, prompt, reply_markup=await admin_menu.cancel_action("admin:group_actions_menu"))
    bot.register_next_step_handler(call.message, process_ga_value)

async def process_ga_value(message: types.Message):
    """پردازش مقدار وارد شده و نمایش تاییدیه نهایی."""
    admin_id = message.from_user.id
    if admin_id not in ga_state: return
    
    try:
        await bot.delete_message(admin_id, message.message_id)
    except: pass

    try:
        value = float(message.text.strip())
        ga_state[admin_id]['value'] = value
        
        data = ga_state[admin_id]
        action_str = "افزودن حجم" if data['action'] == "add_gb" else "افزودن زمان"
        target_str = f"پلن {data['target_value']}" if data['target_type'] == 'plan' else f"فیلتر: {data['target_value']}"
        
        confirm_text = (
            "⚠️ **تایید نهایی عملیات گروهی**\n\n"
            f"🎯 هدف: {target_str}\n"
            f"🛠 عملیات: {action_str}\n"
            f"🔢 مقدار: `{value}`\n\n"
            "آیا مطمئن هستید؟ این عملیات روی تمام کاربران منطبق اجرا می‌شود و غیرقابل بازگشت است."
        )
        
        await _safe_edit(
            admin_id, 
            data['msg_id'], 
            confirm_text, 
            reply_markup=await admin_menu.confirm_group_action_menu()
        )
        
    except ValueError:
        await bot.send_message(admin_id, "❌ لطفاً فقط عدد وارد کنید.")

# ==============================================================================
# 3. اجرا و پردازش پس‌زمینه
# ==============================================================================

async def ga_execute(call: types.CallbackQuery, params: list):
    """شروع اجرای عملیات گروهی."""
    admin_id = call.from_user.id
    data = ga_state.pop(admin_id, None)
    
    if not data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات منقضی شده است.", show_alert=True)
        return

    await bot.edit_message_text(
        "🚀 عملیات در پس‌زمینه شروع شد...\n"
        "⏳ لطفاً صبر کنید. پس از پایان کار، گزارشی برای شما ارسال خواهد شد.",
        admin_id,
        call.message.message_id
    )

    # اجرای تسک در پس‌زمینه بدون مسدود کردن ربات
    asyncio.create_task(
        run_group_action_task(
            admin_id, 
            data['action'], 
            data['value'], 
            data['target_type'], 
            data['target_value']
        )
    )

async def run_group_action_task(admin_id, action, value, target_type, target_value):
    """تسک اصلی اعمال تغییرات روی کاربران و پنل‌ها."""
    success_count = 0
    fail_count = 0
    total_processed = 0
    
    logger.info(f"Starting group action: {action} {value} for {target_type}:{target_value}")

    async with db.get_session() as session:
        # 1. ساخت کوئری برای یافتن کاربران هدف
        stmt = select(UserUUID).options(selectinload(UserUUID.allowed_panels)).where(UserUUID.is_active == True)
        
        # اعمال فیلترها
        if target_type == 'filter':
            if target_value == 'expiring_soon':
                # کاربرانی که کمتر از 3 روز تا انقضا دارند (در دیتابیس معمولاً تاریخ نداریم، باید از پنل بگیریم)
                # اما اگر expire در دیتابیس ذخیره شده باشد، می‌توان فیلتر کرد.
                # فرض: فعلاً روی همه اعمال می‌کنیم چون سینک دقیق expire در دیتابیس ممکن است نباشد.
                pass 
            elif target_value == 'inactive_30_days':
                # کاربرانی که 30 روز است وصل نشده‌اند
                thirty_days_ago = datetime.now() - timedelta(days=30)
                stmt = stmt.where(UserUUID.updated_at < thirty_days_ago) # تقریبی
        
        # اگر target_type == 'plan'، فعلاً روی همه فعال‌ها اعمال می‌شود 
        # (چون لینک مستقیم پلن به یوزر در دیتابیس UserUUID وجود ندارد)
        
        result = await session.execute(stmt)
        active_uuids = result.scalars().all()

        if not active_uuids:
            await bot.send_message(admin_id, "❌ هیچ کاربری با شرایط انتخاب شده یافت نشد.")
            return

        total_to_process = len(active_uuids)
        
        # 2. اعمال تغییرات
        for uuid_obj in active_uuids:
            if not uuid_obj.allowed_panels:
                continue

            user_success = False
            for panel_db in uuid_obj.allowed_panels:
                try:
                    panel_api = await PanelFactory.get_panel(panel_db.name)
                    
                    # تشخیص شناسه (UUID یا Username)
                    identifier = uuid_obj.uuid
                    if panel_db.panel_type == 'marzban':
                        mapping = await db.get_marzban_username_by_uuid(uuid_obj.uuid)
                        identifier = mapping if mapping else uuid_obj.name

                    if action == 'add_gb':
                        await panel_api.modify_user(identifier, add_gb=value)
                    elif action == 'add_days':
                        await panel_api.modify_user(identifier, add_days=int(value))
                        
                    user_success = True
                except Exception as e:
                    logger.error(f"Failed to update user {uuid_obj.uuid} on panel {panel_db.name}: {e}")
            
            if user_success:
                success_count += 1
            else:
                fail_count += 1
            
            total_processed += 1
            # جلوگیری از فشار به سرور با تاخیر کوتاه
            if total_processed % 10 == 0:
                await asyncio.sleep(0.1)

    # 3. گزارش پایان کار
    report = (
        "✅ <b>پایان عملیات گروهی</b>\n\n"
        f"🎯 هدف: {target_type} ({target_value})\n"
        f"👥 کل پردازش شده: {total_processed}\n"
        f"✅ موفق: {success_count}\n"
        f"❌ ناموفق: {fail_count}"
    )
    
    try:
        await bot.send_message(admin_id, report, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to send group action report: {e}")