# bot/user_handlers/account.py

import logging
from telebot import types
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards.user import user_keyboard as user_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.language import get_string
from bot.services.account_service import account_service

logger = logging.getLogger(__name__)

# =============================================================================
# 1. نمایش منوی مدیریت یک سرویس (وقتی روی دکمه سرویس کلیک می‌شود)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('acc_'))
async def account_details_handler(call: types.CallbackQuery):
    """نمایش جزئیات و دکمه‌های مدیریت یک سرویس خاص"""
    user_id = call.from_user.id
    # فرمت کال‌بک: acc_{id} که id همان شناسه جدول uuids است
    try:
        acc_db_id = int(call.data.split('_')[1])
    except (IndexError, ValueError):
        return

    lang = await db.get_user_language(user_id)
    
    # دریافت UUID واقعی از روی ID دیتابیس
    uuid_record = await db.get_uuid_record_by_id(acc_db_id)
    
    if not uuid_record or uuid_record['user_id'] != user_id:
        await bot.answer_callback_query(call.id, "❌ سرویس یافت نشد.", show_alert=True)
        # رفرش کردن لیست
        await _refresh_account_list(user_id, call.message.message_id, lang)
        return

    uuid_str = uuid_record['uuid']
    name = uuid_record['name']

    # دریافت اطلاعات فنی (حجم و زمان) از سرویس
    details = await account_service.get_service_details(uuid_str, user_id)
    
    # ساخت متن نمایش
    if details:
        usage_gb = f"{details.get('usage_gb', 0):.2f}"
        total_gb = f"{details.get('limit_gb', 0)}"
        expire_date = details.get('expire_date', 'نامحدود')
        state_emoji = "✅" if details.get('enable', True) else "❌"
        
        text = (
            f"👤 **{escape_markdown(name)}**\n\n"
            f"📊 مصرف: `{usage_gb}` / `{total_gb}` گیگابایت\n"
            f"📅 انقضا: {escape_markdown(str(expire_date))}\n"
            f"وضعیت: {state_emoji}"
        )
    else:
        text = f"👤 **{escape_markdown(name)}**\n\n⚠️ اطلاعات مصرف در دسترس نیست."

    # نمایش منوی مدیریت (لینک، تمدید، حذف و...)
    # نکته: ما ID دیتابیس (acc_db_id) را پاس می‌دهیم چون کوتاه‌تر از UUID است
    markup = await user_menu.account_menu(acc_db_id, lang)
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')


# =============================================================================
# 2. دریافت لینک‌های اتصال
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('getlinks_'))
async def get_links_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    acc_db_id = int(call.data.split('_')[1])
    lang = await db.get_user_language(user_id)

    uuid_record = await db.get_uuid_record_by_id(acc_db_id)
    if not uuid_record:
        return

    # نمایش منوی انتخاب نوع لینک (معمولی / Base64)
    markup = await user_menu.get_links_menu(acc_db_id, lang)
    text = escape_markdown(get_string('select_link_type', lang))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: call.data.startswith('getlink_'))
async def show_link_content_handler(call: types.CallbackQuery):
    """نمایش نهایی لینک سابسکریپشن"""
    user_id = call.from_user.id
    data = call.data # getlink_normal_123 یا getlink_b64_123
    parts = data.split('_')
    link_type = parts[1] # normal / b64
    acc_db_id = int(parts[2])
    
    lang = await db.get_user_language(user_id)
    uuid_record = await db.get_uuid_record_by_id(acc_db_id)
    
    if not uuid_record:
        await bot.answer_callback_query(call.id, "Error")
        return

    # درخواست لینک از سرویس
    links = await account_service.generate_subscription_links(uuid_record['uuid'])
    
    final_link = links['sub_link'] if link_type == 'normal' else links['sub_b64']
    
    text = (
        f"🔗 **لینک اتصال شما:**\n\n"
        f"`{final_link}`\n\n"
        f"⚠️ برای اتصال، این لینک را کپی کرده و در نرم‌افزار (V2RayNG/NapsternetV) وارد کنید."
    )
    
    # دکمه بازگشت
    markup = types.InlineKeyboardMarkup()
    markup.add(user_menu.back_btn(f"acc_{acc_db_id}", lang))
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')

# =============================================================================
# 3. تغییر نام سرویس
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('changename_'))
async def ask_new_name_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    acc_db_id = int(call.data.split('_')[1])
    
    # ذخیره استیت برای دریافت پیام متنی
    if not hasattr(bot, 'user_states'): bot.user_states = {}
    bot.user_states[user_id] = {
        'step': 'rename_service',
        'acc_id': acc_db_id,
        'msg_id': call.message.message_id
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 انصراف", callback_data=f"acc_{acc_db_id}"))
    
    text = "✏️ لطفاً نام جدید سرویس را ارسال کنید:"
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: (
    hasattr(bot, 'user_states') and 
    m.from_user.id in bot.user_states and 
    bot.user_states[m.from_user.id].get('step') == 'rename_service'
))
async def do_rename_service(message: types.Message):
    user_id = message.from_user.id
    state = bot.user_states[user_id]
    acc_db_id = state['acc_id']
    msg_id = state['msg_id']
    new_name = message.text.strip()
    
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass
    
    uuid_record = await db.get_uuid_record_by_id(acc_db_id)
    if uuid_record:
        # فراخوانی سرویس برای تغییر نام
        await account_service.rename_service(uuid_record['uuid'], new_name, user_id)
        
    del bot.user_states[user_id]
    
    # بازگشت به منوی سرویس با نام جدید
    # یک کال‌بک ساختگی ایجاد می‌کنیم تا کد تکرار نشود
    fake_call = types.CallbackQuery(id='0', from_user=message.from_user, data=f"acc_{acc_db_id}", message=message)
    fake_call.message.message_id = msg_id
    await account_details_handler(fake_call)


# =============================================================================
# 4. حذف سرویس (فقط از ربات)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
async def delete_service_confirm(call: types.CallbackQuery):
    user_id = call.from_user.id
    acc_db_id = int(call.data.split('_')[1])
    lang = await db.get_user_language(user_id)
    
    # منوی تاییدیه (بله/خیر)
    markup = await user_menu.confirm_action_menu(
        yes_callback=f"confirmdel_{acc_db_id}", 
        no_callback=f"acc_{acc_db_id}", 
        lang_code=lang
    )
    
    text = escape_markdown("⚠️ آیا مطمئن هستید که می‌خواهید این سرویس را از لیست خود حذف کنید؟")
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirmdel_'))
async def delete_service_execute(call: types.CallbackQuery):
    user_id = call.from_user.id
    acc_db_id = int(call.data.split('_')[1])
    lang = await db.get_user_language(user_id)
    
    uuid_record = await db.get_uuid_record_by_id(acc_db_id)
    if uuid_record:
        # درخواست حذف از سرویس
        await account_service.delete_service(uuid_record['uuid'], user_id)
        
    await bot.answer_callback_query(call.id, "🗑 سرویس حذف شد.")
    
    # بازگشت به لیست اصلی
    await _refresh_account_list(user_id, call.message.message_id, lang)

# --- تابع کمکی ---
async def _refresh_account_list(user_id, msg_id, lang):
    """رفرش کردن لیست اکانت‌ها (استفاده مجدد از کیبورد main_menu)"""
    user_uuids = await db.uuids(user_id)
    markup = await user_menu.accounts(user_uuids, lang)
    text = escape_markdown(get_string('account_list_title', lang))
    await _safe_edit(user_id, msg_id, text, reply_markup=markup, parse_mode='Markdown')