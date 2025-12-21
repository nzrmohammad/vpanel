# bot/admin_handlers/settings.py

import time
import logging
from telebot import types
from bot.database import db
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# متغیرهای گلوبال
bot = None
admin_conversations = {}

def initialize_settings_handlers(bot_instance, state_dict):
    global bot, admin_conversations
    bot = bot_instance
    admin_conversations = state_dict

# --- 1. منوی اصلی تنظیمات ---
async def settings_main_panel(call: types.CallbackQuery, params: list):
    mode = params[0] if params else 'main'
    
    if mode == 'wallet':
        # === زیرمنوی مدیریت روش‌های پرداخت ===
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💳 کارت‌های بانکی", callback_data="admin:pay_methods:card"),
            types.InlineKeyboardButton("💎 کریپتو (Crypto)", callback_data="admin:pay_methods:crypto")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
        
        text = "💰 *مدیریت روش‌های پرداخت*\n\nلطفاً نوع روش پرداخت مورد نظر را انتخاب کنید:"
        
    else:
        # === منوی اصلی تنظیمات سیستم ===
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("💰 مدیریت کیف پول و پرداخت", callback_data="admin:settings:wallet"))
        
        markup.add(
            types.InlineKeyboardButton("📢 کانال گزارشات", callback_data="admin:set_chan:log"),
            types.InlineKeyboardButton("🧾 کانال رسیدها", callback_data="admin:set_chan:proof")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
        
        text = (
            "⚙️ *تنظیمات سیستم*\n\n"
            "از این بخش می‌توانید تنظیمات کلی ربات، روش‌های پرداخت و کانال‌های متصل را مدیریت کنید\\."
        )

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# --- 2. نمایش لیست کارت‌ها/ولت‌ها ---
async def list_payment_methods(call: types.CallbackQuery, params: list):
    if not params: return
    method_type = params[0]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    header_text = ""

    # === بخش جدید: مدیریت نرخ تتر (فقط برای کریپتو) ===
    if method_type == 'crypto':
        # دریافت نرخ فعلی از دیتابیس (تنظیمات سراسری)
        current_rate = await db.get_config('usdt_rate', '60000')
        
        # دکمه ویرایش نرخ در بالای لیست
        markup.add(types.InlineKeyboardButton(
            f"💰 نرخ تتر: {int(current_rate):,} تومان (ویرایش)", 
            callback_data="admin:edit_usdt_rate"
        ))
        header_text = f"💵 **نرخ فعلی تتر:** `{int(current_rate):,}` تومان\n\n"

    # دریافت لیست متدها
    methods = await db.get_payment_methods(method_type, active_only=False)
    
    type_title = "کارت‌های بانکی" if method_type == 'card' else "کیف پول‌های کریپتو"
    text = f"📋 *مدیریت {type_title}*\n\n{header_text}لیست روش‌های تعریف شده:\n"
    
    if not methods:
        text += "_هیچ موردی یافت نشد\\._"
    else:
        for m in methods:
            safe_title = escape_markdown(m['title'])
            
            is_active = m.get('is_active', True)
            status_icon = "✅" if is_active else "❌"
            status_text = "فعال" if is_active else "غیرفعال"
            
            # دکمه تغییر وضعیت
            markup.add(types.InlineKeyboardButton(
                f"{status_icon} {m['title']} ({status_text})", 
                callback_data=f"admin:toggle_method:{m['id']}:{method_type}"
            ))
            
            # دکمه حذف
            markup.add(types.InlineKeyboardButton(
                f"🗑 حذف {m['title']}", 
                callback_data=f"admin:del_method:{m['id']}:{method_type}"
            ))
            
            details_txt = ""
            if method_type == 'card':
                details_txt = f"`{m['details'].get('card_number')}`"
            else:
                details_txt = f"`{m['details'].get('network')}`"
            
            text += f"🔹 {safe_title}\n{details_txt}\n\n"

    add_text = "➕ افزودن کارت جدید" if method_type == 'card' else "➕ افزودن ولت جدید"
    markup.add(types.InlineKeyboardButton(add_text, callback_data=f"admin:add_method:{method_type}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:wallet"))
    
    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# --- 3. حذف و تغییر وضعیت ---
async def delete_payment_method_handler(call: types.CallbackQuery, params: list):
    if len(params) < 2: return
    method_id = int(params[0])
    method_type = params[1]
    
    await db.delete_payment_method(method_id)
    await bot.answer_callback_query(call.id, "✅ حذف شد.")
    await list_payment_methods(call, [method_type])

async def toggle_payment_method_handler(call: types.CallbackQuery, params: list):
    if len(params) < 2: return
    method_id = int(params[0])
    method_type = params[1]
    
    await db.toggle_payment_method(method_id)
    await bot.answer_callback_query(call.id, "✅ وضعیت تغییر کرد.")
    await list_payment_methods(call, [method_type])

# --- 4. هندلر تغییر نرخ تتر (سراسری) ---
async def edit_usdt_rate_start(call: types.CallbackQuery, params: list):
    user_id = call.from_user.id
    msg_id = call.message.message_id
    
    current_rate = await db.get_config('usdt_rate', '60000')
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:pay_methods:crypto"))
    
    text = (
        f"💰 **ویرایش نرخ تتر**\n\n"
        f"نرخ فعلی: `{int(current_rate):,}` تومان\n\n"
        "لطفاً نرخ جدید تتر را به تومان وارد کنید:\n"
        "مثال: `62000`"
    )
    
    await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='Markdown')
    
    admin_conversations[user_id] = {
        'action_type': 'set_usdt_rate',
        'next_handler': process_usdt_rate_input,
        'msg_id': msg_id,
        'timestamp': time.time()
    }

async def process_usdt_rate_input(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    rate_str = message.text.strip()
    if not rate_str.isdigit():
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:pay_methods:crypto"))
        await _safe_edit(user_id, state['msg_id'], "❌ لطفاً فقط عدد وارد کنید.", reply_markup=markup)
        return

    # ذخیره در تنظیمات سراسری
    await db.set_config('usdt_rate', rate_str)
    
    del admin_conversations[user_id]
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:pay_methods:crypto"))
    
    await _safe_edit(
        user_id, state['msg_id'], 
        f"✅ نرخ تتر با موفقیت به `{int(rate_str):,}` تومان تغییر یافت.", 
        reply_markup=markup, parse_mode='Markdown'
    )


# --- 5. شروع افزودن روش جدید ---
async def start_add_method(call: types.CallbackQuery, params: list):
    method_type = params[0]
    user_id = call.from_user.id
    msg_id = call.message.message_id
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
    
    if method_type == 'card':
        # --- کارت (مرحله ۱) ---
        text = "🏦 لطفاً **نام بانک** را وارد کنید:\nمثال: `بانک ملت`"
        await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='Markdown')
        
        admin_conversations[user_id] = {
            'action_type': 'add_card_step1',
            'next_handler': process_card_step_1_bank,
            'method_type': 'card',
            'data': {},
            'msg_id': msg_id,
            'timestamp': time.time()
        }
        
    else:
        # --- کریپتو (مرحله ۱) ---
        text = (
            "💎 **افزودن کیف پول جدید**\n\n"
            "لطفاً **آدرس کیف پول (Wallet Address)** را ارسال کنید:\n"
            "مثال: `T9yQw...jK12`"
        )
        await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='Markdown')
        
        admin_conversations[user_id] = {
            'action_type': 'add_crypto_step1',
            'next_handler': process_crypto_step_1_address,
            'method_type': 'crypto',
            'data': {},
            'msg_id': msg_id,
            'timestamp': time.time()
        }

# --- هندلرهای کارت (بدون تغییر) ---
async def process_card_step_1_bank(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    state['data']['bank_name'] = message.text.strip()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
    
    await _safe_edit(user_id, state['msg_id'], f"✅ بانک: {state['data']['bank_name']}\n\n💳 لطفاً **شماره کارت یا حساب** را وارد کنید:", reply_markup=markup, parse_mode='Markdown')
    state['next_handler'] = process_card_step_2_number

async def process_card_step_2_number(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    state['data']['card_number'] = message.text.strip()
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
    
    await _safe_edit(user_id, state['msg_id'], f"✅ بانک: {state['data']['bank_name']}\n✅ شماره: {state['data']['card_number']}\n\n👤 لطفاً **نام صاحب حساب** را وارد کنید:", reply_markup=markup, parse_mode='Markdown')
    state['next_handler'] = process_card_step_3_holder

async def process_card_step_3_holder(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    data = state['data']
    data['card_holder'] = message.text.strip()
    
    await save_payment_method(user_id, state, 'card', data)

# --- هندلرهای کریپتو (فقط ۲ مرحله: آدرس و شبکه) ---

async def process_crypto_step_1_address(message: types.Message):
    """مرحله ۱: دریافت آدرس ولت"""
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    address = message.text.strip()
    state['data']['address'] = address
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
    
    await _safe_edit(
        user_id, state['msg_id'],
        f"✅ آدرس: `{address[:10]}...`\n\n🌐 لطفاً **شبکه انتقال** را وارد کنید:\nمثال: `TRC20`",
        reply_markup=markup, parse_mode='Markdown'
    )
    state['next_handler'] = process_crypto_step_2_network

async def process_crypto_step_2_network(message: types.Message):
    """مرحله ۲: دریافت شبکه و ذخیره نهایی (نرخ دیگر پرسیده نمی‌شود)"""
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    network = message.text.strip().upper()
    state['data']['network'] = network
    
    # اینجا دیگر مرحله بعد نداریم، ذخیره می‌کنیم
    # نرخ در system_config ذخیره شده است، در متد پرداخت فقط اطلاعات ولت مهم است
    
    await save_payment_method(user_id, state, 'crypto', state['data'])

# --- ذخیره نهایی ---
async def save_payment_method(user_id, state, method_type, data):
    try:
        title = ""
        if method_type == 'card':
            title = f"{data['bank_name']} - {data['card_holder']}"
        else:
            title = f"Tether ({data['network']})"
            
        await db.add_payment_method(method_type, title, data)
        
        del admin_conversations[user_id]
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"admin:pay_methods:{method_type}"))
        
        msg_text = "✅ **کارت بانکی افزوده شد.**" if method_type == 'card' else "✅ **کیف پول کریپتو افزوده شد.**"
        
        await _safe_edit(user_id, state['msg_id'], msg_text, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error saving method: {e}")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
        await _safe_edit(user_id, state['msg_id'], "❌ خطا در ذخیره‌سازی.", reply_markup=markup)

# --- 5. تنظیم کانال‌ها ---
async def set_channel_start(call: types.CallbackQuery, params: list):
    chan_type = params[0]
    user_id = call.from_user.id
    msg_id = call.message.message_id
    
    if chan_type == 'log':
        type_name = "گزارشات ادمین"
        config_key = "admin_group_id"
    else:
        type_name = "رسیدهای واریزی"
        config_key = "proof_channel_id"

    current_id = await db.get_config(config_key)
    ltr_mark = "\u200e" 
    
    current_display = "❌ \\(تنظیم نشده\\)"
    
    if current_id:
        safe_id = str(current_id).replace("-", "\\-")
        
        try:
            chat_info = await bot.get_chat(current_id)
            safe_title = escape_markdown(chat_info.title)
            
            current_display = f"✅ *{safe_title}*\n🆔 `{ltr_mark}{safe_id}`"
            
        except Exception as e:
            current_display = f"⚠️ `{ltr_mark}{safe_id}`\n\\(ربات نام کانال را نمی‌بیند، بررسی کنید ادمین باشد\\)"

    text = (
        f"📢 *تنظیم کانال {type_name}*\n\n"
        f"🔻 *وضعیت فعلی:*\n{current_display}\n"
        "➖➖➖➖➖➖➖➖\n"
        "💡 *راهنمای دریافت آیدی:*\n"
        "۱\\. یک پیام از کانال خود را به ربات `@getidsbot` فوروارد کنید\\.\n"
        "۲\\. مقدار `Chat ID` را کپی کنید \\(باید با `\\-100` شروع شود\\)\\.\n\n"
        "👇 *لطفاً آیدی عددی کانال یا گروه جدید را ارسال کنید:*\n"
        "مثال: `\\-1001234567890`"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:main"))
    
    await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='MarkdownV2')

    admin_conversations[user_id] = {
        'action_type': 'set_channel',
        'next_handler': process_channel_id,
        'chan_type': chan_type,
        'msg_id': msg_id,
        'timestamp': time.time()
    }

async def process_channel_id(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    # دریافت نوع کانال از وضعیت ذخیره شده
    chan_type = state.get('chan_type')
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    text = message.text.strip()
    
    # اعتبارسنجی آیدی
    if not (text.startswith("-") and text[1:].isdigit()) and not text.isdigit():
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:main"))
        await _safe_edit(user_id, state['msg_id'], "❌ آیدی نامعتبر است. باید عدد باشد (مثلاً -100...)", reply_markup=markup)
        return

    # انتخاب کلید مناسب برای دیتابیس
    config_key = "admin_group_id" if chan_type == 'log' else "proof_channel_id"
    
    # ذخیره در دیتابیس
    await db.set_config(config_key, text)
    
    # پایان مکالمه
    del admin_conversations[user_id]
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="admin:settings:main"))
    
    await _safe_edit(
        user_id, state['msg_id'], 
        f"✅ *کانال با موفقیت ثبت شد\\.*\nآیدی: `{text}`", 
        reply_markup=markup, parse_mode='MarkdownV2'
    )