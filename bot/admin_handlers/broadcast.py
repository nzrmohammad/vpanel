# bot/admin_handlers/broadcast.py

import asyncio
import logging
from telebot import types
from sqlalchemy import select, update
from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, BroadcastTask

logger = logging.getLogger(__name__)

# استیت موقت فقط برای مرحله انتخاب (قبل از ثبت در دیتابیس)
broadcast_setup = {}

@bot.callback_query_handler(func=lambda call: call.data == "admin:broadcast")
async def broadcast_menu_handler(call: types.CallbackQuery):
    """نمایش منوی انتخاب هدف"""
    await bot.edit_message_text(
        "📣 <b>پیام همگانی (نسخه پایدار)</b>\n\nلطفاً مخاطبین پیام را انتخاب کنید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=admin_menu.broadcast_target_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin:broadcast_target:"))
async def broadcast_get_message(call: types.CallbackQuery):
    """دریافت پیام از ادمین"""
    target_type = call.data.split(":")[2]
    broadcast_setup[call.from_user.id] = {"target": target_type}
    
    await bot.send_message(
        call.from_user.id,
        f"📣 مخاطبین انتخابی: <b>{target_type}</b>\n\n"
        "لطفاً پیام خود را ارسال کنید (متن، عکس، ...):",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(call.message, process_broadcast_message)

async def process_broadcast_message(message: types.Message):
    """ذخیره پیام و نمایش تاییدیه"""
    admin_id = message.chat.id
    if admin_id not in broadcast_setup:
        return

    broadcast_setup[admin_id]['message_id'] = message.message_id
    broadcast_setup[admin_id]['chat_id'] = message.chat.id

    await bot.send_message(
        admin_id,
        "⚠️ <b>تایید نهایی ارسال</b>\n\nآیا مطمئن هستید؟ این عملیات در دیتابیس ثبت شده و قابل پیگیری خواهد بود.",
        reply_markup=admin_menu.confirm_broadcast_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin:broadcast_confirm")
async def broadcast_confirm(call: types.CallbackQuery):
    """شروع عملیات: ثبت در دیتابیس و اجرا"""
    admin_id = call.from_user.id
    setup_data = broadcast_setup.pop(admin_id, None)
    
    if not setup_data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد.")
        return

    # 1. ایجاد رکورد در دیتابیس
    async with db.get_session() as session:
        task = BroadcastTask(
            admin_id=admin_id,
            target_type=setup_data['target'],
            message_id=setup_data['message_id'],
            from_chat_id=setup_data['chat_id'],
            status='in_progress'
        )
        session.add(task)
        await session.commit()
        # رفرش برای گرفتن ID تسک
        await session.refresh(task)
        task_id = task.id

    await bot.edit_message_text(
        f"🚀 <b>برادکست #{task_id} شروع شد...</b>\nوضعیت در دیتابیس ذخیره می‌شود.",
        admin_id,
        call.message.message_id,
        parse_mode='HTML'
    )

    # اجرای تسک در پس‌زمینه با پاس دادن ID دیتابیس
    asyncio.create_task(run_persistent_broadcast(task_id))

async def run_persistent_broadcast(task_id: int):
    """اجرای برادکست با قابلیت آپدیت وضعیت در دیتابیس"""
    async with db.get_session() as session:
        # دریافت اطلاعات تسک
        task = await session.get(BroadcastTask, task_id)
        if not task: return
        
        target = task.target_type
        msg_id = task.message_id
        from_chat = task.from_chat_id
        admin_id = task.admin_id

        # دریافت کاربران بر اساس هدف
        user_ids = []
        if target == 'all':
            stmt = select(User.user_id)
            result = await session.execute(stmt)
            user_ids = result.scalars().all()
        elif target == 'active': # کاربرانی که سرویس فعال دارند
            stmt = select(User.user_id).join(UserUUID).where(UserUUID.is_active == True).distinct()
            result = await session.execute(stmt)
            user_ids = result.scalars().all()
        # (سایر شرط‌ها را می‌توانید اضافه کنید)

        # آپدیت تعداد کل
        task.total_users = len(user_ids)
        await session.commit()

    # حلقه ارسال
    success = 0
    failed = 0
    
    for i, uid in enumerate(user_ids):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
            success += 1
        except Exception as e:
            # اگر کاربر بلاک کرده باشد
            failed += 1
        
        # هر 20 پیام یکبار دیتابیس را آپدیت می‌کنیم (برای کاهش فشار)
        if i % 20 == 0:
            async with db.get_session() as session:
                await session.execute(
                    update(BroadcastTask)
                    .where(BroadcastTask.id == task_id)
                    .values(sent_count=success, failed_count=failed)
                )
                await session.commit()
        
        await asyncio.sleep(0.05) # جلوگیری از Flood

    # پایان کار: آپدیت نهایی
    async with db.get_session() as session:
        await session.execute(
            update(BroadcastTask)
            .where(BroadcastTask.id == task_id)
            .values(status='completed', sent_count=success, failed_count=failed)
        )
        await session.commit()

    # اطلاع به ادمین
    try:
        await bot.send_message(
            admin_id,
            f"✅ <b>پایان برادکست #{task_id}</b>\n\n"
            f"📤 موفق: {success}\n"
            f"❌ ناموفق: {failed}\n"
            f"👥 کل: {len(user_ids)}",
            parse_mode='HTML'
        )
    except:
        pass