# bot/user_handlers/support.py

import logging
import asyncio
from telebot import types

from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.language import get_string

logger = logging.getLogger(__name__)

# دیکشنری وضعیت
support_states = {}

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def handle_support_request(call: types.CallbackQuery):
    """شروع پروسه ارسال تیکت"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    lang_code = await db.get_user_language(uid)
    
    prompt = (
        f"*{escape_markdown('📝 تیکت پشتیبانی جدید')}*\n\n"
        f"{escape_markdown('لطفاً پیام، عکس یا ویدیوی خود را ارسال کنید.')}\n"
        f"{escape_markdown('پیام شما مستقیماً برای تیم پشتیبانی ارسال می‌شود.')}"
    )
    
    kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
    
    support_states[uid] = {'original_msg_id': msg_id}

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice', 'audio', 'sticker'], func=lambda m: m.from_user.id in support_states)
async def process_support_ticket(message: types.Message):
    """دریافت پیام کاربر و ارسال به تاپیک پشتیبانی"""
    uid = message.from_user.id
    
    # خروج با دستور
    if message.text and message.text.startswith('/'):
        if uid in support_states: del support_states[uid]
        return

    state = support_states.pop(uid)
    original_msg_id = state.get('original_msg_id')
    lang_code = await db.get_user_language(uid)

    # 1. دریافت تنظیمات از دیتابیس
    main_group_id = await db.get_config('main_group_id', default='0')
    support_topic_id = await db.get_config('topic_id_support', default='0')

    # اگر گروه تنظیم نشده باشد
    if str(main_group_id) == '0':
        await _safe_edit(uid, original_msg_id, "❌ سیستم پشتیبانی موقتاً غیرفعال است.", reply_markup=None)
        return

    chat_id = int(main_group_id)
    thread_id = int(support_topic_id) if str(support_topic_id) != '0' else None

    # حذف پیام کاربر برای تمیزی چت (اختیاری)
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    # نمایش "در حال ارسال"
    await _safe_edit(uid, original_msg_id, "⏳ در حال ارسال...", reply_markup=None)

    try:
        user_info = message.from_user
        user_data = await db.user(uid)
        wallet_balance = user_data.get('wallet_balance', 0.0) if user_data else 0.0
        
        # 2. فروارد پیام به تاپیک مشخص
        forwarded_msg = await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=uid,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
        
        # 3. ساخت کپشن اطلاعات برای ادمین
        info_caption = (
            f"👤 *New Ticket*\n"
            f"From: {escape_markdown(user_info.first_name)} "
            f"{f'(@{escape_markdown(user_info.username)})' if user_info.username else ''}\n"
            f"🆔 `{uid}`\n"
            f"💰 Balance: `{wallet_balance:,.0f}`"
        )
        
        kb_admin = types.InlineKeyboardMarkup()
        kb_admin.add(
            types.InlineKeyboardButton("🚫 بستن تیکت", callback_data=f"admin:ticket:close:{uid}"),
            types.InlineKeyboardButton("👤 پروفایل", callback_data=f"admin:user_info:{uid}")
        )

        # ارسال پیام اطلاعات روی پیام فروارد شده (در همان تاپیک)
        admin_msg = await bot.send_message(
            chat_id=chat_id, 
            text=info_caption, 
            parse_mode="MarkdownV2", 
            reply_to_message_id=forwarded_msg.message_id,
            reply_markup=kb_admin,
            message_thread_id=thread_id
        )

        # 4. ثبت در دیتابیس (برای اینکه بفهمیم ریپلای ادمین مال کدوم یوزره)
        await db.create_support_ticket(uid, admin_msg.message_id)
        
        # 5. پیام موفقیت به کاربر
        success_text = (
            f"✅ *پیام شما ارسال شد.*\n\n"
            f"{escape_markdown('پاسخ ادمین در همینجا برای شما ارسال خواهد شد.')}"
        )
        kb_back = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
        )
        await _safe_edit(uid, original_msg_id, success_text, reply_markup=kb_back, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Support Error: {e}")
        await _safe_edit(uid, original_msg_id, "❌ خطا در ارسال پیام.", reply_markup=None)