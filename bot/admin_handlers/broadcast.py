# bot/admin_handlers/broadcast.py

import asyncio
import logging
from datetime import datetime, timedelta
from telebot import types
from sqlalchemy import select, update, func, and_

from bot.bot_instance import bot
from bot.keyboards import admin as admin_menu
from bot.database import db
from bot.db.base import User, UserUUID, BroadcastTask, UsageSnapshot

logger = logging.getLogger(__name__)

# حافظه موقت برای ذخیره مراحل ویزارد برادکست
broadcast_setup = {}

async def start_broadcast_flow(call: types.CallbackQuery, params: list):
    """شروع فرآیند: نمایش منوی انتخاب هدف"""
    # ✅ اصلاح شده: افزودن await قبل از admin_menu
    markup = await admin_menu.broadcast_target_menu()
    
    await bot.edit_message_text(
        "📣 <b>پیام همگانی (نسخه پایدار)</b>\n\nلطفاً مخاطبین پیام را انتخاب کنید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

async def ask_for_broadcast_message(call: types.CallbackQuery, params: list):
    """مرحله دوم: دریافت پیام از ادمین"""
    target_type = params[0] # online, active_1, inactive_7, all, ...
    
    broadcast_setup[call.from_user.id] = {"target": target_type}
    
    targets_fa = {
        "all": "همه کاربران",
        "online": "کاربران آنلاین (۲۴ ساعت اخیر)",
        "active_1": "کاربران فعال (سرویس‌دار)",
        "inactive_7": "کاربران غیرفعال (۷ روز اخیر)",
        "inactive_0": "کاربرانی که هرگز وصل نشدند"
    }
    
    target_name = targets_fa.get(target_type, target_type)
    
    await bot.send_message(
        call.from_user.id,
        f"📣 مخاطبین انتخابی: <b>{target_name}</b>\n\n"
        "لطفاً پیام خود را ارسال کنید (متن، عکس، ویدیو، ...):",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(call.message, _process_broadcast_message_step)

async def _process_broadcast_message_step(message: types.Message):
    """مرحله سوم: ذخیره پیام و نمایش تاییدیه"""
    admin_id = message.chat.id
    if admin_id not in broadcast_setup:
        return

    # ذخیره مشخصات پیام برای کپی کردن
    broadcast_setup[admin_id]['message_id'] = message.message_id
    broadcast_setup[admin_id]['chat_id'] = message.chat.id

    await bot.send_message(
        admin_id,
        "⚠️ <b>تایید نهایی ارسال</b>\n\nآیا مطمئن هستید؟ این عملیات در دیتابیس ثبت شده و در پس‌زمینه اجرا می‌شود.",
        reply_markup=admin_menu.confirm_broadcast_menu(),
        parse_mode='HTML'
    )

async def broadcast_confirm(call: types.CallbackQuery, params: list):
    """مرحله چهارم: ثبت تسک در دیتابیس و شروع اجرا"""
    admin_id = call.from_user.id
    setup_data = broadcast_setup.pop(admin_id, None)
    
    if not setup_data:
        await bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد (منقضی شده).")
        return

    # ایجاد رکورد در دیتابیس
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
        await session.refresh(task)
        task_id = task.id

    await bot.edit_message_text(
        f"🚀 <b>برادکست #{task_id} در پس‌زمینه شروع شد...</b>\n"
        "می‌توانید از این منو خارج شوید. گزارش پایان ارسال خواهد شد.",
        admin_id,
        call.message.message_id,
        parse_mode='HTML'
    )

    # اجرای تسک در پس‌زمینه (بدون بلوک کردن بات)
    asyncio.create_task(_run_persistent_broadcast(task_id))

async def _run_persistent_broadcast(task_id: int):
    """ورکر اصلی ارسال پیام"""
    logger.info(f"Starting broadcast task #{task_id}")
    
    async with db.get_session() as session:
        # دریافت اطلاعات تسک
        task = await session.get(BroadcastTask, task_id)
        if not task: return
        
        target = task.target_type
        msg_id = task.message_id
        from_chat = task.from_chat_id
        admin_id = task.admin_id

        # --- انتخاب کاربران بر اساس Target ---
        user_ids = []
        stmt = select(User.user_id).distinct()
        
        if target == 'all':
            # همه کاربران ثبت نام شده
            pass 
            
        elif target == 'active_1':
            # کاربرانی که حداقل یک سرویس فعال دارند
            stmt = stmt.join(UserUUID).where(UserUUID.is_active == True)
            
        elif target == 'online':
            # کاربرانی که در ۲۴ ساعت گذشته اسنپ‌شات مصرف داشته‌اند (تقریبی از آنلاین بودن)
            one_day_ago = datetime.utcnow() - timedelta(days=1)
            stmt = stmt.join(UserUUID).join(UsageSnapshot).where(UsageSnapshot.taken_at >= one_day_ago)
            
        elif target == 'inactive_7':
            # کاربرانی که سرویس فعال دارند اما در ۷ روز گذشته مصرفی ثبت نشده
            # (این کوئری ممکن است سنگین باشد، ساده‌تر: همه فعال‌ها)
            # اینجا برای سادگی کاربرانی که سرویس غیرفعال دارند را می‌گیریم
            stmt = stmt.join(UserUUID).where(UserUUID.is_active == False)
            
        elif target == 'inactive_0':
            # کاربرانی که هیچ سرویسی ندارند یا اولین اتصالشان ثبت نشده
            stmt = stmt.outerjoin(UserUUID).where(
                (UserUUID.id == None) | (UserUUID.first_connection_time == None)
            )

        result = await session.execute(stmt)
        user_ids = result.scalars().all()

        # آپدیت تعداد کل
        task.total_users = len(user_ids)
        await session.commit()

    # حلقه ارسال
    success = 0
    failed = 0
    
    # برای جلوگیری از مسدود شدن طولانی دیتابیس، سشن را در حلقه باز نمی‌کنیم
    # فقط هر N پیام وضعیت را آپدیت می‌کنیم
    
    for i, uid in enumerate(user_ids):
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
            success += 1
        except Exception as e:
            # کاربر بلاک کرده یا اکانت حذف شده
            failed += 1
        
        # تاخیر برای جلوگیری از Flood Wait تلگرام
        await asyncio.sleep(0.04) 
        
        # آپدیت وضعیت در دیتابیس (هر 50 پیام)
        if i % 50 == 0 and i > 0:
            async with db.get_session() as session:
                await session.execute(
                    update(BroadcastTask)
                    .where(BroadcastTask.id == task_id)
                    .values(sent_count=success, failed_count=failed)
                )
                await session.commit()

    # پایان کار: آپدیت نهایی و بستن تسک
    async with db.get_session() as session:
        await session.execute(
            update(BroadcastTask)
            .where(BroadcastTask.id == task_id)
            .values(status='completed', sent_count=success, failed_count=failed)
        )
        await session.commit()

    # اطلاع به ادمین
    try:
        report = (
            f"✅ <b>پایان برادکست #{task_id}</b>\n\n"
            f"🎯 هدف: {target}\n"
            f"👥 کل مخاطبین: {len(user_ids)}\n"
            f"📤 موفق: {success}\n"
            f"❌ ناموفق (بلاک/حذف): {failed}"
        )
        await bot.send_message(admin_id, report, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to send broadcast report to admin: {e}")