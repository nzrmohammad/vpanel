# bot/user_handlers/wallet/menu.py

from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.database import db
from bot.utils.date_helpers import to_shamsi
from bot.utils.formatters import escape_markdown
from .states import user_payment_states

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
    
    text = "📜 *تاریخچه تراکنش‌ها*\n"
    if not transactions:
        text += "──────────────────\nتراکنشی یافت نشد"
    else:
        for t in transactions:
            amount = t.get('amount', 0)
            raw_desc = t.get('description') or t.get('type', 'Unknown')
            raw_date = to_shamsi(t.get('transaction_date'), include_time=True)
            
            icon = "➕" if amount > 0 else "➖"
            amount_str = f"{int(abs(amount)):,}"
            
            text += (
                "──────────────────\n"
                f"{icon} {escape_markdown(amount_str)} تومان \n"
                f" {escape_markdown(raw_desc)} \n"
                f" {escape_markdown(raw_date)}\n"
            )

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn("wallet:main", lang))
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=kb, parse_mode='MarkdownV2')

# --- تنظیمات و دکمه‌های دیگر ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:settings")
async def wallet_settings_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    user_data = await db.user(user_id)
    markup = await user_menu.wallet_settings_menu(user_data.get('auto_renew', False), lang)
    await bot.edit_message_text("⚙️ **تنظیمات تمدید خودکار**", user_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "wallet:toggle_auto_renew")
async def toggle_auto_renew_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await db.user(user_id)
    new_status = not user_data.get('auto_renew', False)
    await db.update_auto_renew_setting(user_id, new_status)
    await wallet_settings_handler(call)
    await bot.answer_callback_query(call.id, f"تمدید خودکار {'✅ فعال' if new_status else '❌ غیرفعال'} شد")

@bot.callback_query_handler(func=lambda call: call.data in ["show_addons", "wallet:transfer_start", "wallet:gift_start"])
async def placeholder_handler(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 این قابلیت به زودی فعال می‌شود.", show_alert=True)