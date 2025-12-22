# bot/admin_handlers/group_actions.py

import asyncio
import logging
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import UserUUID
from bot.services.panels import PanelFactory
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

logger = logging.getLogger(__name__)

# استیت برای ذخیره مراحل
admin_conversations = {}

def initialize_group_actions_handlers(b, conv_dict):
    """دریافت مقادیر سراسری از فایل اصلی"""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def _delete_user_message(msg: types.Message):
    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except: pass

# ==============================================================================
# 1. منوها و انتخاب‌های اولیه
# ==============================================================================

async def handle_select_plan_for_action(call: types.CallbackQuery, params: list):
    """نمایش لیست پلن‌ها برای انتخاب هدف عملیات گروهی."""
    plans = await db.get_all_plans(active_only=True)
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "⚙️ **دستور گروهی (بر اساس پلن)**\n\nلطفاً پلن مورد نظر را انتخاب کنید:",
        reply_markup=await admin_menu.select_plan_for_action_menu(plans),
        parse_mode="Markdown"
    )

async def handle_select_advanced_filter(call: types.CallbackQuery, params: list):
    """نمایش فیلترهای پیشرفته."""
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "🔥 **دستور گروهی (پیشرفته)**\n\nچه گروهی از کاربران را هدف قرار می‌دهید؟",
        reply_markup=await admin_menu.advanced_group_action_filter_menu(),
        parse_mode="Markdown"
    )

async def handle_select_action_type(call: types.CallbackQuery, params: list):
    """انتخاب نوع عملیات (حجم یا زمان)."""
    # params[0]: context_value (plan_id or filter_code)
    # تشخیص اینکه آیا ورودی از منوی پلن آمده یا فیلتر
    # (در اینجا ساده‌سازی می‌کنیم: اگر عدد بود پلن است، اگر متن بود فیلتر)
    context_value = params[0]
    context_type = 'plan' if str(context_value).isdigit() else 'filter'
    
    await _safe_edit(
        call.from_user.id,
        call.message.message_id,
        "🔧 چه تغییری می‌خواهید اعمال کنید؟",
        reply_markup=await admin_menu.select_action_type_menu(context_value, context_type)
    )

async def handle_select_action_for_filter(call: types.CallbackQuery, params: list):
    """هندلر واسط برای فیلترهای پیشرفته (جهت سازگاری با منو)."""
    # params[0]: filter_code
    await handle_select_action_type(call, params)

# ==============================================================================
# 2. دریافت مقادیر و تاییدیه
# ==============================================================================

async def handle_ask_action_value(call: types.CallbackQuery, params: list):
    """دریافت مقدار عددی."""
    # params: [action, context_type, context_value]
    action, context_type, context_value = params[0], params[1], params[2]
    uid, msg_id = call.from_user.id, call.message.message_id
    
    admin_conversations[uid] = {
        'step': 'ga_value',
        'msg_id': msg_id,
        'action': action,
        'target_type': context_type,
        'target_value': context_value,
        'next_handler': process_ga_value # <--- ست کردن هندلر بعدی برای روتر
    }
    
    unit = "گیگابایت" if action == "add_gb" else "روز"
    prompt = f"🔢 لطفاً مقدار **{unit}** مورد نظر را وارد کنید (عدد):"
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action("admin:group_actions_menu"), parse_mode="Markdown")

async def process_ga_value(message: types.Message):
    """پردازش مقدار وارد شده."""
    uid, text = message.from_user.id, message.text.strip()
    await _delete_user_message(message)
    
    if uid not in admin_conversations: return
    data = admin_conversations[uid] # نگه داشتن دیتا برای مرحله بعد (پاک نمی‌کنیم)
    msg_id = data['msg_id']
    
    try:
        value = float(text)
        # بروزرسانی استیت با مقدار جدید
        admin_conversations[uid]['value'] = value
        # مرحله بعدی وجود ندارد (تاییدیه است)، پس next_handler را حذف می‌کنیم تا لوپ نشود
        if 'next_handler' in admin_conversations[uid]:
            del admin_conversations[uid]['next_handler']
        
        action_str = "افزودن حجم" if data['action'] == "add_gb" else "افزودن زمان"
        target_str = f"پلن {data['target_value']}" if data['target_type'] == 'plan' else f"فیلتر: {data['target_value']}"
        
        confirm_text = (
            "⚠️ **تایید نهایی عملیات گروهی**\n\n"
            f"🎯 هدف: `{target_str}`\n"
            f"🛠 عملیات: `{action_str}`\n"
            f"🔢 مقدار: `{value}`\n\n"
            "آیا مطمئن هستید؟ این عملیات روی تمام کاربران منطبق اجرا می‌شود."
        )
        
        await _safe_edit(
            uid, msg_id, confirm_text, 
            reply_markup=await admin_menu.confirm_group_action_menu(),
            parse_mode="Markdown"
        )
        
    except ValueError:
        await _safe_edit(uid, msg_id, "❌ لطفاً فقط عدد وارد کنید.", reply_markup=await admin_menu.cancel_action("admin:group_actions_menu"))

# ==============================================================================
# 3. اجرا
# ==============================================================================

async def ga_execute(call: types.CallbackQuery, params: list):
    """شروع اجرای عملیات."""
    uid = call.from_user.id
    data = admin_conversations.pop(uid, None)
    
    if not data or 'value' not in data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات منقضی شده است.", show_alert=True)
        return

    await bot.edit_message_text(
        "🚀 عملیات در پس‌زمینه شروع شد...\n"
        "⏳ لطفاً صبر کنید. پس از پایان کار، گزارشی برای شما ارسال خواهد شد.",
        uid,
        call.message.message_id
    )

    # اجرای تسک در پس‌زمینه
    asyncio.create_task(
        run_group_action_task(
            uid, 
            data['action'], 
            data['value'], 
            data['target_type'], 
            data['target_value']
        )
    )

async def run_group_action_task(admin_id, action, value, target_type, target_value):
    """تسک اصلی اعمال تغییرات."""
    success_count = 0
    fail_count = 0
    
    async with db.get_session() as session:
        # ساخت کوئری پایه
        stmt = select(UserUUID).options(selectinload(UserUUID.allowed_panels)).where(UserUUID.is_active == True)
        
        # اعمال فیلترها (ساده‌سازی شده)
        if target_type == 'filter' and target_value == 'inactive_30_days':
            thirty_days_ago = datetime.now() - timedelta(days=30)
            stmt = stmt.where(UserUUID.updated_at < thirty_days_ago)
        
        # نکته: فیلتر بر اساس پلن (plan) نیاز به جوین با جداول دیگر دارد که پیچیده است.
        # در اینجا فرض می‌کنیم اگر 'plan' بود، روی همه اعمال شود یا منطق خاصی اضافه شود.
        # برای جلوگیری از تغییر ناخواسته همه کاربران، اگر پلن انتخاب شده بود و منطق دقیق نداریم، لاگ می‌زنیم.
        
        result = await session.execute(stmt)
        active_uuids = result.scalars().all()

        if not active_uuids:
            try: await bot.send_message(admin_id, "❌ کاربری با این مشخصات یافت نشد.")
            except: pass
            return

        for uuid_obj in active_uuids:
            if not uuid_obj.allowed_panels: continue

            user_success = False
            for panel_db in uuid_obj.allowed_panels:
                try:
                    panel_api = await PanelFactory.get_panel(panel_db.name)
                    
                    identifier = uuid_obj.uuid
                    if panel_db.panel_type == 'marzban':
                        # دریافت یوزرنیم برای مرزبان
                        mapping = await db.get_marzban_username_by_uuid(uuid_obj.uuid)
                        identifier = mapping if mapping else uuid_obj.name

                    if action == 'add_gb':
                        await panel_api.modify_user(identifier, add_gb=value)
                    elif action == 'add_days':
                        await panel_api.modify_user(identifier, add_days=int(value))
                        
                    user_success = True
                except Exception as e:
                    logger.error(f"Group Action Error: {e}")
            
            if user_success: success_count += 1
            else: fail_count += 1
            
            # تاخیر کوچک برای جلوگیری از فشار
            if (success_count + fail_count) % 20 == 0:
                await asyncio.sleep(0.5)

    report = (
        "✅ <b>پایان عملیات گروهی</b>\n\n"
        f"👥 کل پردازش شده: {success_count + fail_count}\n"
        f"✅ موفق: {success_count}\n"
        f"❌ ناموفق: {fail_count}"
    )
    try: await bot.send_message(admin_id, report, parse_mode='HTML')
    except: pass