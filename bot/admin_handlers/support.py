# bot/admin_handlers/support.py

import logging
import asyncio
from telebot import types
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.config import ADMIN_IDS
from bot.language import get_string

logger = logging.getLogger(__name__)

CACHED_MAIN_GROUP_ID = None

async def update_cached_group_id():
    global CACHED_MAIN_GROUP_ID
    val = await db.get_config('main_group_id')
    CACHED_MAIN_GROUP_ID = int(val) if val and str(val) != '0' else None

# =============================================================================
# 1. هندلر پاسخ دادن ادمین
# =============================================================================
@bot.message_handler(func=lambda m: m.chat.type in ['supergroup', 'group'], content_types=['text', 'photo', 'video', 'voice', 'document', 'sticker', 'audio', 'animation'])
async def handle_admin_reply_in_group(message: types.Message):
    global CACHED_MAIN_GROUP_ID
    
    if CACHED_MAIN_GROUP_ID is None:
        await update_cached_group_id()
    
    if message.chat.id != CACHED_MAIN_GROUP_ID:
        return

    if not message.reply_to_message:
        return

    # پیدا کردن تیکت
    reply_msg = message.reply_to_message
    ticket = await db.get_ticket_by_admin_message_id(reply_msg.message_id)
    
    if not ticket:
        return

    user_id = ticket['user_id']
    
    # استخراج آیدی پیام فوروارد شده
    forwarded_msg_id = None
    if reply_msg.entities:
        for ent in reply_msg.entities:
            if ent.type == "text_link" and ent.url and "tg://ticket_msg?id=" in ent.url:
                try:
                    forwarded_msg_id = int(ent.url.split("=")[1])
                except: 
                    pass
                break
    
    try:
        # ارسال کپی پیام برای کاربر
        kb_user = types.InlineKeyboardMarkup()
        kb_user.add(
            types.InlineKeyboardButton("✍️ پاسخ مجدد", callback_data="support:user_reply"),
            types.InlineKeyboardButton("✅ ختم گفتگو", callback_data="support:user_close")
        )

        await bot.copy_message(
            chat_id=user_id, 
            from_chat_id=message.chat.id, 
            message_id=message.message_id,
            reply_markup=kb_user
        )
        
        # دریافت زمان حذف
        delete_delay = int(await db.get_config('ticket_auto_delete_time', 60))

        # ویرایش پیام تیکت به "پاسخ داده شد"
        try:
            original_text = reply_msg.text or reply_msg.caption or ""
            lines = original_text.split('\n')
            if len(lines) > 0:
                lines[0] = "✅ *پاسخ داده شد* (حذف خودکار...)"
            
            new_text = "\n".join(lines)
            
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=reply_msg.message_id,
                text=new_text,
                reply_markup=None,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Could not edit ticket message: {e}")

        # حذف پیام ادمین
        try: await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except: pass

        # اسکژول کردن حذف پیام ربات + پیام فوروارد شده
        if delete_delay > 0:
            asyncio.create_task(
                delete_ticket_chain(message.chat.id, reply_msg.message_id, forwarded_msg_id, delete_delay)
            )

    except Exception as e:
        logger.error(f"Failed to handle admin reply: {e}")
        await bot.reply_to(message, f"❌ خطا: {str(e)}")

async def delete_ticket_chain(chat_id, bot_msg_id, fwd_msg_id, delay):
    """حذف پیام‌های سمت ادمین"""
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, bot_msg_id)
    except: pass
    if fwd_msg_id:
        try: await bot.delete_message(chat_id, fwd_msg_id)
        except: pass

# =============================================================================
# 2. هندلر دکمه بستن تیکت توسط ادمین
# =============================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('admin:ticket:close:'))
async def close_ticket_callback(call: types.CallbackQuery):
    try:
        ticket = await db.get_ticket_by_admin_message_id(call.message.message_id)
        
        forwarded_msg_id = None
        if call.message.entities:
            for ent in call.message.entities:
                if ent.type == "text_link" and ent.url and "tg://ticket_msg?id=" in ent.url:
                    try: forwarded_msg_id = int(ent.url.split("=")[1])
                    except: pass
                    break

        if ticket:
            await db.close_ticket(ticket['id'])
            target_user_id = int(call.data.split(':')[-1])
            
            # ویرایش پیام ادمین به بسته شد
            try:
                await bot.edit_message_text(
                    chat_id=call.message.chat.id, 
                    message_id=call.message.message_id, 
                    text="🔒 [تیکت بسته شد] (حذف خودکار...)", 
                    reply_markup=None
                )
            except: pass
            
            # دریافت زمان حذف
            delete_delay = int(await db.get_config('ticket_auto_delete_time', 60))

            # ✅ اصلاح: فقط حذف پیام بسته شدن (بدون ارسال منو)
            try:
                msg_text = "🔒 گفتگوی پشتیبانی توسط مدیریت بسته شد."
                if delete_delay > 0:
                     # متن تغییر کرد: فقط نوشته حذف می‌شود، نه بازگشت به منو
                     msg_text += f"\n\n⏳ _(حذف پیام تا {delete_delay} ثانیه دیگر...)_"
                
                sent_msg = await bot.send_message(target_user_id, msg_text, parse_mode="Markdown")
                
                if delete_delay > 0:
                    asyncio.create_task(
                        user_delete_message_only(target_user_id, sent_msg.message_id, delete_delay)
                    )
            except Exception as e:
                logger.error(f"Error sending closed msg to user: {e}")
            
            # حذف سمت ادمین
            if delete_delay > 0:
                asyncio.create_task(
                    delete_ticket_chain(call.message.chat.id, call.message.message_id, forwarded_msg_id, delete_delay)
                )
            
        await bot.answer_callback_query(call.id, "تیکت بسته شد.")
    except Exception as e:
        logger.error(f"Error closing ticket: {e}")

async def user_delete_message_only(chat_id, msg_id, delay):
    """✅ فقط پیام را حذف می‌کند و منو را ارسال نمی‌کند"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, msg_id)
    except: pass