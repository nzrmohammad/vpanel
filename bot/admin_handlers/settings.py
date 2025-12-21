# bot/admin_handlers/settings.py

import time
import logging
from telebot import types
from bot.database import db
from bot.utils import _safe_edit, escape_markdown

logger = logging.getLogger(__name__)

# متغیرهای گلوبال برای ذخیره وضعیت ربات و مکالمات ادمین
bot = None
admin_conversations = {}

def initialize_settings_handlers(bot_instance, state_dict):
    """مقداردهی اولیه و دریافت نمونه ربات و دیکشنری وضعیت‌ها"""
    global bot, admin_conversations
    bot = bot_instance
    admin_conversations = state_dict

# --- 1. منوی اصلی تنظیمات ---
async def settings_main_panel(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی تنظیمات با چیدمان دو ستونه"""
    
    user_id = call.from_user.id
    if user_id in admin_conversations:
        del admin_conversations[user_id]

    mode = params[0] if params else 'main'
    
    if mode == 'wallet':
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💎 کریپتو (Crypto)", callback_data="admin:pay_methods:crypto"),
            types.InlineKeyboardButton("💳 کارت‌های بانکی", callback_data="admin:pay_methods:card")
            
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
        
        text = "💰 *مدیریت روش‌های پرداخت*\n\nلطفاً نوع روش پرداخت مورد نظر را انتخاب کنید:"
        
    else:
        markup = types.InlineKeyboardMarkup(row_width=2)
        
        # ردیف اول: کیف پول | پشتیبانی
        markup.add(
            types.InlineKeyboardButton("☎️ اکانت پشتیبانی", callback_data="admin:set_chan:support"),
            types.InlineKeyboardButton("💰 مدیریت کیف پول", callback_data="admin:settings:wallet")
            
        )
        
        # ردیف دوم: کانال گزارشات | کانال رسیدها
        markup.add(
            types.InlineKeyboardButton("📢 کانال گزارشات", callback_data="admin:set_chan:log"),
            types.InlineKeyboardButton("🧾 کانال رسیدها", callback_data="admin:set_chan:proof")
        )
        
        # ردیف سوم: بازگشت
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
        
        text = (
            "⚙️ *تنظیمات سیستم*\n\n"
            "از این بخش می‌توانید تنظیمات کلی ربات، روش‌های پرداخت و کانال‌های متصل را مدیریت کنید\\."
        )

    await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# --- 2. نمایش لیست کارت‌ها/ولت‌ها ---
async def list_payment_methods(call: types.CallbackQuery, params: list):
    """نمایش لیست روش‌های پرداخت فعال و غیرفعال"""
    
    # === 🛠 FIX: پاک کردن وضعیت‌های قبلی ===
    user_id = call.from_user.id
    if user_id in admin_conversations:
        del admin_conversations[user_id]
    # ======================================

    if not params: return
    method_type = params[0]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    header_text = ""

    # === بخش مدیریت نرخ تتر (فقط برای کریپتو) ===
    if method_type == 'crypto':
        current_rate = await db.get_config('usdt_rate', '60000')
        markup.add(types.InlineKeyboardButton(
            f"💰 نرخ تتر: {int(current_rate):,} تومان (ویرایش)", 
            callback_data="admin:edit_usdt_rate"
        ))
        header_text = f"💵 **نرخ فعلی تتر:** `{int(current_rate):,}` تومان\n\n"

    # دریافت لیست متدها از دیتابیس
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

# --- 4. هندلر تغییر نرخ تتر ---
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
        "مثال: `100000`"
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


# --- 5. شروع افزودن روش جدید (کارت/کریپتو) ---
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

# --- هندلرهای کارت (مراحل) ---
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

# --- هندلرهای کریپتو (مراحل) ---

async def process_crypto_step_1_address(message: types.Message):
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
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    network = message.text.strip().upper()
    state['data']['network'] = network
    
    await save_payment_method(user_id, state, 'crypto', state['data'])

# --- ذخیره نهایی روش پرداخت ---
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

# --- 6. تنظیم کانال‌ها و اکانت پشتیبانی ---
async def set_channel_start(call: types.CallbackQuery, params: list):
    """شروع پروسه تنظیم کانال با خروجی مینیمال و دقیق برای پشتیبانی"""
    chan_type = params[0]
    user_id = call.from_user.id
    msg_id = call.message.message_id
    
    # 1. تعیین تنظیمات
    if chan_type == 'log':
        type_name = "گزارشات ادمین"
        config_key = "admin_group_id"
        help_text = "آیدی عددی کانال/گروه \\(مثال: `\u200e-1001234567890`\\)"
    elif chan_type == 'proof':
        type_name = "رسیدهای واریزی"
        config_key = "proof_channel_id"
        help_text = "آیدی عددی کانال \\(مثال: `\u200e-1001234567890`\\)"
    else: # support
        type_name = "اکانت پشتیبانی"
        config_key = "support_username"
        help_text = "یوزرنیم اکانت پشتیبانی \\(مثال: `@admin` یا `support`\\)"

    # 2. دریافت مقدار فعلی
    current_val = await db.get_config(config_key)
    
    status_section = ""
    
    if current_val:
        raw_val = str(current_val).strip()
        safe_val = f"\u200e{raw_val}".replace("_", "\\_").replace("*", "\\*")
        
        # === تنظیمات اختصاصی پشتیبانی ===
        if chan_type == 'support':
            # تمیزکردن یوزرنیم برای لینک
            clean_username = raw_val.replace('@', '')
            # افزودن @ برای نمایش (اگر ندارد)
            display_text = raw_val if raw_val.startswith('@') else f"@{raw_val}"
            safe_display = escape_markdown(display_text)
            
            # ساخت بخش وضعیت دقیقاً طبق نمونه درخواستی
            # نکته: فاصله \n بعد از "فعال" باعث می‌شود "لینک" در خط بعد قرار گیرد
            status_section = (
                f"✅ *فعال*\n"
                f"🔗 *لینک:* [{safe_display}](https://t.me/{clean_username})"
            )

        # === تنظیمات کانال‌ها (مثل قبل) ===
        else:
            try:
                chat_id = int(raw_val) if raw_val.lstrip('-').isdigit() else raw_val
                chat_obj = await bot.get_chat(chat_id)
                title = chat_obj.title or "بدون نام"
                
                if chat_obj.username:
                    link_txt = f"[@{escape_markdown(chat_obj.username)}]"
                elif chat_obj.invite_link:
                    link_txt = f"[لینک]({escape_markdown(chat_obj.invite_link)})"
                else:
                    link_txt = "_(خصوصی)_"
                
                status_section = (
                    f"✅ *فعال*\n"
                    f"📢 *کانال:* {escape_markdown(title)}\n"
                    f"🔗 *آدرس:* {link_txt}\n"
                    f"🔢 *آیدی:* `{safe_val}`"
                )
            except:
                status_section = (
                    f"⚠️ *ثبت شده (عدم دسترسی)*\n"
                    f"🔢 *آیدی:* `{safe_val}`"
                )
    else:
        status_section = "❌ *غیرفعال*"

    # 4. چیدمان نهایی پیام
    text = (
        f"⚙️ *تنظیمات {type_name}*\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔻 *وضعیت فعلی:* {status_section}\n" 
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👇 *برای تغییر، مقدار جدید را ارسال کنید:*\n"
        f"{help_text}"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
    
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
    
    chan_type = state.get('chan_type')
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    text = message.text.strip()
    
    # اعتبارسنجی ورودی
    if chan_type == 'support':
        # برای پشتیبانی هر متنی (مثل یوزرنیم) قابل قبول است
        if len(text) < 3:
             await _safe_edit(user_id, state['msg_id'], "❌ یوزرنیم خیلی کوتاه است.", reply_markup=None)
             return
    else:
        # برای کانال‌ها باید حتما عدد باشد (مثبت یا منفی)
        if not (text.startswith("-") and text[1:].isdigit()) and not text.isdigit():
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:main"))
            await _safe_edit(user_id, state['msg_id'], "❌ آیدی نامعتبر است. باید عدد باشد (مثلاً -100...)", reply_markup=markup)
            return

    # انتخاب کلید مناسب برای دیتابیس
    if chan_type == 'log':
        config_key = "admin_group_id"
    elif chan_type == 'proof':
        config_key = "proof_channel_id"
    else:
        config_key = "support_username" # ✅ اصلاح شده: هماهنگ با wallet.py
    
    # ذخیره در دیتابیس
    await db.set_config(config_key, text)
    
    # پاک کردن وضعیت
    if user_id in admin_conversations:
        del admin_conversations[user_id]
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="admin:settings:main"))
    
    # اسکیپ کردن متن برای نمایش صحیح
    safe_text = text.replace("_", "\\_").replace("*", "\\*")
    
    await _safe_edit(
        user_id, state['msg_id'], 
        f"✅ *{state.get('chan_type')} با موفقیت ثبت شد\\.*\nمقدار: `{safe_text}`", 
        reply_markup=markup, parse_mode='MarkdownV2'
    )