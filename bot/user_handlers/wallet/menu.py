# bot/user_handlers/wallet/menu.py

from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.database import db
from bot.utils.date_helpers import to_shamsi
from bot.utils.formatters import escape_markdown
from .states import user_payment_states
from bot.formatters import user_formatter

# --- منوی اصلی کیف پول ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:main")
async def wallet_main_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # پاکسازی وضعیت قبلی اگر وجود داشت
    if user_id in user_payment_states:
        del user_payment_states[user_id]

    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    text = "💰 *کیف پول*"
    markup = await user_menu.wallet_main_menu(balance, lang)
    
    try:
        await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='MarkdownV2')
    except:
        await bot.send_message(user_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# --- تاریخچه تراکنش‌ها ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:history")
async def wallet_history_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    transactions = await db.get_wallet_history(user_id, limit=10)
    text = user_formatter.wallet_history_list(transactions)

    kb = await user_menu.wallet_history_menu(lang)
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=kb, parse_mode='MarkdownV2')

@bot.callback_query_handler(func=lambda call: call.data == "show_addons")
async def placeholder_handler(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 این قابلیت به زودی فعال می‌شود.", show_alert=True)