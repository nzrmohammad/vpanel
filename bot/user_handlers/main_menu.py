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

# bot/user_handlers/main_menu.py

# ... (ایمپورت‌های قبلی سرجای خود باشند) ...

# تابع handle_uuid_login قبلی را پاک کنید و این را جایگزین کنید:

@bot.message_handler(func=lambda m: (
    (hasattr(bot, 'user_states') and m.from_user.id in bot.user_states and bot.user_states[m.from_user.id].get('step') == 'waiting_for_uuid') 
    or _UUID_RE.match(m.text or "")
))
async def handle_uuid_login(message: types.Message):
    """
    مدیریت ورودی کانفیگ/UUID.
    این تابع هم ورودی‌های صحیح UUID را می‌گیرد و هم اگر کاربر در مرحله افزودن اکانت باشد،
    هر متنی (حتی غلط مثل 11) را می‌گیرد تا بتواند خطا دهد.
    """
    user_id = message.from_user.id
    input_text = message.text.strip() if message.text else ""
    lang = await db.get_user_language(user_id)
    
    # 1. تشخیص اینکه آیا کاربر از طریق دکمه "افزودن اکانت" آمده یا مستقیم پیام داده
    state = getattr(bot, 'user_states', {}).get(user_id)
    is_in_add_flow = state and state.get('step') == 'waiting_for_uuid'
    menu_msg_id = state.get('msg_id') if is_in_add_flow else None

    # 2. حذف پیام کاربر (برای تمیز ماندن چت)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

    # 3. اعتبارسنجی فرمت UUID
    # اگر فرمت غلط باشد (مثل عدد 11) و کاربر در پروسه افزودن باشد، باید خطا بدهیم
    if not _UUID_RE.match(input_text):
        if is_in_add_flow and menu_msg_id:
            try:
                # نمایش خطا روی همان منوی قبلی
                error_text = "❌ فرمت UUID اشتباه است.\nلطفاً کد کانفیگ صحیح را ارسال کنید:"
                # دکمه بازگشت هم نگه می‌داریم
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                
                await bot.edit_message_text(error_text, message.chat.id, menu_msg_id, reply_markup=markup)
            except Exception as e:
                logger.error(f"Error editing menu for invalid input: {e}")
        # اگر کاربر همینجوری "11" فرستاده و در پروسه نیست، واکنشی نشان نمی‌دهیم (یا می‌توان گفت دستور نامعتبر)
        return

    # 4. آماده‌سازی پیام "در حال بررسی"
    # اگر در پروسه بودیم، پیام قبلی را ادیت می‌کنیم. اگر نه، پیام جدید می‌فرستیم.
    wait_text = "⏳ در حال بررسی ..."
    target_msg_id = None

    if is_in_add_flow and menu_msg_id:
        try:
            await bot.edit_message_text(wait_text, message.chat.id, menu_msg_id)
            target_msg_id = menu_msg_id
        except:
            # اگر پیام قبلی پاک شده بود، پیام جدید می‌فرستیم
            msg = await bot.send_message(message.chat.id, wait_text)
            target_msg_id = msg.message_id
    else:
        msg = await bot.send_message(message.chat.id, wait_text)
        target_msg_id = msg.message_id

    # 5. استعلام از پنل‌ها
    try:
        uuid_str = input_text
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if info:
            # یافت شد -> ثبت در دیتابیس
            name = info.get('name') or message.from_user.first_name or "My Config"
            result = await db.add_uuid(user_id, uuid_str, name)
            
            if result in ["db_msg_uuid_added", "db_msg_uuid_reactivated"]:
                success_text = get_string(result, lang)
                
                # پاک کردن استیت چون کار تمام شد
                if is_in_add_flow and hasattr(bot, 'user_states'):
                    del bot.user_states[user_id]

                # دریافت لیست اکانت‌ها برای نمایش نهایی
                accounts = await db.uuids(user_id)
                
                # محاسبه درصد مصرف (برای زیبایی لیست)
                if accounts:
                    for acc in accounts:
                        try:
                            u_str = str(acc['uuid'])
                            # نکته: اگر بخواهید سریعتر باشد، می‌توانید از همان info استفاده کنید
                            # اما چون لیست کلی است، شاید نیاز به رفرش باشد
                            if u_str == uuid_str:
                                acc['usage_percentage'] = info.get('usage_percentage', 0)
                                acc['expire'] = info.get('expire')
                            else:
                                # برای بقیه اکانت‌ها فعلاً صفر یا کش (بهینه سازی سرعت)
                                acc['usage_percentage'] = 0 
                        except: pass
                
                # ساخت منوی لیست اکانت‌ها
                markup = await user_menu.accounts(accounts, lang)
                final_text = f"✅ {success_text}\n\n{get_string('account_list_title', lang)}"
                
                # ویرایش پیام نهایی (جایگزین کردن "در حال بررسی" با "لیست اکانت‌ها")
                await bot.edit_message_text(
                    final_text, 
                    message.chat.id, 
                    target_msg_id, 
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                    
            elif result == "db_err_uuid_already_active_self":
                # اکانت تکراری است
                err_txt = get_string(result, lang)
                # دکمه بازگشت برای تلاش مجدد
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                await bot.edit_message_text(err_txt, message.chat.id, target_msg_id, reply_markup=markup)
            else:
                # خطای دیتابیس
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                await bot.edit_message_text("❌ خطا در ثبت اطلاعات.", message.chat.id, target_msg_id, reply_markup=markup)
        else:
            # یافت نشد (در هیچ پنلی)
            not_found_txt = get_string("uuid_not_found", lang)
            markup = types.InlineKeyboardMarkup()
            markup.add(user_menu.back_btn("manage", lang))
            await bot.edit_message_text(not_found_txt, message.chat.id, target_msg_id, reply_markup=markup)

    except Exception as e:
        logger.error(f"UUID Login Error: {e}")
        try:
            await bot.edit_message_text("❌ خطای غیرمنتظره رخ داد.", message.chat.id, target_msg_id)
        except: pass

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