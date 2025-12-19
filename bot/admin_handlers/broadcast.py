# bot/admin_handlers/broadcast.py

import asyncio
import logging
import time  # برای هماهنگی با سیستم Timeout در admin_router
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, update

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, BroadcastTask, UsageSnapshot

logger = logging.getLogger(__name__)

async def start_broadcast_flow(call: types.CallbackQuery, params: list):
    """شروع فرآیند: نمایش منوی انتخاب هدف"""
    uid = call.from_user.id
    # پاک کردن وضعیت قبلی در صورت وجود برای جلوگیری از تداخل
    if uid in bot.context_state:
        del bot.context_state[uid]
    
    markup = await admin_menu.broadcast_target_menu()
    
    await bot.edit_message_text(
        "📣 *پیام همگانی*\n\nلطفاً مخاطبین پیام را انتخاب کنید:",
        uid,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='MarkdownV2'
    )

async def ask_for_broadcast_message(call: types.CallbackQuery, params: list):
    """مرحله دوم: دریافت پیام از ادمین (ویرایش پیام فعلی و افزودن دکمه بازگشت)"""
    target_type = params[0]
    uid = call.from_user.id
    
    targets_fa = {
        "all": "همه کاربران",
        "online": "کاربران آنلاین \(۲۴س\)",
        "active_1": "کاربران فعال",
        "inactive_7": "غیرفعال \(هفتگی\)",
        "inactive_0": "هرگز متصل نشده"
    }
    target_name = targets_fa.get(target_type, target_type)

    # ایجاد دکمه برای بازگشت به منوی پیام همگانی
    markup = types.InlineKeyboardMarkup()
    # تغییر کال‌بک به admin:broadcast برای بازگشت به مرحله اول
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به منوی قبل", callback_data="admin:broadcast"))

    # ویرایش پیام فعلی طبق درخواست شما
    await bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text=(
            f"🎯 هدف انتخاب شده: *{target_name}*\n\n"
            "لطفاً پیام خود را ارسال کنید \(متن، عکس، ویدیو\.\.\.\):"
        ),
        reply_markup=markup,
        parse_mode='MarkdownV2'
    )
    
    # ثبت وضعیت در context_state برای هندل کردن پیام بعدی توسط روتر
    bot.context_state[uid] = {
        "target": target_type,
        "timestamp": time.time(),
        "next_handler": _process_broadcast_message_step
    }

async def _process_broadcast_message_step(message: types.Message):
    """مرحله سوم: دریافت محتوا و نمایش تاییدیه نهایی"""
    uid = message.from_user.id
    
    if uid not in bot.context_state:
        return

    state = bot.context_state[uid]
    state['message_id'] = message.message_id
    state['chat_id'] = message.chat.id
    state['next_handler'] = None  # پایان دریافت پیام متنی

    markup = await admin_menu.confirm_broadcast_menu()
    
    await bot.send_message(
        uid,
        "⚠️ *تایید نهایی ارسال*\n\nآیا از ارسال این محتوا برای مخاطبین مطمئن هستید؟",
        reply_markup=markup,
        parse_mode='MarkdownV2'
    )

async def broadcast_confirm(call: types.CallbackQuery, params: list):
    """مرحله چهارم: ثبت تسک و شروع ارسال"""
    uid = call.from_user.id
    data = bot.context_state.pop(uid, None)
    
    if not data or 'message_id' not in data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد\.", show_alert=True)
        return

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
        f"🚀 *برادکست \#{task_id} شروع شد\.\.\.*\nگزارش نهایی ارسال می‌شود\.",
        uid,
        call.message.message_id,
        parse_mode='MarkdownV2'
    )

    # اجرای عملیات ارسال در پس‌زمینه
    asyncio.create_task(_run_persistent_broadcast(task_id))

async def _run_persistent_broadcast(task_id: int):
    """تسک اصلی ارسال پیام‌ها"""
    async with db.get_session() as session:
        task = await session.get(BroadcastTask, task_id)
        if not task: return
        
        target = task.target_type
        msg_id = task.message_id
        from_chat = task.from_chat_id
        admin_id = task.admin_id

        stmt = select(User.user_id).distinct()
        if target == 'active_1':
            stmt = stmt.join(UserUUID).where(UserUUID.is_active == True)
        elif target == 'online':
            yesterday = datetime.utcnow() - timedelta(days=1)
            stmt = stmt.join(UserUUID).join(UsageSnapshot).where(UsageSnapshot.taken_at >= yesterday)
        
        result = await session.execute(stmt)
        user_ids = result.scalars().all()
        
        task.total_users = len(user_ids)
        await session.commit()

    success, failed = 0, 0
    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # جلوگیری از محدودیت ارسال تلگرام

    async with db.get_session() as session:
        await session.execute(
            update(BroadcastTask).where(BroadcastTask.id == task_id)
            .values(status='completed', sent_count=success, failed_count=failed)
        )
        await session.commit()

    try:
        await bot.send_message(
            admin_id, 
            f"✅ *پایان برادکست \#{task_id}*\n\n📤 موفق: {success}\n❌ ناموفق: {failed}", 
            parse_mode='MarkdownV2'
        )
    except Exception:
        pass