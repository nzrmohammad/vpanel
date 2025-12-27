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
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

# دیکشنری وضعیت
support_states = {}

# =============================================================================
# 1. شروع تیکت
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def handle_support_request(call: types.CallbackQuery):
    await start_support_session(call.from_user.id, call.message.message_id, is_reply=False)

async def start_support_session(user_id, msg_id, is_reply=False):
    lang_code = await db.get_user_language(user_id)
    
    if is_reply:
        title = "✍️ ارسال پاسخ"
        desc = "لطفاً پاسخ خود را بنویسید."
    else:
        title = "📝 تیکت پشتیبانی جدید"
        desc = "لطفاً پیام، عکس یا ویدیوی خود را ارسال کنید."
    
    prompt = (
        f"*{escape_markdown(title)}*\n\n"
        f"{escape_markdown(desc)}\n"
        f"{escape_markdown('پیام شما مستقیماً برای تیم پشتیبانی ارسال می‌شود.')}\n\n"
        f"{escape_markdown('برای انصراف دکمه زیر را بزنید.')}"
    )
    
    kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
    try:
        await _safe_edit(user_id, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
    except:
        await bot.send_message(user_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
    
    support_states[user_id] = {'original_msg_id': msg_id, 'is_reply': is_reply}

# =============================================================================
# 2. دریافت پیام کاربر
# =============================================================================
@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice', 'audio', 'sticker'], func=lambda m: m.from_user.id in support_states)
async def process_support_ticket(message: types.Message):
    uid = message.from_user.id
    
    if message.text and message.text.startswith('/'):
        if uid in support_states: del support_states[uid]
        return

    state = support_states.pop(uid)
    original_msg_id = state.get('original_msg_id')
    is_reply = state.get('is_reply', False)
    lang_code = await db.get_user_language(uid)

    # تنظیمات
    main_group_id = await db.get_config('main_group_id', default='0')
    support_topic_id = await db.get_config('topic_id_support', default='0')

    if str(main_group_id) == '0':
        err_txt = escape_markdown("❌ سیستم پشتیبانی موقتاً غیرفعال است.")
        await _safe_edit(uid, original_msg_id, err_txt, reply_markup=None, parse_mode="MarkdownV2")
        return

    chat_id = int(main_group_id)
    thread_id = int(support_topic_id) if str(support_topic_id) != '0' else None

    # پیام انتظار
    waiting_txt = "⏳ در حال ارسال به مدیریت..." 
    await _safe_edit(uid, original_msg_id, waiting_txt, reply_markup=None, parse_mode=None)

    try:
        user_info = message.from_user
        user_data = await db.user(uid)
        
        raw_balance = user_data.get('wallet_balance', 0.0) if user_data else 0.0
        safe_balance = escape_markdown("{:,.0f}".format(raw_balance))

        # 1. فوروارد پیام
        forwarded_msg = await bot.forward_message(
            chat_id=chat_id,
            from_chat_id=uid,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
        
        # حذف پیام کاربر از ربات
        try: await bot.delete_message(uid, message.message_id)
        except: pass

        # 2. ساخت متن اطلاعات
        if is_reply:
            header = "↩️ *پاسخ کاربر \\(ادامه تیکت\\)*"
        else:
            header = "📩 *تیکت جدید*"

        if user_info.username:
            username_line = f"🆔 یوزرنیم: @{escape_markdown(user_info.username)}"
        else:
            username_line = f"🆔 یوزرنیم: \\-"

        hidden_id_link = f"[\u200b](tg://ticket_msg?id={forwarded_msg.message_id})"

        info_caption = (
            f"{header}\n"
            f"👤 کاربر: {escape_markdown(user_info.first_name)}\n"
            f"{username_line}\n"
            f"🔢 شناسه عددی: `{uid}`\n"
            f"💰 موجودی: `{safe_balance} تومان`\n"
            f"{hidden_id_link}" 
        )
        
        kb_admin = types.InlineKeyboardMarkup()
        # ✅ اصلاح: فقط دکمه بستن تیکت (حذف دکمه پروفایل)
        kb_admin.add(
            types.InlineKeyboardButton("🚫 بستن تیکت", callback_data=f"admin:ticket:close:{uid}")
        )

        # ارسال پیام اطلاعات
        admin_msg = await bot.send_message(
            chat_id=chat_id, 
            text=info_caption, 
            parse_mode="MarkdownV2", 
            reply_to_message_id=forwarded_msg.message_id,
            reply_markup=kb_admin,
            message_thread_id=thread_id,
            disable_web_page_preview=True
        )

        await db.create_support_ticket(uid, admin_msg.message_id)
        
        # 3. پیام موفقیت
        delay_seconds = 10
        
        success_text = (
            f"✅ *پیام شما با موفقیت ارسال شد\\.*\n\n"
            f"{escape_markdown('پاسخ مدیریت برای شما ارسال خواهد شد.')}\n\n"
            f"⏳ {escape_markdown(f'بازگشت به منوی اصلی تا {delay_seconds} ثانیه دیگر...')}"
        )
        
        kb_back = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)} (الان برگرد)", callback_data="back")
        )
        
        await _safe_edit(uid, original_msg_id, success_text, reply_markup=kb_back, parse_mode="MarkdownV2")
        
        # حذف و بازگشت به منو
        asyncio.create_task(delete_and_return_home(uid, original_msg_id, delay_seconds, lang_code))

    except Exception as e:
        logger.error(f"Support Error: {e}")
        error_message = escape_markdown("❌ خطا در برقراری ارتباط. لطفاً دوباره تلاش کنید.")
        if "chat not found" in str(e).lower():
            error_message = escape_markdown("❌ خطای سیستمی: گروه پشتیبانی یافت نشد.")
        await _safe_edit(uid, original_msg_id, error_message, reply_markup=None, parse_mode="MarkdownV2")

async def delete_and_return_home(chat_id, message_id, delay, lang_code):
    """صبر می‌کند، پیام را حذف می‌کند و منوی اصلی را می‌فرستد"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except: pass 
    
    try:
        is_admin = chat_id in ADMIN_IDS
        markup = await user_menu.main(is_admin, lang_code)
        welcome_text = get_string('main_menu_title', lang_code) 
        if not welcome_text or welcome_text.startswith('Error'):
            welcome_text = "🏠 *منوی اصلی*" if lang_code == 'fa' else "🏠 *Main Menu*"

        await bot.send_message(chat_id, welcome_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error returning to main menu: {e}")
        await bot.send_message(chat_id, "🏠", reply_markup=None)

# =============================================================================
# 3. دکمه‌های کاربر
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "support:user_reply")
async def user_reply_to_admin(call: types.CallbackQuery):
    await start_support_session(call.from_user.id, call.message.message_id, is_reply=True)

@bot.callback_query_handler(func=lambda call: call.data == "support:user_close")
async def user_close_ticket(call: types.CallbackQuery):
    try: await bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    await bot.answer_callback_query(call.id, "✅ گفتگو بسته شد.", show_alert=False)