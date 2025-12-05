# bot/admin_handlers/group_actions.py

import asyncio
import logging
from telebot import types
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.bot_instance import bot
from bot.keyboards import admin_menu
from bot.database import db
from bot.db.base import UserUUID, Panel
from bot.services.panels import PanelFactory  # فرض بر این است که این کلاس وجود دارد

logger = logging.getLogger(__name__)

# استیت برای ذخیره مراحل عملیات گروهی
ga_state = {}

@bot.callback_query_handler(func=lambda call: call.data == "admin:group_actions_menu")
async def ga_menu(call: types.CallbackQuery):
    """نمایش منوی انتخاب نوع عملیات"""
    await bot.edit_message_text(
        "⚙️ <b>مدیریت گروهی کاربران</b>\n\n"
        "چه تغییری می‌خواهید روی کاربران اعمال کنید؟",
        call.from_user.id,
        call.message.message_id,
        reply_markup=admin_menu.group_actions_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:ga_action:"))
async def ga_select_action(call: types.CallbackQuery):
    """انتخاب نوع اکشن (افزودن حجم یا زمان)"""
    action = call.data.split(":")[2]
    ga_state[call.from_user.id] = {"action": action}
    
    action_name = "حجم (GB)" if action == "add_gb" else "زمان (روز)"
    
    msg = await bot.send_message(
        call.from_user.id,
        f"🔢 لطفاً مقدار <b>{action_name}</b> را وارد کنید:\n"
        "(مثلاً برای ۱۰ گیگابایت عدد 10 را بفرستید)",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, ga_get_value)

async def ga_get_value(message: types.Message):
    """دریافت مقدار عددی"""
    try:
        value = float(message.text)
        if message.chat.id not in ga_state:
            await bot.send_message(message.chat.id, "❌ نشست منقضی شده. دوباره تلاش کنید.")
            return

        ga_state[message.chat.id]["value"] = value
        
        # نمایش تاییدیه نهایی
        data = ga_state[message.chat.id]
        action_str = "افزودن حجم" if data['action'] == "add_gb" else "افزودن زمان"
        
        await bot.send_message(
            message.chat.id,
            f"⚠️ <b>تایید نهایی</b>\n\n"
            f"عملیات: {action_str}\n"
            f"مقدار: {value}\n"
            f"هدف: تمام کاربران فعال\n\n"
            "آیا مطمئن هستید؟ این عملیات غیرقابل بازگشت است.",
            reply_markup=admin_menu.confirm_group_action_menu(),
            parse_mode='HTML'
        )
    except ValueError:
        await bot.send_message(message.chat.id, "❌ لطفاً فقط عدد وارد کنید.")

@bot.callback_query_handler(func=lambda call: call.data == "admin:ga_confirm")
async def ga_execute(call: types.CallbackQuery):
    """اجرای عملیات"""
    admin_id = call.from_user.id
    data = ga_state.get(admin_id)
    if not data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد.")
        return

    # پاک کردن استیت
    del ga_state[admin_id]

    await bot.edit_message_text(
        "🚀 عملیات در پس‌زمینه شروع شد...\nنتیجه نهایی گزارش خواهد شد.",
        admin_id,
        call.message.message_id
    )

    # اجرای تسک در پس‌زمینه
    asyncio.create_task(run_group_action_task(admin_id, data['action'], data['value']))

async def run_group_action_task(admin_id, action, value):
    """تسک اصلی اعمال تغییرات روی پنل‌ها"""
    success_count = 0
    fail_count = 0
    
    async with db.get_session() as session:
        # ۱. دریافت تمام UUID های فعال به همراه پنل‌های مجازشان
        # استفاده از selectinload برای جلوگیری از ارور Lazy Loading
        stmt = (
            select(UserUUID)
            .where(UserUUID.is_active == True)
            .options(selectinload(UserUUID.allowed_panels))
        )
        result = await session.execute(stmt)
        active_uuids = result.scalars().all()

        if not active_uuids:
            await bot.send_message(admin_id, "❌ هیچ کاربر فعالی یافت نشد.")
            return

        for uuid_obj in active_uuids:
            try:
                # اگر کاربر به هیچ پنلی وصل نیست، رد شو
                if not uuid_obj.allowed_panels:
                    continue

                # ۲. اعمال تغییر روی تمام پنل‌هایی که کاربر در آن‌ها وجود دارد
                for panel_db in uuid_obj.allowed_panels:
                    try:
                        # اتصال به API پنل
                        panel_api = await PanelFactory.get_panel(panel_db.name)
                        
                        if action == 'add_gb':
                            await panel_api.modify_user(uuid_obj.uuid, add_gb=value)
                        elif action == 'add_days':
                            await panel_api.modify_user(uuid_obj.uuid, add_days=int(value))
                            
                        # اینجا می‌توانید دیتابیس محلی را هم آپدیت کنید (اختیاری)
                        # مثلا: uuid_obj.limit_gb += value
                        
                    except Exception as e:
                        logger.error(f"Failed to update user {uuid_obj.uuid} on panel {panel_db.name}: {e}")
                        fail_count += 1
                    else:
                        success_count += 1
                        
            except Exception as e:
                logger.error(f"Error processing uuid {uuid_obj.id}: {e}")
                fail_count += 1
            
            # تاخیر خیلی کوتاه برای جلوگیری از فشار به سرور
            await asyncio.sleep(0.05)

    # ۳. گزارش پایان کار
    report = (
        "✅ <b>پایان عملیات گروهی</b>\n\n"
        f"تعداد موفق: {success_count}\n"
        f"تعداد خطا: {fail_count}"
    )
    await bot.send_message(admin_id, report, parse_mode='HTML')