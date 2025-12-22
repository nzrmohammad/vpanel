# bot/admin_handlers/settings.py

import time
import logging
from telebot import types
from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

logger = logging.getLogger(__name__)

# متغیرهای گلوبال وضعیت
bot = None
admin_conversations = {}

# =========================================================
# 🛠 تنظیمات مرکزی ربات (قابل تغییر در دیتابیس)
# =========================================================
# تمام متغیرهایی که می‌خواهید ادمین بتواند تغییر دهد اینجا تعریف می‌شوند.

BOT_CONFIGS = {
    # --- 📢 کانال‌ها و ارتباطات ---
    'support_username': {
        'category': 'channels', 'title': '☎️ اکانت پشتیبانی', 'type': 'str',
        'desc': 'یوزرنیم اکانت پشتیبانی (بدون @)', 'def': 'admin'
    },
    'admin_group_id': {
        'category': 'channels', 'title': '📢 کانال گزارشات', 'type': 'int',
        'desc': 'آیدی عددی کانال/گروه برای لاگ‌ها', 'def': '0'
    },
    'proof_channel_id': {
        'category': 'channels', 'title': '🧾 کانال رسیدها', 'type': 'int',
        'desc': 'آیدی عددی کانال رسیدهای واریزی', 'def': '0'
    },

    # --- 👥 سیستم رفرال (دعوت دوستان) ---
    'enable_referral_system': {
        'category': 'referral', 'title': '👥 سیستم رفرال', 'type': 'bool',
        'desc': 'فعال یا غیرفعال کردن سیستم دعوت دوستان', 'def': 'True'
    },
    'referral_reward_gb': {
        'category': 'referral', 'title': '🎁 حجم هدیه رفرال (GB)', 'type': 'int',
        'desc': 'حجم هدیه برای هر معرفی موفق', 'def': '10'
    },
    'referral_reward_days': {
        'category': 'referral', 'title': '⏳ روز هدیه رفرال', 'type': 'int',
        'desc': 'تعداد روز هدیه برای هر معرفی موفق', 'def': '5'
    },
    'ambassador_badge_threshold': {
        'category': 'referral', 'title': '🏅 حدنصاب نشان سفیر', 'type': 'int',
        'desc': 'تعداد معرفی لازم برای دریافت نشان سفیر', 'def': '5'
    },

    # --- 🔄 انتقال حجم (Transfer) ---
    'enable_traffic_transfer': {
        'category': 'transfer', 'title': '🔄 انتقال حجم', 'type': 'bool',
        'desc': 'قابلیت انتقال حجم بین کاربران', 'def': 'True'
    },
    'min_transfer_gb': {
        'category': 'transfer', 'title': '🔽 حداقل انتقال (GB)', 'type': 'int',
        'desc': 'حداقل حجم قابل انتقال', 'def': '1'
    },
    'max_transfer_gb': {
        'category': 'transfer', 'title': '🔼 حداکثر انتقال (GB)', 'type': 'int',
        'desc': 'حداکثر حجم قابل انتقال در هر بار', 'def': '20'
    },
    'transfer_cooldown_days': {
        'category': 'transfer', 'title': '⏱ کول‌داون انتقال (روز)', 'type': 'int',
        'desc': 'فاصله زمانی مجاز بین دو انتقال', 'def': '10'
    },

    # --- 🎁 هدیه، قرعه‌کشی و تشویقی ---
    'birthday_gift_gb': {
        'category': 'gift', 'title': '🎂 حجم هدیه تولد (GB)', 'type': 'int',
        'desc': 'مقدار حجم هدیه تولد', 'def': '1'
    },
    'birthday_gift_days': {
        'category': 'gift', 'title': '⏳ اعتبار هدیه تولد', 'type': 'int',
        'desc': 'اعتبار هدیه تولد (روز)', 'def': '3'
    },
    'enable_lucky_lottery': {
        'category': 'gift', 'title': '🍀 قرعه‌کشی شانس', 'type': 'bool',
        'desc': 'فعال‌سازی سیستم قرعه‌کشی تصادفی', 'def': 'True'
    },
    'lucky_lottery_badge_requirement': {
        'category': 'gift', 'title': '🎟 امتیاز لازم قرعه‌کشی', 'type': 'int',
        'desc': 'امتیاز لازم برای شرکت در قرعه‌کشی', 'def': '20'
    },

    # --- ⚠️ تنظیمات هشدار ---
    'warning_usage_threshold': {
        'category': 'warning', 'title': '⚠️ درصد هشدار مصرف', 'type': 'int',
        'desc': 'هشدار در درصد مصرف (مثلاً 80)', 'def': '80'
    },
    'daily_usage_alert_threshold_gb': {
        'category': 'warning', 'title': '📈 هشدار مصرف روزانه', 'type': 'int',
        'desc': 'هشدار مصرف بیش از حد مجاز در یک روز (GB)', 'def': '2'
    },
    'notify_admin_on_usage': {
        'category': 'warning', 'title': '🔔 اطلاع به ادمین', 'type': 'bool',
        'desc': 'ارسال گزارش مصرف بالا به ادمین', 'def': 'True'
    },

    # --- ⚙️ تنظیمات سیستمی و زمان‌بندی ---
    'daily_report_time': {
        'category': 'system', 'title': '⏰ زمان گزارش روزانه', 'type': 'str',
        'desc': 'فرمت HH:MM (مثلاً 23:57)', 'def': '23:57'
    },
    'cleanup_time': {
        'category': 'system', 'title': '🧹 زمان پاکسازی', 'type': 'str',
        'desc': 'فرمت HH:MM (مثلاً 00:01)', 'def': '00:01'
    },
    'random_servers_count': {
        'category': 'system', 'title': '🎲 تعداد سرور رندوم', 'type': 'int',
        'desc': 'تعداد سرورهای پیشنهادی به کاربر', 'def': '10'
    },
    'warning_days_before_expiry': {
        'category': 'system', 'title': '📅 هشدار انقضا (روز)', 'type': 'int',
        'desc': 'چند روز قبل انقضا هشدار دهیم؟', 'def': '3'
    },
    'welcome_message_delay_hours': {
        'category': 'system', 'title': '⏳ تاخیر خوش‌آمد', 'type': 'int',
        'desc': 'تاخیر پیام خوش‌آمد (ساعت)', 'def': '24'
    },
    'usage_warning_check_hours': {
        'category': 'system', 'title': '⏰ بازه چک هشدار', 'type': 'int',
        'desc': 'فاصله چک کردن مصرف (ساعت)', 'def': '6'
    },
    'online_report_update_hours': {
        'category': 'system', 'title': '🔄 آپدیت آنلاین', 'type': 'int',
        'desc': 'بازه آپدیت گزارش آنلاین (ساعت)', 'def': '1'
    }
}

def initialize_settings_handlers(bot_instance, state_dict):
    global bot, admin_conversations
    bot = bot_instance
    admin_conversations = state_dict

# =========================================================
# 1. منوی اصلی تنظیمات
# =========================================================

async def settings_main_panel(call: types.CallbackQuery, params: list):
    """نمایش منوی اصلی تنظیمات"""
    user_id = call.from_user.id
    if user_id in admin_conversations: del admin_conversations[user_id]
    
    mode = params[0] if params else 'main'
    
    # --- بخش کیف پول ---
    if mode == 'wallet':
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💎 کریپتو (Crypto)", callback_data="admin:pay_methods:crypto"),
            types.InlineKeyboardButton("💳 کارت‌های بانکی", callback_data="admin:pay_methods:card")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
        
        text = "💰 *مدیریت روش‌های پرداخت*\n\nلطفاً نوع روش پرداخت مورد نظر را انتخاب کنید:"
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')
        return

    # --- منوی اصلی ---
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # ردیف 1
    markup.add(
        types.InlineKeyboardButton("📢 کانال‌ها", callback_data="admin:sys_conf:list:channels"),
        types.InlineKeyboardButton("⚙️ سیستم و زمان‌بندی", callback_data="admin:sys_conf:list:system")
    )
    # ردیف 2
    markup.add(
        types.InlineKeyboardButton("👥 رفرال و دعوت", callback_data="admin:sys_conf:list:referral"),
        types.InlineKeyboardButton("🔄 انتقال حجم", callback_data="admin:sys_conf:list:transfer")
    )
    # ردیف 3
    markup.add(
        types.InlineKeyboardButton("🎁 جوایز و قرعه‌کشی", callback_data="admin:sys_conf:list:gift"),
        types.InlineKeyboardButton("⚠️ هشدارها", callback_data="admin:sys_conf:list:warning")
    )
    
    markup.add(types.InlineKeyboardButton("💰 مدیریت کیف پول و کارت‌ها", callback_data="admin:settings:wallet"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin:panel"))
    
    text = (
        "⚙️ *پنل تنظیمات پیشرفته*\n\n"
        "تمام تنظیمات ربات به صورت یکپارچه در دسته‌بندی‌های بالا قرار دارند\\.\n"
        "برای تغییر هر بخش، روی دکمه مربوطه کلیک کنید\\."
    )
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

# =========================================================
# 2. هندلرهای سیستم (با MarkdownV2 Safe)
# =========================================================

async def list_config_category(call: types.CallbackQuery, params: list):
    """نمایش آیتم‌های یک دسته‌بندی"""
    if not params: return
    category = params[0]
    user_id = call.from_user.id
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # مرتب‌سازی کلیدها برای نمایش منظم
    sorted_keys = sorted([k for k, v in BOT_CONFIGS.items() if v.get('category') == category])
    
    for key in sorted_keys:
        info = BOT_CONFIGS[key]
        val = await db.get_config(key, info['def'])
        
        if info['type'] == 'bool':
            status = "✅ فعال" if str(val).lower() == 'true' else "❌ غیرفعال"
            btn_text = f"{info['title']}: {status}"
        else:
            val_str = str(val)
            # نمایش خلاصه‌تر برای متن‌های طولانی
            if len(val_str) > 20: val_str = val_str[:17] + "..."
            btn_text = f"{info['title']}: {val_str}"
            
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:sys_conf:edit:{key}"))
        
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
    
    cat_names = {
        'channels': 'کانال‌ها و ارتباطات', 
        'gift': 'جوایز و قرعه‌کشی', 
        'warning': 'هشدارهای سیستم', 
        'system': 'سیستمی و زمان‌بندی',
        'referral': 'سیستم رفرال',
        'transfer': 'انتقال حجم'
    }
    cat_title = cat_names.get(category, category)
    safe_cat_title = escape_markdown(cat_title)
    
    text = f"📂 *تنظیمات {safe_cat_title}*\n\nبرای ویرایش هر مورد روی آن کلیک کنید:"
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

async def edit_config_start(call: types.CallbackQuery, params: list):
    """شروع ویرایش"""
    key = params[0]
    if key not in BOT_CONFIGS: return
    
    info = BOT_CONFIGS[key]
    user_id = call.from_user.id
    
    # تغییر مقدار Boolean به صورت دکمه‌ای (بدون نیاز به تایپ)
    if info['type'] == 'bool':
        current = await db.get_config(key, info['def'])
        new_val = "False" if str(current).lower() == 'true' else "True"
        await db.set_config(key, new_val)
        return await list_config_category(call, [info['category']])
    
    # دریافت ورودی متنی/عددی
    current_val = await db.get_config(key, info['def'])
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data=f"admin:sys_conf:list:{info['category']}"))
    
    safe_title = escape_markdown(info['title'])
    safe_desc = escape_markdown(info['desc'])
    safe_val = escape_markdown(str(current_val))
    
    text = (
        f"✍️ *ویرایش: {safe_title}*\n\n"
        f"📝 توضیح: {safe_desc}\n"
        f"🔹 مقدار فعلی: `{safe_val}`\n\n"
        f"👇 لطفاً مقدار جدید را ارسال کنید:"
    )
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')
    
    admin_conversations[user_id] = {
        'action_type': 'save_sys_config',
        'next_handler': process_config_save,
        'key': key,
        'msg_id': call.message.message_id,
        'timestamp': time.time()
    }

async def process_config_save(message: types.Message):
    """ذخیره نهایی"""
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    key = state['key']
    info = BOT_CONFIGS[key]
    value = message.text.strip()
    
    # اعتبارسنجی عددی
    if info['type'] == 'int':
        if not (value.lstrip('-').isdigit()):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data=f"admin:sys_conf:list:{info['category']}"))
            err_text = "❌ خطا: لطفاً فقط *عدد* وارد کنید\\."
            await _safe_edit(user_id, state['msg_id'], err_text, reply_markup=markup, parse_mode='MarkdownV2')
            return
            
    # اعتبارسنجی زمان (فرمت HH:MM)
    if 'time' in key and ':' not in value:
         markup = types.InlineKeyboardMarkup()
         markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data=f"admin:sys_conf:list:{info['category']}"))
         err_text = "❌ خطا: لطفاً فرمت زمان را به صورت *HH:MM* (مثلاً 23:57) وارد کنید\\."
         await _safe_edit(user_id, state['msg_id'], err_text, reply_markup=markup, parse_mode='MarkdownV2')
         return

    await db.set_config(key, value)
    del admin_conversations[user_id]
    
    safe_title = escape_markdown(info['title'])
    msg_text = f"✅ تنظیمات *{safe_title}* ذخیره شد\\."
    
    await bot.send_message(user_id, msg_text, disable_notification=True, parse_mode='MarkdownV2')
    
    class FakeCall:
        def __init__(self, u_id, m_id):
            self.from_user = type('User', (), {'id': u_id})()
            self.message = type('Message', (), {'message_id': m_id})()
            
    await list_config_category(FakeCall(user_id, state['msg_id']), [info['category']])

# =========================================================
# 3. بخش‌های قدیمی (کارت بانکی و کیف پول)
# =========================================================

async def list_payment_methods(call: types.CallbackQuery, params: list):
    user_id = call.from_user.id
    if user_id in admin_conversations: del admin_conversations[user_id]

    if not params: return
    method_type = params[0]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    header_text = ""

    if method_type == 'crypto':
        current_rate = await db.get_config('usdt_rate', '60000')
        markup.add(types.InlineKeyboardButton(
            f"💰 نرخ تتر: {int(current_rate):,} تومان (ویرایش)", 
            callback_data="admin:edit_usdt_rate"
        ))
        
        safe_rate = escape_markdown(f"{int(current_rate):,}")
        header_text = f"💵 *نرخ فعلی تتر:* `{safe_rate}` تومان\n\n"

    methods = await db.get_payment_methods(method_type, active_only=False)
    type_title = "کارت‌های بانکی" if method_type == 'card' else "کیف پول‌های کریپتو"
    
    safe_header = escape_markdown(f"مدیریت {type_title}")
    text = f"📋 *{safe_header}*\n\n{header_text}لیست روش‌های تعریف شده:\n"
    
    if not methods:
        text += "_هیچ موردی یافت نشد\\._"
    else:
        for m in methods:
            safe_title = escape_markdown(m['title'])
            is_active = m.get('is_active', True)
            status_icon = "✅" if is_active else "❌"
            
            markup.add(types.InlineKeyboardButton(
                f"{status_icon} {m['title']}", 
                callback_data=f"admin:toggle_method:{m['id']}:{method_type}"
            ))
            markup.add(types.InlineKeyboardButton(
                f"🗑 حذف {m['title']}", 
                callback_data=f"admin:del_method:{m['id']}:{method_type}"
            ))
            
            raw_details = m['details'].get('card_number') if method_type == 'card' else m['details'].get('network')
            safe_details = escape_markdown(str(raw_details)) if raw_details else ""
            
            text += f"🔹 {safe_title}\n`{safe_details}`\n\n"

    add_text = "➕ افزودن کارت جدید" if method_type == 'card' else "➕ افزودن ولت جدید"
    markup.add(types.InlineKeyboardButton(add_text, callback_data=f"admin:add_method:{method_type}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:wallet"))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

async def delete_payment_method_handler(call: types.CallbackQuery, params: list):
    if len(params) < 2: return
    await db.delete_payment_method(int(params[0]))
    await bot.answer_callback_query(call.id, "✅ حذف شد.")
    await list_payment_methods(call, [params[1]])

async def toggle_payment_method_handler(call: types.CallbackQuery, params: list):
    if len(params) < 2: return
    await db.toggle_payment_method(int(params[0]))
    await bot.answer_callback_query(call.id, "✅ وضعیت تغییر کرد.")
    await list_payment_methods(call, [params[1]])

async def edit_usdt_rate_start(call: types.CallbackQuery, params: list):
    user_id = call.from_user.id
    current = await db.get_config('usdt_rate', '60000')
    safe_current = escape_markdown(current)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:pay_methods:crypto"))
    
    text = f"💰 نرخ فعلی: `{safe_current}`\nقیمت جدید را وارد کنید:"
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')
    
    admin_conversations[user_id] = {
        'action_type': 'set_usdt_rate', 'next_handler': process_usdt_rate_input,
        'msg_id': call.message.message_id, 'timestamp': time.time()
    }

async def process_usdt_rate_input(message: types.Message):
    user_id = message.from_user.id
    if user_id not in admin_conversations: return
    state = admin_conversations[user_id]
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    
    if not message.text.isdigit():
        return await bot.send_message(user_id, "❌ لطفاً عدد وارد کنید.")

    await db.set_config('usdt_rate', message.text.strip())
    del admin_conversations[user_id]
    class FakeCall:
        def __init__(self): 
            self.from_user = type('U',(),{'id':user_id})()
            self.message = type('M',(),{'message_id':state['msg_id']})()
    await list_payment_methods(FakeCall(), ['crypto'])

async def start_add_method(call: types.CallbackQuery, params: list):
    method_type = params[0]
    user_id = call.from_user.id
    msg_id = call.message.message_id
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:settings:wallet"))
    
    if method_type == 'card':
        text = "🏦 لطفاً *نام بانک* را وارد کنید:\nمثال: `بانک ملت`"
        action = 'add_card_step1'
        handler = process_card_step_1_bank
    else:
        text = "💎 *آدرس کیف پول* را ارسال کنید:"
        action = 'add_crypto_step1'
        handler = process_crypto_step_1_address
        
    await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='MarkdownV2')
    admin_conversations[user_id] = {
        'action_type': action, 'next_handler': handler,
        'method_type': method_type, 'data': {}, 'msg_id': msg_id, 'timestamp': time.time()
    }

async def process_card_step_1_bank(message: types.Message):
    user_id = message.from_user.id
    state = admin_conversations.get(user_id)
    if not state: return
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    state['data']['bank_name'] = message.text.strip()
    
    text = "💳 لطفاً *شماره کارت* را وارد کنید:"
    await _safe_edit(user_id, state['msg_id'], text, reply_markup=None, parse_mode='MarkdownV2')
    state['next_handler'] = process_card_step_2_number

async def process_card_step_2_number(message: types.Message):
    user_id = message.from_user.id
    state = admin_conversations.get(user_id)
    if not state: return
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    state['data']['card_number'] = message.text.strip()
    
    text = "👤 لطفاً *نام صاحب حساب* را وارد کنید:"
    await _safe_edit(user_id, state['msg_id'], text, reply_markup=None, parse_mode='MarkdownV2')
    state['next_handler'] = process_card_step_3_holder

async def process_card_step_3_holder(message: types.Message):
    user_id = message.from_user.id
    state = admin_conversations.get(user_id)
    if not state: return
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    state['data']['card_holder'] = message.text.strip()
    await save_payment_method(user_id, state, 'card', state['data'])

async def process_crypto_step_1_address(message: types.Message):
    user_id = message.from_user.id
    state = admin_conversations.get(user_id)
    if not state: return
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    state['data']['address'] = message.text.strip()
    
    text = "🌐 لطفاً *شبکه \\(Network\\)* را وارد کنید \\(مثال: TRC20\\):"
    await _safe_edit(user_id, state['msg_id'], text, reply_markup=None, parse_mode='MarkdownV2')
    state['next_handler'] = process_crypto_step_2_network

async def process_crypto_step_2_network(message: types.Message):
    user_id = message.from_user.id
    state = admin_conversations.get(user_id)
    if not state: return
    try: await bot.delete_message(user_id, message.message_id)
    except: pass
    state['data']['network'] = message.text.strip().upper()
    await save_payment_method(user_id, state, 'crypto', state['data'])

async def save_payment_method(user_id, state, method_type, data):
    title = f"{data['bank_name']} - {data['card_holder']}" if method_type == 'card' else f"Tether ({data['network']})"
    await db.add_payment_method(method_type, title, data)
    del admin_conversations[user_id]
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:pay_methods:{method_type}"))
    
    text = "✅ با موفقیت اضافه شد\\."
    await _safe_edit(user_id, state['msg_id'], text, reply_markup=markup, parse_mode='MarkdownV2')