# bot/user_handlers/main_menu.py

import logging
from telebot import types

# --- Imports ---
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.parsers import _UUID_RE
from bot.language import get_string
from bot.config import ADMIN_IDS
from bot import combined_handler

logger = logging.getLogger(__name__)

# =============================================================================
# 1. دستور Start و منوی اصلی
# =============================================================================

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
    """نقطه ورود کاربر به ربات"""
    user_id = message.from_user.id
    
    # ثبت یا بروزرسانی اطلاعات کاربر در دیتابیس
    await db.add_or_update_user(
        user_id, 
        message.from_user.username, 
        message.from_user.first_name, 
        message.from_user.last_name
    )
    
    # بررسی سیستم معرف (Referral)
    referral_status = await db.get_config('enable_referral_system', 'True')
    is_referral_enabled = referral_status.lower() == 'true'
    
    args = message.text.split()
    if len(args) > 1 and is_referral_enabled:
        referral_code = args[1]
        referrer_info = await db.get_referrer_info(user_id)
        if not referrer_info:
            await db.set_referrer(user_id, referral_code)

    # --- نمایش منو ---
    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    user_uuids = await db.uuids(user_id)
    
    if user_uuids or is_admin:
        text = get_string('main_menu_title', lang)
        markup = await user_menu.main(is_admin, lang)
    else:
        # اگر کاربر سرویس ندارد، از او می‌خواهیم کانفیگ بفرستد
        text = get_string('start_prompt', lang)
        markup = types.ReplyKeyboardRemove()
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)


# =============================================================================
# 2. هندلر ورود با کانفیگ (UUID Login)
# =============================================================================

@bot.message_handler(regexp=_UUID_RE.pattern)
async def handle_uuid_login(message: types.Message):
    """
    تشخیص UUID ارسال شده توسط کاربر و اضافه کردن آن به لیست اکانت‌ها.
    """
    user_id = message.from_user.id
    
    # جلوگیری از تداخل با عملیات ادمین (اگر ادمین در حال انجام کاری باشد)
    if user_id in ADMIN_IDS and hasattr(bot, 'context_state') and user_id in bot.context_state:
        return 

    uuid_str = message.text.strip()
    lang = await db.get_user_language(user_id)
    
    # ۱. حذف پیام کاربر برای تمیز ماندن چت
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

    # ۲. نمایش پیام "در حال بررسی"
    wait_msg = await bot.send_message(message.chat.id, "⏳ در حال بررسی ...")

    try:
        # استعلام وضعیت سرویس از پنل‌ها
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if info:
            # اگر سرویس معتبر بود، ثبت کن
            name = info.get('name') or message.from_user.first_name or "My Config"
            result = await db.add_uuid(user_id, uuid_str, name)
            
            if result in ["db_msg_uuid_added", "db_msg_uuid_reactivated"]:
                success_text = get_string(result, lang)
                
                # دریافت لیست اکانت‌ها برای نمایش
                accounts = await db.uuids(user_id)
                
                # بروزرسانی درصد مصرف اکانت‌ها (اختیاری ولی برای نمایش بهتر است)
                if accounts:
                    for acc in accounts:
                        try:
                            u_str = str(acc['uuid'])
                            u_info = await combined_handler.get_combined_user_info(u_str)
                            if u_info:
                                acc['usage_percentage'] = u_info.get('usage_percentage', 0)
                                acc['expire'] = u_info.get('expire')
                        except: pass
                
                # نمایش لیست اکانت‌ها به جای منوی اصلی
                markup = await user_menu.accounts(accounts, lang)
                final_text = f"✅ {success_text}\n\n{get_string('account_list_title', lang)}"
                
                await bot.edit_message_text(
                    final_text, 
                    message.chat.id, 
                    wait_msg.message_id, 
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                
            elif result == "db_err_uuid_already_active_self":
                await bot.edit_message_text(get_string(result, lang), message.chat.id, wait_msg.message_id)
            else:
                await bot.edit_message_text("❌ این سرویس قبلاً ثبت شده است.", message.chat.id, wait_msg.message_id)
        else:
            await bot.edit_message_text(get_string("uuid_not_found", lang), message.chat.id, wait_msg.message_id)
            
    except Exception as e:
        logger.error(f"UUID Login Error: {e}")
        await bot.edit_message_text("❌ خطای سیستمی رخ داد.", message.chat.id, wait_msg.message_id)

# =============================================================================
# 3. دکمه بازگشت (Back)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "back")
async def back_to_main_menu_handler(call: types.CallbackQuery):
    """بازگشت به منوی اصلی"""
    user_id = call.from_user.id
    
    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    text = get_string('main_menu_title', lang)
    markup = await user_menu.main(is_admin, lang)
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)