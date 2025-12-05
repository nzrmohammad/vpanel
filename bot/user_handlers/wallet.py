# bot/user_handlers/wallet.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.formatters import user_formatter
from bot.database import db
from bot.language import get_string
from bot.config import CARD_PAYMENT_INFO, ONLINE_PAYMENT_LINK, ENABLE_TRAFFIC_TRANSFER
from bot.services.panels import PanelFactory
import logging

logger = logging.getLogger(__name__)

# --- منوی اصلی کیف پول ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:main")
async def wallet_main_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    balance = db.get_user_balance(user_id)
    
    # دریافت متن زیبا از فرمتر
    # (فرض بر این است که متدی برای گرفتن ۵ تراکنش آخر در دیتابیس دارید)
    transactions = db.get_user_transactions(user_id, limit=5)
    text = user_formatter.wallet_page(balance, transactions, lang)
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=user.wallet_main_menu(balance, lang),
        parse_mode='HTML'
    )

# --- شارژ حساب ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:charge")
async def wallet_charge_methods(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    await bot.edit_message_text(
        get_string('prompt_select_payment_method', lang),
        user_id,
        call.message.message_id,
        reply_markup=user_menu.payment_options_menu(lang)
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_card_details")
async def show_card_details(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
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
        reply_markup=user_menu.back_btn("wallet:charge", lang), # دکمه بازگشت ساده
        parse_mode='HTML'
    )

# --- خرید سرویس (Buy Plan) ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:buy_confirm:'))
async def buy_plan_confirm(call: types.CallbackQuery):
    """نمایش فاکتور نهایی قبل از کسر موجودی"""
    try:
        # دریافت ID پلن از کالبک (فرمت: wallet:buy_confirm:PLAN_ID)
        # نکته: مطمئن شوید دکمه‌ای که کاربر کلیک کرده، ID را می‌فرستد نه اسم را.
        plan_id = int(call.data.split(':')[2])
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "❌ خطای سیستمی: شناسه پلن نامعتبر است.")
        return

    user_id = call.from_user.id
    lang = db.get_user_lang(user_id) # این متد در UserDB/base.py موجود است

    # 1. دریافت اطلاعات پلن از دیتابیس
    selected_plan = await db.get_plan_by_id(plan_id)
    
    if not selected_plan:
        await bot.answer_callback_query(call.id, "❌ پلن مورد نظر یافت نشد یا حذف شده است.")
        return

    # 2. دریافت موجودی کاربر
    # متد get_user_balance وجود ندارد، از متد جامع user() استفاده می‌کنیم
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    # 3. نمایش فاکتور با استفاده از فرمتر (UserFormatter)
    # مطمئن شوید user_formatter.purchase_confirmation آرگومان‌های درست را می‌گیرد
    text = user_formatter.purchase_confirmation(
        plan_name=selected_plan['name'],
        price=selected_plan['price'],
        current_balance=balance,
        lang_code=lang
    )
    
    # 4. ساخت کیبورد تایید نهایی
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # بررسی موجودی برای فعال/غیرفعال کردن دکمه خرید
    if balance >= selected_plan['price']:
        # ارسال ID پلن به مرحله بعد
        markup.add(
            types.InlineKeyboardButton(
                "✅ تایید و پرداخت", 
                callback_data=f"wallet:do_buy:{selected_plan['id']}"
            )
        )
    else:
        markup.add(
            types.InlineKeyboardButton(
                "💳 افزایش موجودی", 
                callback_data="wallet:charge"
            )
        )

    markup.add(
        types.InlineKeyboardButton(
            "❌ انصراف", 
            callback_data="view_plans"
        )
    )
    
    await bot.edit_message_text(
        text, 
        user_id, 
        call.message.message_id, 
        reply_markup=markup, 
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:do_buy:'))
async def execute_purchase(call: types.CallbackQuery):
    plan_id = int(call.data.split(':')[2])
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    # 1. دریافت پلن
    plan = await db.get_plan_by_id(plan_id)
    if not plan: return
    
    # 2. چک کردن موجودی
    balance = await db.get_user_balance(user_id) # اصلاح: await فراموش نشود
    if balance < plan['price']:
        await bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
        return

    await bot.edit_message_text("⏳ در حال فعال‌سازی سرویس...", user_id, call.message.message_id)

    # 3. انتخاب پنل مناسب (مثلاً اولین پنل فعال که با دسته‌بندی پلن می‌خواند)
    # این منطق باید هوشمندتر باشد، فعلاً ساده‌ترین حالت:
    target_panel_name = "server1" # باید منطق انتخاب پنل بنویسید یا دیفالت بگذارید
    # پیشنهاد: یک متد در db بسازید: db.get_best_panel_for_plan(plan['allowed_categories'])
    
    try:
        panel_api = await PanelFactory.get_panel(target_panel_name)
        
        # تولید نام کاربری یکتا
        import uuid as uuid_lib
        random_suffix = str(uuid_lib.uuid4())[:8]
        username = f"u{user_id}_{random_suffix}"
        
        # ساخت در پنل
        new_service = await panel_api.add_user(username, plan['volume_gb'], plan['days'])
        
        if new_service:
            # کسر موجودی
            await db.update_wallet_balance(user_id, -plan['price'], 'purchase', f"خرید پلن {plan['name']}")
            
            # استخراج UUID (بسته به پنل متفاوت است)
            # در هیدیفای uuid است، در مرزبان معمولا در پاسخ نیست و باید از username استفاده کرد
            service_uuid = new_service.get('uuid') or username 
            
            # ذخیره سرویس در دیتابیس (اصلاح نام متد)
            await db.add_uuid(
                user_id=user_id,
                uuid_str=service_uuid,
                name=username
            )
            
            # اعطای دسترسی به پنل (خیلی مهم)
            # باید مشخص کنید این UUID روی کدام پنل ساخته شده
            uuid_id = await db.get_uuid_id_by_uuid(service_uuid)
            await db.grant_access_by_category(uuid_id, plan['allowed_categories'])

            await bot.edit_message_text(
                f"✅ <b>خرید موفقیت‌آمیز بود!</b>\n\nنام کاربری: <code>{username}</code>",
                user_id, 
                call.message.message_id,
                reply_markup=user_menu.post_charge_menu(lang),
                parse_mode='HTML'
            )
        else:
            await bot.send_message(user_id, "❌ خطا در ساخت سرویس در پنل.")
            
    except Exception as e:
        logger.error(f"Purchase Error: {e}")
        await bot.send_message(user_id, "❌ خطای غیرمنتظره.")