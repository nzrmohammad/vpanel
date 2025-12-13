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
    lang = await db.get_user_language(user_id)
    
    markup = await user_menu.payment_options_menu(lang, back_callback="wallet:main")
    
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

# --- 1. تاریخچه تراکنش‌ها ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:history")
async def wallet_history_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # دریافت لیست تراکنش‌ها (مثلاً 10 تای آخر)
    transactions = await db.get_wallet_history(user_id, limit=10)
    
    if not transactions:
        text = "📜 **تاریخچه تراکنش‌ها**\n\nهنوز هیچ تراکنشی ثبت نشده است."
    else:
        text = "📜 **تاریخچه ۱۰ تراکنش آخر:**\n\n"
        for t in transactions:
            amount = t.get('amount', 0)
            desc = t.get('description', t.get('type', 'Unknown'))
            date_str = user_formatter.format_date(t.get('transaction_date'))
            
            icon = "🟢" if amount > 0 else "🔴"
            amount_str = f"{int(abs(amount)):,} تومان"
            
            text += f"{icon} **{amount_str}**\n📅 {date_str}\n📝 {desc}\n──────────────────\n"

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn("wallet:main", lang))
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=kb,
        parse_mode='Markdown'
    )

# --- 2. تنظیمات تمدید خودکار ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:settings")
async def wallet_settings_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    user_data = await db.user(user_id)
    auto_renew = user_data.get('auto_renew', False)
    
    markup = await user_menu.wallet_settings_menu(auto_renew, lang)
    
    text = (
        "⚙️ **تنظیمات تمدید خودکار**\n\n"
        "با فعال‌سازی این گزینه، سرویس‌های شما در صورت داشتن موجودی کافی، به صورت خودکار تمدید خواهند شد."
    )
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data == "wallet:toggle_auto_renew")
async def toggle_auto_renew_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    # تغییر وضعیت در دیتابیس
    user_data = await db.user(user_id)
    current_status = user_data.get('auto_renew', False)
    new_status = not current_status
    
    await db.update_auto_renew_setting(user_id, new_status)
    
    # رفرش منو
    await wallet_settings_handler(call)
    
    status_msg = "✅ فعال شد" if new_status else "❌ غیرفعال شد"
    await bot.answer_callback_query(call.id, f"تمدید خودکار {status_msg}")

# --- 3. انتقال موجودی ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:transfer_start")
async def transfer_balance_start(call: types.CallbackQuery):
    # فعلاً پیام "به زودی" یا لاجیک ساده
    await bot.answer_callback_query(call.id, "🔜 قابلیت انتقال موجودی به زودی فعال می‌شود.", show_alert=True)

# --- 4. خرید هدیه ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:gift_start")
async def gift_purchase_start(call: types.CallbackQuery):
    # فعلاً پیام "به زودی"
    await bot.answer_callback_query(call.id, "🔜 قابلیت خرید هدیه به زودی فعال می‌شود.", show_alert=True)

# --- 5. مشاهده سرویس‌ها (انتخاب دسته) ---
@bot.callback_query_handler(func=lambda call: call.data == "view_plans")
async def view_plans_categories(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # نمایش منوی دسته‌بندی‌ها
    markup = await user_menu.plan_categories_menu(lang)
    
    await bot.edit_message_text(
        get_string('prompt_select_plan_category', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
    )

# تابع show_plans_list را به این صورت آپدیت کنید:

@bot.callback_query_handler(func=lambda call: call.data.startswith("show_plans:"))
async def show_plans_list(call: types.CallbackQuery):
    category = call.data.split(":")[1]
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # 1. چک کردن توضیحات (Alert)
    # ابتدا لیست کتگوری‌ها را می‌گیریم تا توضیحات این یکی را پیدا کنیم
    categories = await db.get_server_categories()
    selected_cat = next((c for c in categories if c['code'] == category), None)
    
    if selected_cat and selected_cat.get('description'):
        # نمایش هشدار به کاربر
        await bot.answer_callback_query(call.id, selected_cat['description'], show_alert=True)
        # مکث کوتاه برای اینکه کاربر پیام را ببیند (اختیاری است، تلگرام خودش هندل می‌کند)
    
    # 2. ادامه فرآیند دریافت موجودی و پلن‌ها...
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    all_plans = await db.get_all_plans(active_only=True)
    
    filtered_plans = []
    for plan in all_plans:
        cats = plan.get('allowed_categories') or []
        if category == 'combined':
            if len(cats) > 1 or not cats:
                filtered_plans.append(plan)
        else:
            if category in cats and len(cats) == 1:
                filtered_plans.append(plan)
    
    if not filtered_plans:
        # اگر پلنی نبود فقط یک پیام ساده بده، آلرت توضیحات قبلا نمایش داده شده
        # اگر آلرت بالا اجرا شده باشد، این یکی اجرا نمی‌شود چون هر کالبک یک answer دارد
        # پس اینجا شرط می‌گذاریم
        try:
            await bot.answer_callback_query(call.id, get_string('fmt_plans_none_in_category', lang), show_alert=True)
        except:
            pass # قبلا answer شده
        return

    markup = await user_menu.plan_category_menu(lang, balance, filtered_plans)
    
    cat_title = category.upper() if category != 'combined' else get_string('btn_cat_combined', lang)
    text = get_string('fmt_plans_title', lang).format(type_title=cat_title)
    
    await bot.edit_message_text(
        text,
        user_id,
        call.message.message_id,
        reply_markup=markup
    )

# --- 7. دکمه‌های جانبی (حجم اضافه و روش پرداخت از منوی پلن) ---
@bot.callback_query_handler(func=lambda call: call.data == "show_addons")
async def show_addons_handler(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 بسته‌های حجم و زمان اضافه به زودی فعال می‌شوند.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "show_payment_options")
async def redirect_to_payment(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    markup = await user_menu.payment_options_menu(lang, back_callback="view_plans")
    
    await bot.edit_message_text(
        get_string('prompt_select_payment_method', lang),
        user_id,
        call.message.message_id,
        reply_markup=markup
    )