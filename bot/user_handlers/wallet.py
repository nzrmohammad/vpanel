# bot/user_handlers/wallet.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot.language import get_string
from bot.config import CARD_PAYMENT_INFO
from bot.services.panels import PanelFactory
import logging
import uuid as uuid_lib

logger = logging.getLogger(__name__)

# --- منوی اصلی کیف پول ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:main")
async def wallet_main_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    # ✅ اصلاح نام متد و افزودن await
    lang = await db.get_user_language(user_id)
    
    # ✅ دریافت موجودی از متد user (چون get_user_balance وجود نداشت)
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    # ✅ اصلاح نام متد تراکنش‌ها
    transactions = await db.get_wallet_history(user_id, limit=5)
    
    text = user_formatter.wallet_page(balance, transactions, lang)
    
    # ✅ افزودن await برای منوی async
    markup = await user_menu.wallet_main_menu(balance, lang)
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

# --- شارژ حساب ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:charge")
async def wallet_charge_methods(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id) # ✅ await
    
    # ✅ افزودن await
    markup = await user_menu.payment_options_menu(lang)
    
    await bot.edit_message_text(
        get_string('prompt_select_payment_method', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_card_details")
async def show_card_details(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id) # ✅ await
    
    info = CARD_PAYMENT_INFO
    text = (
        f"💳 <b>{get_string('payment_card_details_title', lang)}</b>\n\n"
        f"🏦 <b>{info.get('bank_name')}</b>\n"
        f"👤 <b>{info.get('card_holder')}</b>\n"
        f"🔢 <code>{info.get('card_number')}</code>\n\n"
        f"⚠️ {get_string('payment_card_instructions', lang)}"
    )
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=user_menu.back_btn("wallet:charge", lang),
        parse_mode='HTML'
    )

# --- خرید سرویس (Buy Plan) ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:buy_confirm:'))
async def buy_plan_confirm(call: types.CallbackQuery):
    try:
        plan_id = int(call.data.split(':')[2])
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی.")
        return

    user_id = call.from_user.id
    lang = await db.get_user_language(user_id) # ✅ await

    selected_plan = await db.get_plan_by_id(plan_id)
    if not selected_plan:
        await bot.answer_callback_query(call.id, "❌ پلن یافت نشد.")
        return

    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    text = user_formatter.purchase_confirmation(
        plan_name=selected_plan['name'],
        price=selected_plan['price'],
        current_balance=balance,
        lang_code=lang
    )
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if balance >= selected_plan['price']:
        markup.add(types.InlineKeyboardButton("✅ تایید و پرداخت", callback_data=f"wallet:do_buy:{selected_plan['id']}"))
    else:
        markup.add(types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="wallet:charge"))

    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="view_plans"))
    
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:do_buy:'))
async def execute_purchase(call: types.CallbackQuery):
    try:
        plan_id = int(call.data.split(':')[2])
        user_id = call.from_user.id
        lang = await db.get_user_language(user_id) # ✅ await
        
        plan = await db.get_plan_by_id(plan_id)
        if not plan: return
        
        user_data = await db.user(user_id)
        balance = user_data.get('wallet_balance', 0)
        
        if balance < plan['price']:
            await bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
            return

        await bot.edit_message_text("⏳ در حال فعال‌سازی سرویس...", user_id, call.message.message_id)

        target_panel_name = "server1" # باید منطق انتخاب سرور را بعداً تکمیل کنید
        
        panel_api = await PanelFactory.get_panel(target_panel_name)
        
        random_suffix = str(uuid_lib.uuid4())[:8]
        username = f"u{user_id}_{random_suffix}"
        
        new_service = await panel_api.add_user(username, plan['volume_gb'], plan['days'])
        
        if new_service:
            await db.update_wallet_balance(user_id, -plan['price'], 'purchase', f"خرید پلن {plan['name']}")
            
            service_uuid = new_service.get('uuid') or username 
            
            await db.add_uuid(user_id=user_id, uuid_str=service_uuid, name=username)
            
            # ثبت دسترسی‌ها
            uuid_id = await db.get_uuid_id_by_uuid(service_uuid)
            if uuid_id and plan.get('allowed_categories'):
                await db.grant_access_by_category(uuid_id, plan['allowed_categories'])

            markup = await user_menu.post_charge_menu(lang) # ✅ await
            await bot.edit_message_text(
                f"✅ <b>خرید موفقیت‌آمیز بود!</b>\n\nنام کاربری: <code>{username}</code>",
                user_id, 
                call.message.message_id,
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            await bot.send_message(user_id, "❌ خطا در ساخت سرویس در پنل.")
            
    except Exception as e:
        logger.error(f"Purchase Error: {e}")
        await bot.send_message(user_id, "❌ خطای غیرمنتظره.")