# bot/admin_handlers/broadcast.py

import asyncio
import logging
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, update, func

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, BroadcastTask, UsageSnapshot

logger = logging.getLogger(__name__)

# حافظه موقت محلی (چون برادکست معمولاً تک مرحله‌ای است و نیاز به پایداری طولانی ندارد)
broadcast_setup = {}

async def start_broadcast_flow(call: types.CallbackQuery, params: list):
    """شروع فرآیند: نمایش منوی انتخاب هدف"""
    uid = call.from_user.id
    # پاک کردن حافظه قبلی اگر مانده باشد
    if uid in broadcast_setup: del broadcast_setup[uid]
    
    markup = await admin_menu.broadcast_target_menu()
    
    await bot.edit_message_text(
        "📣 <b>پیام همگانی</b>\n\nلطفاً مخاطبین پیام را انتخاب کنید:",
        uid,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

async def ask_for_broadcast_message(call: types.CallbackQuery, params: list):
    """مرحله دوم: دریافت پیام از ادمین"""
    target_type = params[0]
    uid = call.from_user.id
    
    broadcast_setup[uid] = {"target": target_type}
    
    targets_fa = {
        "all": "همه کاربران",
        "online": "کاربران آنلاین (۲۴س)",
        "active_1": "کاربران فعال",
        "inactive_7": "غیرفعال (هفتگی)",
        "inactive_0": "هرگز متصل نشده"
    }
    target_name = targets_fa.get(target_type, target_type)
    
    await bot.send_message(
        uid,
        f"📣 مخاطبین: <b>{target_name}</b>\n\n"
        "لطفاً پیام خود را ارسال کنید (متن، عکس، ویدیو...):",
        parse_mode='HTML',
        reply_markup=types.ForceReply() # برای راحتی کار
    )
    
    # ثبت هندلر مرحله بعد
    bot.register_next_step_handler(call.message, _process_broadcast_message_step)

async def _process_broadcast_message_step(message: types.Message):
    """مرحله سوم: ذخیره پیام و نمایش تاییدیه"""
    uid = message.from_user.id
    
    # اگر کاربر دستور لغو فرستاد
    if message.text and message.text == '/cancel':
        if uid in broadcast_setup: del broadcast_setup[uid]
        await bot.send_message(uid, "❌ عملیات لغو شد.")
        return

    if uid not in broadcast_setup:
        await bot.send_message(uid, "❌ نشست منقضی شده. دوباره تلاش کنید.")
        return

    broadcast_setup[uid]['message_id'] = message.message_id
    broadcast_setup[uid]['chat_id'] = message.chat.id

    markup = await admin_menu.confirm_broadcast_menu()
    
    await bot.send_message(
        uid,
        "⚠️ <b>تایید نهایی ارسال</b>\n\nآیا مطمئن هستید؟",
        reply_markup=markup,
        parse_mode='HTML'
    )

async def broadcast_confirm(call: types.CallbackQuery, params: list):
    """مرحله چهارم: ثبت و اجرا"""
    uid = call.from_user.id
    data = broadcast_setup.pop(uid, None)
    
    if not data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد.")
        return

    # ثبت در دیتابیس
    async with db.get_session() as session:
        task = BroadcastTask(
            admin_id=uid,
            target_type=data['target'],
            message_id=data['message_id'],
            from_chat_id=data['chat_id'],
            status='in_progress'
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = task.id

    await bot.edit_message_text(
        f"🚀 <b>برادکست #{task_id} شروع شد...</b>\nگزارش نهایی ارسال می‌شود.",
        uid,
        call.message.message_id,
        parse_mode='HTML'
    )

    # اجرا در پس‌زمینه
    asyncio.create_task(_run_persistent_broadcast(task_id))

async def _run_persistent_broadcast(task_id: int):
    """تسک اصلی ارسال"""
    async with db.get_session() as session:
        task = await session.get(BroadcastTask, task_id)
        if not task: return
        
        target = task.target_type
        msg_id = task.message_id
        from_chat = task.from_chat_id
        admin_id = task.admin_id

        # انتخاب کاربران
        stmt = select(User.user_id).distinct()
        if target == 'active_1':
            stmt = stmt.join(UserUUID).where(UserUUID.is_active == True)
        elif target == 'online':
            yesterday = datetime.utcnow() - timedelta(days=1)
            stmt = stmt.join(UserUUID).join(UsageSnapshot).where(UsageSnapshot.taken_at >= yesterday)
        # سایر فیلترها...

        result = await session.execute(stmt)
        user_ids = result.scalars().all()
        
        task.total_users = len(user_ids)
        await session.commit()

    success, failed = 0, 0
    
    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
            success += 1
        except:
            failed += 1
        await asyncio.sleep(0.05) # جلوگیری از Flood Limit

    # آپدیت نهایی
    async with db.get_session() as session:
        await session.execute(
            update(BroadcastTask).where(BroadcastTask.id == task_id)
            .values(status='completed', sent_count=success, failed_count=failed)
        )
        await session.commit()

    try:
        await bot.send_message(admin_id, f"✅ <b>پایان برادکست #{task_id}</b>\n📤 موفق: {success}\n❌ ناموفق: {failed}", parse_mode='HTML')
    except: pass