# bot/user_handlers/sharing.py

import logging
from telebot import types
from sqlalchemy import select, update, delete
from datetime import datetime

from bot.bot_instance import bot
from bot.database import db
from bot.db.base import User, UserUUID, SharedRequest, Panel
from bot.services.panels import PanelFactory
from bot.utils.formatters import escape_markdown

logger = logging.getLogger(__name__)

# --- 1. تابع شروع درخواست (این را در کد خود صدا بزنید) ---

async def handle_uuid_conflict(message, uuid_str: str):
    """
    زمانی که کاربر UUID تکراری وارد می‌کند، این تابع را صدا بزنید.
    """
    requester_id = message.from_user.id
    requester_user = message.from_user
    
    # 1. پیدا کردن صاحب اصلی اکانت
    async with db.get_session() as session:
        # پیدا کردن سرویس
        stmt = select(UserUUID).where(UserUUID.uuid == uuid_str)
        res = await session.execute(stmt)
        existing_uuid = res.scalars().first()
        
        if not existing_uuid:
            await bot.reply_to(message, "❌ سرویس یافت نشد.")
            return

        owner_id = existing_uuid.user_id
        
        # اگر کاربر خودش صاحب اکانت است
        if owner_id == requester_id:
            await bot.reply_to(message, "⚠️ شما قبلاً این سرویس را در لیست خود دارید.")
            return

        # 2. دریافت اطلاعات صاحب اکانت برای نمایش (در صورت رد شدن)
        owner_obj = await session.get(User, owner_id)
        # owner_name اینجا استفاده نمیشه فعلا، ولی داریمش

    # 3. ارسال پیام به درخواست‌دهنده (Requester)
    # نکته: از \\. استفاده می‌کنیم تا ارور سینتکس ندهد
    req_text = (
        "⛔️ *این اکانت متعلق به کاربر دیگری است*\\.\n\n"
        "درخواست شما برای استفاده مشترک به ایشان ارسال شد\\. لطفاً منتظر تایید بمانید\\.\\.\\."
    )
    req_markup = types.InlineKeyboardMarkup()
    req_markup.add(types.InlineKeyboardButton("❌ لغو درخواست", callback_data=f"share:cancel:{uuid_str}"))
    
    sent_req = await bot.send_message(requester_id, req_text, parse_mode='MarkdownV2', reply_markup=req_markup)

    # 4. ارسال پیام به صاحب اکانت (Owner)
    # دریافت اطلاعات درخواست‌دهنده
    r_name = escape_markdown(requester_user.first_name or "Unknown")
    r_id = requester_user.id
    r_username = f"@{escape_markdown(requester_user.username)}" if requester_user.username else "ندارد"
    uuid_name = escape_markdown(existing_uuid.name or "Unknown")

    owner_text = (
        f"⚠️ *یک کاربر دیگر قصد دارد به اکانت «{uuid_name}» شما متصل شود*\\.\n\n"
        f"👤 *اطلاعات درخواست دهنده:*\n"
        f"نام: {r_name}\n"
        f"آیدی: `{r_id}`\n"
        f"یوزرنیم: {r_username}\n\n"
        f"❓ آیا اجازه می‌دهید این کاربر به صورت مشترک از این اکانت استفاده کند؟"
    )
    
    owner_markup = types.InlineKeyboardMarkup()
    owner_markup.add(
        types.InlineKeyboardButton("✅ بله، اجازه می‌دهم", callback_data=f"share:accept:{sent_req.message_id}"),
        types.InlineKeyboardButton("❌ خیر", callback_data=f"share:reject:{sent_req.message_id}")
    )
    
    sent_owner = await bot.send_message(owner_id, owner_text, parse_mode='MarkdownV2', reply_markup=owner_markup)

    # 5. ذخیره درخواست در دیتابیس
    async with db.get_session() as session:
        new_req = SharedRequest(
            requester_id=requester_id,
            owner_id=owner_id,
            uuid_str=str(uuid_str),
            requester_msg_id=sent_req.message_id,
            owner_msg_id=sent_owner.message_id,
            status='pending'
        )
        session.add(new_req)
        await session.commit()


# --- 2. هندلر دکمه‌های صاحب اکانت (Accept / Reject) ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('share:accept:') or call.data.startswith('share:reject:'))
async def handle_owner_decision(call: types.CallbackQuery):
    action, req_msg_id = call.data.split(':')[1], int(call.data.split(':')[2])
    owner_id = call.from_user.id
    
    async with db.get_session() as session:
        # پیدا کردن درخواست
        stmt = select(SharedRequest).where(SharedRequest.requester_msg_id == req_msg_id)
        res = await session.execute(stmt)
        req = res.scalars().first()
        
        if not req or req.status != 'pending':
            try:
                await bot.answer_callback_query(call.id, "این درخواست منقضی یا تعیین تکلیف شده است.", show_alert=True)
                await bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            return

        requester_id = req.requester_id
        uuid_str = req.uuid_str
        
        # دریافت اطلاعات صاحب (برای ارسال به درخواست‌دهنده)
        owner_user = await session.get(User, owner_id)
        owner_name = escape_markdown(owner_user.first_name if owner_user else "Unknown")
        
        # ✅ حل مشکل ارور 400: اسکیپ کردن متن پیام قبلی
        safe_old_text = escape_markdown(call.message.text)
        
        if action == 'accept':
            # ---------------- قبول درخواست ----------------
            
            # 1. اضافه کردن UUID برای درخواست‌دهنده
            srv_stmt = select(UserUUID).where(UserUUID.uuid == uuid_str)
            srv_res = await session.execute(srv_stmt)
            orig_srv = srv_res.scalars().first()
            orig_name = orig_srv.name if orig_srv else "Shared Service"
            
            # ثبت در دیتابیس
            new_uuid_obj = UserUUID(
                user_id=requester_id,
                uuid=uuid_str,
                name=orig_name,
                is_active=True,
                allowed_categories=orig_srv.allowed_categories if orig_srv else []
            )
            session.add(new_uuid_obj)
            
            # لینک کردن پنل‌ها (اختیاری: کپی کردن پنل‌های سرویس اصلی)
            if orig_srv and orig_srv.allowed_panels:
                # چون رابطه many-to-many است، اینجا فقط آبجکت را اضافه می‌کنیم
                # نکته: برای سادگی فرض می‌کنیم اینسرت خودکار انجام می‌شود یا در sync بعدی درست می‌شود
                pass

            req.status = 'accepted'
            await session.commit()
            
            # 2. ادیت پیام صاحب (Owner)
            try:
                await bot.edit_message_text(
                    f"{safe_old_text}\n\n✅ *درخواست تایید شد و دسترسی داده شد\\.*",
                    owner_id, call.message.message_id, parse_mode='MarkdownV2', reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error editing owner msg: {e}")
            
            # 3. پیام به درخواست‌دهنده
            try:
                await bot.edit_message_text(
                    "✅ *تبریک\\! درخواست شما تایید شد\\.*\nاکانت به لیست سرویس‌های شما اضافه گردید\\.",
                    requester_id, req.requester_msg_id, parse_mode='MarkdownV2', reply_markup=None
                )
            except: pass

        else:
            # ---------------- رد درخواست ----------------
            req.status = 'rejected'
            
            # دریافت نام سرویس برای پیام رد
            srv_stmt = select(UserUUID).where(UserUUID.uuid == uuid_str)
            srv_res = await session.execute(srv_stmt)
            orig_srv = srv_res.scalars().first()
            acc_name_safe = escape_markdown(orig_srv.name if orig_srv else "Unknown")

            await session.commit()
            
            # 1. ادیت پیام صاحب (Owner)
            try:
                await bot.edit_message_text(
                    f"{safe_old_text}\n\n❌ *درخواست رد شد\\.*",
                    owner_id, call.message.message_id, parse_mode='MarkdownV2', reply_markup=None
                )
            except Exception as e:
                logger.error(f"Error editing owner msg: {e}")
            
            # 2. پیام به درخواست‌دهنده (با اطلاعات صاحب)
            reject_text = (
                f"❌ متاسفانه درخواست شما برای اکانت «{acc_name_safe}» توسط کاربر زیر رد شد:\n\n"
                f"نام: {owner_name}\n"
                f"آیدی: `{owner_id}`"
            )
            try:
                await bot.edit_message_text(
                    reject_text,
                    requester_id, req.requester_msg_id, parse_mode='MarkdownV2', reply_markup=None
                )
            except: pass

    await bot.answer_callback_query(call.id)


# --- 3. هندلر لغو درخواست توسط درخواست‌دهنده ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('share:cancel:'))
async def handle_request_cancel(call: types.CallbackQuery):
    uuid_str = call.data.split(':')[2]
    requester_id = call.from_user.id
    
    async with db.get_session() as session:
        # پیدا کردن آخرین درخواست پندینگ
        stmt = select(SharedRequest).where(
            SharedRequest.requester_id == requester_id,
            SharedRequest.uuid_str == uuid_str,
            SharedRequest.status == 'pending'
        ).order_by(SharedRequest.id.desc())
        
        res = await session.execute(stmt)
        req = res.scalars().first()
        
        if req:
            req.status = 'cancelled'
            
            # حذف پیام برای صاحب اکانت
            try:
                await bot.delete_message(req.owner_id, req.owner_msg_id)
            except: pass
            
            await session.commit()
            
            try:
                await bot.edit_message_text(
                    "❌ درخواست شما لغو شد\\.",
                    requester_id, call.message.message_id, parse_mode='MarkdownV2', reply_markup=None
                )
            except: pass
        else:
            await bot.answer_callback_query(call.id, "درخواست فعالی یافت نشد.", show_alert=True)
            try:
                await bot.delete_message(requester_id, call.message.message_id)
            except: pass