# bot/admin_handlers/support.py

import logging
import asyncio
from telebot import types
from bot.bot_instance import bot
from bot.database import db

logger = logging.getLogger(__name__)

# کش برای جلوگیری از درخواست زیاد به دیتابیس
CACHED_MAIN_GROUP_ID = None

async def update_cached_group_id():
    """بروزرسانی آیدی گروه اصلی از دیتابیس"""
    global CACHED_MAIN_GROUP_ID
    val = await db.get_config('main_group_id')
    CACHED_MAIN_GROUP_ID = int(val) if val and str(val) != '0' else None

# --- هندلر پاسخ دادن ادمین ---
@bot.message_handler(func=lambda m: m.chat.type in ['supergroup', 'group'], content_types=['text', 'photo', 'video', 'voice', 'document', 'sticker', 'audio'])
async def handle_admin_reply_in_group(message: types.Message):
    """
    اگر ادمین در سوپرگروه اصلی (هر تاپیکی) روی تیکت ریپلای کرد،
    پیام را برای کاربر بفرست.
    """
    global CACHED_MAIN_GROUP_ID
    
    # اگر کش خالی است، پر کن
    if CACHED_MAIN_GROUP_ID is None:
        await update_cached_group_id()
    
    # 1. چک کن پیام داخل گروه اصلی باشه
    if message.chat.id != CACHED_MAIN_GROUP_ID:
        return

    # 2. حتما باید ریپلای باشه
    if not message.reply_to_message:
        return

    # 3. پیدا کردن تیکت از روی پیامی که بهش ریپلای شده
    reply_to_id = message.reply_to_message.message_id
    ticket = await db.get_ticket_by_admin_message_id(reply_to_id)
    
    if not ticket:
        return

    user_id = ticket['user_id']
    
    try:
        # ارسال کپی پیام ادمین برای کاربر
        await bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.message_id)
        
        # تایید ارسال (و حذف خودکار بعد از ۳ ثانیه)
        sent = await bot.reply_to(message, "✅ ارسال شد.")
        await asyncio.sleep(3)
        try: await bot.delete_message(message.chat.id, sent.message_id)
        except: pass

    except Exception as e:
        logger.error(f"Failed to send reply to user {user_id}: {e}")
        # اگر کاربر بلاک کرده باشه یا مشکلی باشه، اینجا لاگ میشه

# --- هندلر دکمه بستن تیکت ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin:ticket:close:'))
async def close_ticket_callback(call: types.CallbackQuery):
    try:
        # بستن تیکت در دیتابیس (صرفاً تغییر وضعیت)
        ticket = await db.get_ticket_by_admin_message_id(call.message.message_id)
        if ticket:
            await db.close_ticket(ticket['id'])
            
            # ویرایش پیام ادمین برای نشان دادن وضعیت بسته شده
            current_text = call.message.caption or call.message.text or ""
            new_text = current_text + "\n\n✅ [بسته شد]"
            
            try:
                # اگر پیام عکس‌دار بود caption ادیت میشه، اگر متن بود text
                if call.message.caption:
                    await bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=new_text, reply_markup=None)
                else:
                    await bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=new_text, reply_markup=None)
            except: pass
            
        await bot.answer_callback_query(call.id, "تیکت بسته شد.")
    except Exception as e:
        logger.error(f"Error closing ticket: {e}")

# تابع خالی برای سازگاری (اگر در main صدا زده شده)
def initialize_support_handlers(bot_instance, conv_dict):
    pass