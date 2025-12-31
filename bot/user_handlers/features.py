# bot/user_handlers/features.py

import logging
import jdatetime
from telebot import types
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user_menu 
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.language import get_string
from bot.formatters import user_formatter
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

# مدیریت وضعیت دریافت تاریخ تولد
feature_states = {}

# --- 1. Referral System ---
@bot.callback_query_handler(func=lambda call: call.data == "referral:info")
async def referral_info_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang_code = await db.get_user_language(user_id)
    bot_username = (await bot.get_me()).username
    
    text = await user_formatter.referral_page(user_id, bot_username, lang_code)
    
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
    )
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# --- 2. Request Service ---
@bot.callback_query_handler(func=lambda call: call.data == "request_service")
async def request_service_handler(call: types.CallbackQuery):
    user = call.from_user
    msg = f"👤 Service Request from:\n{user.first_name} (@{user.username})\nID: {user.id}"
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg)
        except: pass
        
    await bot.answer_callback_query(call.id, "✅ درخواست ارسال شد.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "coming_soon")
async def coming_soon(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 به زودی...", show_alert=True)

# --- 3. Birthday Gift ---
@bot.callback_query_handler(func=lambda call: call.data == "birthday_gift")
async def handle_birthday_gift_request(call: types.CallbackQuery):
    uid = call.from_user.id
    msg_id = call.message.message_id
    lang_code = await db.get_user_language(uid)
    
    user_data = await db.user(uid)
    
    # اگر تاریخ تولد قبلاً ثبت شده باشد
    if user_data and user_data.get('birthday'):
        text = user_formatter.birthday_status_text(user_data)
        # استفاده از تابع simple_back_menu که در کلاس وجود دارد
        kb = await user_menu.simple_back_menu("back", lang_code)
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        # درخواست تاریخ تولد
        raw_text = get_string("prompt_birthday", lang_code)
        prompt = escape_markdown(raw_text).replace("YYYY/MM/DD", "`YYYY/MM/DD`")
        
        # ✅ اینجا قبلاً ارور داشتید. الان چون user_menu آبجکت کلاس است، متد user_cancel_action را دارد
        kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
        
        await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
        
        feature_states[uid] = {'step': 'wait_date', 'msg_id': msg_id}

@bot.message_handler(func=lambda m: m.from_user.id in feature_states)
async def process_birthday_date(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    lang_code = await db.get_user_language(uid)
    
    state = feature_states.pop(uid, None)
    if not state: return
    original_msg_id = state['msg_id']
    
    try: await bot.delete_message(uid, message.message_id)
    except: pass

    if text.startswith('/'): return

    try:
        gregorian_date = jdatetime.datetime.strptime(text, '%Y/%m/%d').togregorian().date()
        await db.update_user_birthday(uid, gregorian_date)
        
        success = escape_markdown(get_string("birthday_success", lang_code))
        kb = await user_menu.simple_back_menu("back", lang_code)
        
        await _safe_edit(uid, original_msg_id, success, reply_markup=kb, parse_mode="MarkdownV2")
        
    except ValueError:
        error = escape_markdown(get_string("birthday_invalid_format", lang_code))
        await bot.send_message(uid, error, parse_mode="MarkdownV2")
        feature_states[uid] = state # بازگرداندن وضعیت برای تلاش مجدد