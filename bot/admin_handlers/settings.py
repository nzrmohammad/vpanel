# bot/admin_handlers/settings.py

import time
import logging
from telebot import types
from bot.database import db
from bot.db.base import PaymentMethod  # ایمپورت مدل برای کوئری مستقیم
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit

logger = logging.getLogger(__name__)

# متغیرهای گلوبال وضعیت
bot = None
admin_conversations = {}

# =========================================================
# 🛠 تنظیمات مرکزی ربات (قابل تغییر در دیتابیس)
# =========================================================

BOT_CONFIGS = {
    # --- 📢 کانال‌ها و تاپیک‌های مدیریتی ---
    'topic_id_proof': 
    {
        'category': 'channels', 'title': '🧾 رسید', 'type': 'int',
        'desc': 'آیدی تاپیک برای ارسال رسیدها', 'def': '0'
    },
    'main_group_id': 
    {
        'category': 'channels', 'title': '🏢 سوپرگروه', 'type': 'int',
        'desc': 'آیدی عددی سوپرگروهی که تاپیک‌ها در آن قرار دارند', 'def': '0'
    },
    'topic_id_log': 
    {
        'category': 'channels', 'title': '📝 گزارشات', 'type': 'int',
        'desc': 'آیدی تاپیک برای لاگ‌های سیستم', 'def': '0'
    },
    'topic_id_shop': 
    {
        'category': 'channels', 'title': '🛒 خریدها', 'type': 'int',
        'desc': 'آیدی تاپیک برای ارسال گزارش خرید و تمدید', 'def': '0'
    },
    'ticket_auto_delete_time': 
    {
        'category': 'channels','title': '⏳ حذف خودکار', 'type': 'int',
        'desc': 'مدت زمان مکث قبل از حذف پیام', 'def': '30'
    },
    'topic_id_support': 
    {
        'category': 'channels', 'title': '🙋‍♂️ پشتیبانی', 'type': 'int',
        'desc': 'آیدی تاپیک برای ارسال تیکت‌ها', 'def': '0'
    },

    # --- 👥 سیستم رفرال (دعوت دوستان) ---
    'enable_referral_system': 
    {
        'category': 'referral', 'title': '👥 سیستم رفرال', 'type': 'bool',
        'desc': 'فعال یا غیرفعال کردن سیستم دعوت دوستان', 'def': 'True'
    },
    'referral_reward_gb': 
    {
        'category': 'referral', 'title': '🎁 حجم هدیه رفرال (GB)', 'type': 'int',
        'desc': 'حجم هدیه برای هر معرفی موفق', 'def': '5'
    },
    'referral_reward_days': 
    {
        'category': 'referral', 'title': '⏳ روز هدیه رفرال', 'type': 'int',
        'desc': 'تعداد روز هدیه برای هر معرفی موفق', 'def': '3'
    },

    # --- 🎁 هدیه، قرعه‌کشی و تشویقی ---
    'birthday_gift_gb': 
    {
        'category': 'gift', 'title': '🎂 حجم هدیه تولد (GB)', 'type': 'int',
        'desc': 'مقدار حجم هدیه تولد', 'def': '10'
    },
    'birthday_gift_days': 
    {
        'category': 'gift', 'title': '⏳ اعتبار هدیه تولد', 'type': 'int',
        'desc': 'اعتبار هدیه تولد (روز)', 'def': '10'
    },

    # --- ⚠️ تنظیمات هشدار ---
    'warning_usage_threshold': {
        'category': 'warning', 'title': '⚠️ هشدار مصرف', 'type': 'int',
        'desc': 'هشدار در درصد مصرف', 'def': '95'
    },
    # --- 📊 تنظیمات گزارش‌گیری (اضافه شده) ---
    'report_page_size': {
        'category': 'reporting', 'title': '📄 تعداد در صفحه', 'type': 'int',
        'desc': 'تعداد آیتم‌ها در هر صفحه گزارش', 'def': '15'
    },
    'report_online_window': {
        'category': 'reporting', 'title': '⏱ بازه آنلاین (دقیقه)', 'type': 'int',
        'desc': 'ملاک آنلاین بودن کاربر (دقیقه اخیر)', 'def': '3'
    },

    # --- ⚙️ تنظیمات سیستمی و زمان‌بندی ---
    'daily_report_time': 
    {
        'category': 'system', 'title': '⏰ زمان گزارش روزانه', 'type': 'str',
        'desc': 'فرمت HH:MM (مثلاً 23:57)', 'def': '23:57'
    },
    'cleanup_time': 
    {
        'category': 'system', 'title': '🧹 زمان پاکسازی', 'type': 'str',
        'desc': 'فرمت HH:MM (مثلاً 00:01)', 'def': '00:01'
    },
    'random_servers_count': 
    {
        'category': 'system', 'title': '🎲 تعداد سرور رندوم', 'type': 'int',
        'desc': 'تعداد سرورهای پیشنهادی به کاربر', 'def': '10'
    },
    'warning_days_before_expiry': 
    {
        'category': 'system', 'title': '📅 هشدار انقضا (روز)', 'type': 'int',
        'desc': 'چند روز قبل انقضا هشدار دهیم؟', 'def': '3'
    },
    'welcome_message_delay_hours': 
    {
        'category': 'system', 'title': '⏳ تاخیر خوش‌آمد', 'type': 'int',
        'desc': 'تاخیر پیام خوش‌آمد (ساعت)', 'def': '24'
    },
    'online_report_update_hours': 
    {
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
        types.InlineKeyboardButton("⚙️ زمان‌بندی", callback_data="admin:sys_conf:list:system"),
        types.InlineKeyboardButton("📢 کانال‌ها", callback_data="admin:sys_conf:list:channels")
        
    )
    # ردیف 2
    markup.add(
        types.InlineKeyboardButton("👥 دعوت", callback_data="admin:sys_conf:list:referral"),
        types.InlineKeyboardButton("💰 کیف پول", callback_data="admin:settings:wallet")
    )
    # ردیف 3
    markup.add(
        types.InlineKeyboardButton("⚠️ هشدارها", callback_data="admin:sys_conf:list:warning"),
        types.InlineKeyboardButton("🎁 جوایز", callback_data="admin:sys_conf:list:gift")
    )

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
    """نمایش آیتم‌های یک دسته‌بندی با قابلیت نمایش نام گروه"""
    if not params: return
    category = params[0]
    user_id = call.from_user.id
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    sorted_keys = [k for k, v in BOT_CONFIGS.items() if v.get('category') == category]
    buttons = [] # 2. ایجاد لیست برای جمع‌آوری دکمه‌ها
    
    for key in sorted_keys:
        info = BOT_CONFIGS[key]
        val = await db.get_config(key, info['def'])
        
        btn_text = ""
        
        if info['type'] == 'bool':
            status = "✅" if str(val).lower() == 'true' else "❌"
            btn_text = f"{status} {info['title']}"
        
        elif key == 'main_group_id' and val and str(val) != '0':
            try:
                chat = await bot.get_chat(int(val))
                chat_title = chat.title if chat.title else "نامشخص"
                if len(chat_title) > 15: chat_title = chat_title[:12] + "..."
                btn_text = f"{info['title']}: {chat_title}"
            except Exception as e:
                btn_text = f"{info['title']}: ❌"
        
        else:
            val_str = str(val)
            if len(val_str) > 10: val_str = val_str[:7] + "..."
            btn_text = f"{info['title']}: {val_str}"
            
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"admin:sys_conf:edit:{key}"))
        
    if buttons:
        markup.add(*buttons)
        
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:main"))
    
    cat_names = {
        'channels': 'کانال‌ها و ارتباطات', 
        'gift': 'جوایز و قرعه‌کشی', 
        'warning': 'هشدارهای سیستم', 
        'system': 'سیستمی و زمان‌بندی',
        'referral': 'سیستم رفرال',
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
    
    back_markup = types.InlineKeyboardMarkup()
    back_markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin:sys_conf:list:{info['category']}"))

    if info['type'] == 'int':
        if not (value.lstrip('-').isdigit()):
            err_text = "❌ خطا: لطفاً فقط *عدد* وارد کنید\\."
            await _safe_edit(user_id, state['msg_id'], err_text, reply_markup=back_markup, parse_mode='MarkdownV2')
            return
            
    if 'time' in key and ':' not in value:
         err_text = "❌ خطا: لطفاً فرمت زمان را به صورت *HH:MM* (مثلاً 23:57) وارد کنید\\."
         await _safe_edit(user_id, state['msg_id'], err_text, reply_markup=back_markup, parse_mode='MarkdownV2')
         return

    await db.set_config(key, value)
    del admin_conversations[user_id]
    
    safe_title = escape_markdown(info['title'])
    safe_val = escape_markdown(value)
    
    msg_text = (
        f"✅ تنظیمات *{safe_title}* با موفقیت ذخیره شد\\.\n\n"
        f"🔹 مقدار جدید: `{safe_val}`"
    )
    
    await _safe_edit(user_id, state['msg_id'], msg_text, reply_markup=back_markup, parse_mode='MarkdownV2')

# =========================================================
# 3. بخش مدیریت کارت‌های بانکی و کیف پول (اصلاح شده)
# =========================================================

async def list_payment_methods(call: types.CallbackQuery, params: list):
    """نمایش لیست روش‌ها (کلیک برای جزئیات)"""
    user_id = call.from_user.id
    if user_id in admin_conversations: del admin_conversations[user_id]

    if not params: return
    method_type = params[0]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    header_text = ""

    # بخش نرخ تتر برای کریپتو
    if method_type == 'crypto':
        current_rate = await db.get_config('usdt_rate', '60000')
        markup.add(types.InlineKeyboardButton(
            f"💰 نرخ تتر: {int(current_rate):,} تومان (ویرایش)", 
            callback_data="admin:edit_usdt_rate"
        ))
        
        safe_rate = escape_markdown(f"{int(current_rate):,}")
        header_text = f"💵 *نرخ فعلی تتر:* `{safe_rate}` تومان\n\n"

    # دریافت لیست متدها
    methods = await db.get_payment_methods(method_type, active_only=False)
    type_title = "کارت‌های بانکی" if method_type == 'card' else "کیف پول‌های کریپتو"
    
    safe_header = escape_markdown(f"مدیریت {type_title}")
    text = f"📋 *{safe_header}*\n\n{header_text}👇 برای مدیریت هر مورد روی آن کلیک کنید:"
    
    if not methods:
        text += "\n\n_هیچ موردی یافت نشد\\._"
    else:
        for m in methods:
            # فقط عنوان نمایش داده شود (وضعیت با آیکون)
            is_active = m.get('is_active', True)
            status_icon = "✅" if is_active else "❌"
            btn_text = f"{status_icon} {m['title']}"
            
            # کلیک روی دکمه -> رفتن به منوی مدیریت تکی (manage)
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"admin:pm_manage:{m['id']}:{method_type}"))

    add_text = "➕ افزودن کارت جدید" if method_type == 'card' else "➕ افزودن ولت جدید"
    markup.add(types.InlineKeyboardButton(add_text, callback_data=f"admin:add_method:{method_type}"))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin:settings:wallet"))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

async def manage_single_payment_method(call: types.CallbackQuery, params: list):
    """منوی مدیریت تکی (حذف / تغییر وضعیت)"""
    if len(params) < 2: return
    method_id = int(params[0])
    method_type = params[1]
    
    user_id = call.from_user.id
    
    # دریافت اطلاعات دقیق متد
    method = await db.get_by_id(PaymentMethod, method_id)
    if not method:
        await bot.answer_callback_query(call.id, "❌ آیتم یافت نشد.")
        return await list_payment_methods(call, [method_type])
        
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # دکمه‌های عملیاتی
    status_text = "غیرفعال کردن ❌" if method.is_active else "فعال کردن ✅"
    markup.add(
        types.InlineKeyboardButton(status_text, callback_data=f"admin:pm_toggle:{method_id}:{method_type}"),
        types.InlineKeyboardButton("🗑 حذف", callback_data=f"admin:pm_del:{method_id}:{method_type}")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"admin:pay_methods:{method_type}"))
    
    # آماده‌سازی متن نمایش
    safe_title = escape_markdown(method.title)
    status_label = "فعال ✅" if method.is_active else "غیرفعال ❌"
    
    details_text = ""
    if method_type == 'card':
        bn = escape_markdown(str(method.details.get('bank_name', '')))
        cn = escape_markdown(str(method.details.get('card_number', '')))
        ch = escape_markdown(str(method.details.get('card_holder', '')))
        details_text = (
            f"🏦 بانک: {bn}\n"
            f"💳 شماره: `{cn}`\n"
            f"👤 صاحب حساب: {ch}"
        )
    else:
        addr = escape_markdown(str(method.details.get('address', '')))
        net = escape_markdown(str(method.details.get('network', '')))
        details_text = (
            f"🌐 شبکه: {net}\n"
            f"💎 آدرس: `{addr}`"
        )

    text = (
        f"⚙️ *مدیریت: {safe_title}*\n\n"
        f"وضعیت: {status_label}\n\n"
        f"{details_text}\n\n"
        f"👇 عملیات مورد نظر را انتخاب کنید:"
    )
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')

async def delete_payment_method_handler(call: types.CallbackQuery, params: list):
    """حذف و بازگشت به لیست اصلی"""
    if len(params) < 2: return
    await db.delete_payment_method(int(params[0]))
    await bot.answer_callback_query(call.id, "✅ با موفقیت حذف شد.")
    # بازگشت به لیست
    await list_payment_methods(call, [params[1]])

async def toggle_payment_method_handler(call: types.CallbackQuery, params: list):
    """تغییر وضعیت و بازگشت به منوی تکی"""
    if len(params) < 2: return
    await db.toggle_payment_method(int(params[0]))
    await bot.answer_callback_query(call.id, "✅ وضعیت تغییر کرد.")
    # بازگشت به منوی تکی (رفرش شدن صفحه)
    await manage_single_payment_method(call, params)

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
    
    # دکمه انصراف برای مواقعی که کاربر منصرف می‌شود
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="admin:pay_methods:crypto"))

    # اعتبارسنجی ورودی
    if not message.text.isdigit():
        err_text = (
            "❌ *خطا: مقدار وارد شده معتبر نیست\\.*\n\n"
            "لطفاً فقط *عدد* \\(قیمت به تومان\\) وارد کنید:"
        )
        await _safe_edit(user_id, state['msg_id'], err_text, reply_markup=markup, parse_mode='MarkdownV2')
        return 

    # ذخیره در دیتابیس
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