# bot/user_handlers/wallet.py

from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.formatters import user_formatter
from bot.database import db
from bot.language import get_string
from bot.services.panels import PanelFactory
from bot.utils.formatters import escape_markdown
from bot.utils.date_helpers import to_shamsi
import logging
import uuid as uuid_lib

logger = logging.getLogger(__name__)

# دیکشنری برای ذخیره وضعیت پرداخت کاربر
# format: {user_id: {'step': 'waiting_amount', 'msg_id': 123, 'amount': 0}}
user_payment_states = {}

# ==========================================
# 1. هندلر توزیع‌کننده (Dispatcher)
# ==========================================
@bot.message_handler(content_types=['text', 'photo'], func=lambda m: m.from_user.id in user_payment_states)
async def wallet_input_handler(message: types.Message):
    """
    این تابع تمام پیام‌های کاربرانی که در پروسه شارژ هستند را دریافت می‌کند
    و به تابع مناسب هدایت می‌کند.
    """
    user_id = message.from_user.id
    state = user_payment_states.get(user_id)
    
    if not state: 
        return

    step = state.get('step')

    if step == 'waiting_amount':
        await process_charge_amount(message)
    elif step == 'waiting_receipt':
        await process_receipt_upload(message)

# ==========================================
# 2. منوی اصلی و شارژ
# ==========================================

# --- منوی اصلی کیف پول ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:main")
async def wallet_main_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # پاک کردن وضعیت قبلی اگر وجود داشت
    if user_id in user_payment_states:
        del user_payment_states[user_id]

    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0) if user_data else 0
    
    text = "💰 *کیف پول*"
    markup = await user_menu.wallet_main_menu(balance, lang)
    
    try:
        await bot.edit_message_text(
            text, user_id, call.message.message_id,
            reply_markup=markup, parse_mode='MarkdownV2'
        )
    except:
        await bot.send_message(user_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# --- شروع شارژ: دریافت مبلغ ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:charge")
async def wallet_charge_start(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # بررسی روش‌های پرداخت فعال
    methods = await db.get_payment_methods(active_only=True)
    if not methods:
        await bot.answer_callback_query(call.id, "❌ در حال حاضر روش پرداختی فعال نیست.", show_alert=True)
        return

    text = (
        "💰 *شارژ کیف پول*\n\n"
        "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
        "مثال: `50000`"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.btn(f"✖️ {get_string('btn_cancel_action', lang)}", "wallet:main"))
    
    msg = await bot.edit_message_text(
        text, user_id, call.message.message_id, 
        reply_markup=kb, parse_mode='MarkdownV2'
    )
    
    user_payment_states[user_id] = {
        'step': 'waiting_amount', 
        'msg_id': msg.message_id
    }

async def process_charge_amount(message: types.Message):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    
    if user_id not in user_payment_states: return

    state = user_payment_states[user_id]
    prev_msg_id = state['msg_id']

    try:
        # 1. حذف پیام ارسالی کاربر (چه متن چه عکس) برای تمیز ماندن چت
        try:
            await bot.delete_message(user_id, message.message_id)
        except: pass
        
        # 2. بررسی اینکه آیا پیام حاوی متن است یا خیر (جلوگیری از ارور NoneType)
        if not message.text:
            error_text = (
                "💰 *شارژ کیف پول*\n\n"
                "⛔ *خطا: فرمت پیام نامعتبر است*\n"
                "لطفاً فقط مبلغ را به صورت *عدد* (به تومان) ارسال کنید، نه عکس یا فایل\\.\n\n"
                "مثال: `50000`"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(user_menu.btn(f"✖️ {get_string('btn_cancel_action', lang)}", "wallet:main"))
            
            # ویرایش پیام قبلی (منو) به جای ارسال پیام جدید
            try:
                await bot.edit_message_text(error_text, user_id, prev_msg_id, reply_markup=kb, parse_mode='MarkdownV2')
            except: pass
            return

        # 3. پردازش متن ارسال شده
        amount_str = message.text.replace(',', '').replace(' ', '').strip()
        
        # بررسی اینکه آیا فقط عدد وارد شده است
        if not amount_str.isdigit():
            error_text = (
                "💰 *شارژ کیف پول*\n\n"
                "⚠️ *خطا: مقدار وارد شده عدد نیست*\n"
                "لطفاً فقط عدد انگلیسی یا فارسی وارد کنید (بدون حروف):\n\n"
                "مثال: `50000`"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(user_menu.btn(f"✖️ {get_string('btn_cancel_action', lang)}", "wallet:main"))
            
            await bot.edit_message_text(error_text, user_id, prev_msg_id, reply_markup=kb, parse_mode='MarkdownV2')
            return
            
        amount = int(amount_str)
        if amount < 5000:
            error_text = (
                "💰 *شارژ کیف پول*\n\n"
                "⚠️ *خطا: مبلغ کمتر از حد مجاز*\n"
                "حداقل مبلغ شارژ ۵,۰۰۰ تومان است\\.\n\n"
                "لطفاً مبلغ بیشتری وارد کنید:"
            )
            kb = types.InlineKeyboardMarkup()
            kb.add(user_menu.btn(f"✖️ {get_string('btn_cancel_action', lang)}", "wallet:main"))
            
            await bot.edit_message_text(error_text, user_id, prev_msg_id, reply_markup=kb, parse_mode='MarkdownV2')
            return

        # 4. همه چیز درست است، ذخیره مبلغ و رفتن به مرحله بعد
        state['amount'] = amount
        state['step'] = 'select_method'
        
        methods = await db.get_payment_methods(active_only=True)
        markup = await user_menu.payment_options_menu(lang, methods, back_callback="wallet:charge")
        
        text = f"💳 مبلغ قابل پرداخت: *{amount:,} تومان*\n\nلطفاً روش پرداخت را انتخاب کنید:"
        
        await bot.edit_message_text(text, user_id, prev_msg_id, reply_markup=markup, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.error(f"Error in charge amount: {e}")
        # در صورت بروز خطای پیش‌بینی نشده، استیت را پاک می‌کنیم
        if user_id in user_payment_states: del user_payment_states[user_id]
        await bot.send_message(user_id, "❌ خطای غیرمنتظره. لطفاً مجدد تلاش کنید.")

# --- نمایش اطلاعات پرداخت ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("payment:select:"))
async def show_payment_details(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    if user_id not in user_payment_states:
        await bot.answer_callback_query(call.id, "نشست منقضی شده. مجدد تلاش کنید.")
        return

    try:
        method_id = int(call.data.split(":")[2])
    except:
        return
    
    methods = await db.get_payment_methods(active_only=True)
    selected_method = next((m for m in methods if m['id'] == method_id), None)
    
    if not selected_method:
        await bot.answer_callback_query(call.id, "این روش پرداخت دیگر فعال نیست.", show_alert=True)
        return

    amount = user_payment_states[user_id]['amount']
    details = selected_method['details']
    
    info_text = ""
    if selected_method['type'] == 'card':
        info_text = (
            f"📝 *اطلاعات کارت*\n\n"
            f"🏦 بانک: {escape_markdown(details.get('bank_name', ''))}\n"
            f"👤 صاحب کارت: {escape_markdown(details.get('card_holder', ''))}\n"
            f"💳 شماره کارت:\n`{details.get('card_number', '')}`"
        )
    else:
        global_rate = await db.get_config('usdt_rate', '60000')
        rate = int(global_rate)
        usdt_amount = round(amount / rate, 2) if rate > 0 else 0
        
        info_text = (
            f"📝 *اطلاعات کیف پول*\n\n"
            f"💎 شبکه: {escape_markdown(details.get('network', ''))}\n"
            f"💵 نرخ تبدیل: {rate:,} تومان\n"
            f"💰 مبلغ تتر: `{usdt_amount} USDT`\n\n"
            f"🔗 آدرس ولت:\n`{details.get('address', '')}`"
        )

    text = (
        f"{info_text}\n\n"
        f"💵 مبلغ قابل پرداخت: *{amount:,} تومان*\n\n"
        "📸 *لطفاً پس از واریز، تصویر رسید را در همین صفحه ارسال کنید\\.*"
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.btn(f"✖️ {get_string('btn_cancel_action', lang)}", "wallet:main"))

    await bot.edit_message_text(
        text, user_id, call.message.message_id,
        reply_markup=kb, parse_mode='MarkdownV2'
    )
    
    # تغییر وضعیت به انتظار دریافت رسید
    user_payment_states[user_id]['step'] = 'waiting_receipt'

# --- پردازش رسید (با متن جدید و حذف عکس) ---
async def process_receipt_upload(message: types.Message):
    user_id = message.from_user.id
    lang = await db.get_user_language(user_id)
    
    state = user_payment_states.get(user_id)
    
    # 1. حذف عکس رسید برای تمیزی چت
    try:
        await bot.delete_message(user_id, message.message_id)
    except Exception as e:
        logger.warning(f"Could not delete receipt message: {e}")

    if message.content_type != 'photo':
        await bot.send_message(user_id, "⚠️ لطفاً فقط تصویر رسید را ارسال کنید.")
        return

    amount = state['amount']
    prev_msg_id = state['msg_id']
    
    # --- متن اصلاح شده ---
    wait_text = "✅ رسید شما دریافت شد\\. پس از تایید توسط ادمین، حساب شما شارژ خواهد شد\\."
    
    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn("wallet:main", lang))
    
    try:
        await bot.edit_message_text(
            wait_text, user_id, prev_msg_id,
            reply_markup=kb, parse_mode='MarkdownV2'
        )
    except:
        await bot.send_message(user_id, wait_text, reply_markup=kb, parse_mode='MarkdownV2')
    
    # ثبت درخواست
    req_id = await db.create_charge_request(user_id, amount, prev_msg_id)
    
    # ارسال به کانال ادمین
    admin_group_id = await db.get_config('admin_group_id')
    
    if admin_group_id:
        try:
            await send_receipt_to_admin(message, req_id, amount, user_id, int(admin_group_id))
        except Exception as e:
            logger.error(f"Failed to send to admin: {e}")
    else:
        logger.warning("Admin group ID not set.")
    
    # پایان کار: حذف استیت
    if user_id in user_payment_states:
        del user_payment_states[user_id]

async def send_receipt_to_admin(message: types.Message, req_id: int, amount: int, user_id: int, chat_id: int):
    """ارسال رسید به گروه مدیریت با فرمت استاندارد"""
    user_data = await db.user(user_id)
    username = user_data.get('username', 'Unknown')
    name = user_data.get('first_name', 'Unknown')
    
    caption = (
        f"💸 *درخواست شارژ جدید*\n"
        f"\u200f🆔 شناسه درخواست: `{req_id}`\n"
        f"👤 کاربر: {escape_markdown(name)}\n"
        f"🔢 آیدی عددی: `{user_id}`\n"
        f"🔗 یوزرنیم: @{escape_markdown(username)}\n"
        f"💳 مبلغ: *{amount:,} تومان*"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید شارژ", callback_data=f"admin:charge_req:confirm:{req_id}"),
        types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"admin:charge_req:reject:{req_id}")
    )
    
    photo_id = message.photo[-1].file_id
    
    await bot.send_photo(
        chat_id=chat_id,
        photo=photo_id,
        caption=caption,
        reply_markup=markup,
        parse_mode='MarkdownV2'
    )

# --- خرید سرویس (Buy Plan) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('wallet:buy_confirm:'))
async def buy_plan_confirm(call: types.CallbackQuery):
    try:
        plan_id = int(call.data.split(':')[2])
    except: return

    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)

    selected_plan = await db.get_plan_by_id(plan_id)
    if not selected_plan:
        await bot.answer_callback_query(call.id, "❌ پلن یافت نشد.")
        return

    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0)
    
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
        lang = await db.get_user_language(user_id)
        
        plan = await db.get_plan_by_id(plan_id)
        if not plan: return
        
        user_data = await db.user(user_id)
        balance = user_data.get('wallet_balance', 0)
        
        if balance < plan['price']:
            await bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
            return

        await bot.edit_message_text("⏳ در حال فعال‌سازی سرویس...", user_id, call.message.message_id)
        
        # انتخاب پنل پیش‌فرض (قابل توسعه)
        target_panel_name = "server1" 
        
        panel_api = await PanelFactory.get_panel(target_panel_name)
        if not panel_api:
             await bot.send_message(user_id, "❌ خطای اتصال به سرور.")
             return

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

            markup = await user_menu.post_charge_menu(lang) 
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

# --- تاریخچه تراکنش‌ها ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:history")
async def wallet_history_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    transactions = await db.get_wallet_history(user_id, limit=10)
    
    header = "📜 *تاریخچه تراکنش‌ها*\n"
    text = header
    
    if not transactions:
        text += "──────────────────\nتراکنشی یافت نشد"
    else:
        for t in transactions:
            amount = t.get('amount', 0)
            raw_desc = t.get('description') or t.get('type', 'Unknown')
            raw_date = to_shamsi(t.get('transaction_date'), include_time=True)
            
            desc = escape_markdown(raw_desc)
            date_str = escape_markdown(raw_date)
            
            amount_val = f"{int(abs(amount)):,}"
            amount_str = escape_markdown(amount_val) + " تومان"
            
            icon = "➕" if amount > 0 else "➖"
            text += (
                "──────────────────\n"
                f"{icon} {amount_str} \n"
                f" {desc} \n"
                f" {date_str}\n"
            )

    kb = types.InlineKeyboardMarkup()
    kb.add(user_menu.back_btn("wallet:main", lang))
    
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=kb, parse_mode='MarkdownV2')

# --- تنظیمات و سایر موارد ---
@bot.callback_query_handler(func=lambda call: call.data == "wallet:settings")
async def wallet_settings_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    user_data = await db.user(user_id)
    auto_renew = user_data.get('auto_renew', False)
    
    markup = await user_menu.wallet_settings_menu(auto_renew, lang)
    text = "⚙️ **تنظیمات تمدید خودکار**\n\nبا فعال‌سازی این گزینه..."
    await bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data == "wallet:toggle_auto_renew")
async def toggle_auto_renew_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await db.user(user_id)
    new_status = not user_data.get('auto_renew', False)
    await db.update_auto_renew_setting(user_id, new_status)
    await wallet_settings_handler(call)
    status_msg = "✅ فعال شد" if new_status else "❌ غیرفعال شد"
    await bot.answer_callback_query(call.id, f"تمدید خودکار {status_msg}")

@bot.callback_query_handler(func=lambda call: call.data == "view_plans")
async def view_plans_categories(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    markup = await user_menu.plan_categories_menu(lang)
    await bot.edit_message_text(get_string('prompt_select_plan_category', lang), user_id, call.message.message_id, reply_markup=markup)

# در فایل bot/user_handlers/wallet.py

@bot.callback_query_handler(func=lambda call: call.data.startswith("show_plans:"))
async def show_plans_list(call: types.CallbackQuery):
    category = call.data.split(":")[1]
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    # 1. دریافت اطلاعات دسته‌بندی
    categories = await db.get_server_categories()
    selected_cat = next((c for c in categories if c['code'] == category), None)
    
    cat_name = selected_cat['name'] if selected_cat else category
    cat_emoji = selected_cat['emoji'] if selected_cat else ""
    cat_desc = selected_cat.get('description') if selected_cat else None
    
    # --- درخواست ۱: نمایش پاپ‌آپ (Alert) ---
    # اگر توضیحات وجود دارد، به صورت هشدار هم نمایش داده شود
    if cat_desc:
        await bot.answer_callback_query(call.id, cat_desc, show_alert=True)
    
    # 2. دریافت و فیلتر پلن‌ها
    user_data = await db.user(user_id)
    balance = user_data.get('wallet_balance', 0)
    all_plans = await db.get_all_plans(active_only=True)
    
    filtered_plans = []
    for plan in all_plans:
        cats = plan.get('allowed_categories') or []
        if category == 'combined':
            if len(cats) > 1 or not cats: filtered_plans.append(plan)
        else:
            if category in cats and len(cats) == 1: filtered_plans.append(plan)
    
    if not filtered_plans:
        try: await bot.answer_callback_query(call.id, get_string('fmt_plans_none_in_category', lang), show_alert=True)
        except: pass
        return

    # 3. ساخت متن پیام
    header_title = f"🚀 *پلن‌های فروش سرویس \({escape_markdown(cat_name)}\)*"
    text = f"{header_title}\n"
    
    # --- درخواست ۱: اضافه شدن توضیحات به متن ---
    if cat_desc:
        text += f"💡 {escape_markdown(cat_desc)}\n"
    
    line = "────────────────────"
    text += f"{line}\n"

    for plan in filtered_plans:
        p_name = escape_markdown(plan['name'])
        
        raw_vol = plan['volume_gb']
        vol_str = f"{int(raw_vol)}" if raw_vol == int(raw_vol) else f"{raw_vol}"
        p_vol = escape_markdown(vol_str)
        
        p_days = plan['days']
        price_comma = f"{int(plan['price']):,}"
        p_price = escape_markdown(price_comma)
        
        # --- درخواست ۲: حذف پرچم تکراری ---
        # اینجا cat_emoji را حذف کردیم چون معمولاً در نام پلن یا هدر هست
        text += (
            f"{p_name}\n"  # قبلاً اینجا {cat_emoji} بود که حذف شد
            f"حجم: {p_vol} گیگابایت\n"
            f"مدت زمان: {p_days} روز\n"
            f"قیمت: {p_price} تومان\n"
            f"{line}\n"
        )

    text += "\nبرای مشاوره، با پشتیبانی در تماس باشید\."

    markup = await user_menu.plan_category_menu(lang, balance, filtered_plans)
    
    try:
        await bot.edit_message_text(
            text, 
            user_id, 
            call.message.message_id, 
            reply_markup=markup, 
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.error(f"Error displaying plans text: {e}")
        # هندل کردن خطای احتمالی Markdown
        fallback_text = text.replace('*', '').replace('\\', '').replace('(', '').replace(')', '')
        await bot.edit_message_text(fallback_text, user_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_addons")
async def show_addons_handler(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 بسته‌های حجم و زمان اضافه به زودی فعال می‌شوند.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "wallet:transfer_start")
async def transfer_balance_start(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 قابلیت انتقال موجودی به زودی فعال می‌شود.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "wallet:gift_start")
async def gift_purchase_start(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 قابلیت خرید هدیه به زودی فعال می‌شود.", show_alert=True)