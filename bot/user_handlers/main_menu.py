# bot/user_handlers/main_menu.py

import logging
import uuid
import random
from telebot import types
from datetime import datetime  # ایمپورت ماژول زمان

# --- Imports ---
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.parsers import _UUID_RE
from bot.language import get_string
from bot.config import ADMIN_IDS
from bot import combined_handler
from bot.services.panels.factory import PanelFactory

logger = logging.getLogger(__name__)

# =============================================================================
# 1. نقطه شروع (Start)
# =============================================================================

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
    """نقطه ورود: نمایش منوی زبان با متن سفارشی"""
    user_id = message.from_user.id
    
    # 1. ثبت یا بروزرسانی کاربر
    await db.add_or_update_user(
        user_id, 
        message.from_user.username, 
        message.from_user.first_name, 
        message.from_user.last_name
    )

    # 2. بررسی سیستم معرف (Referral)
    args = message.text.split()
    referral_status = await db.get_config('enable_referral_system', 'True')
    if len(args) > 1 and referral_status.lower() == 'true':
        await db.set_referrer(user_id, args[1])

    # 3. پاک کردن استیت‌های قبلی (برای جلوگیری از تداخل)
    if not hasattr(bot, 'user_states'):
        bot.user_states = {}
    if user_id in bot.user_states:
        del bot.user_states[user_id]

    # 4. نمایش پیام خوش‌آمدگویی دقیقاً طبق درخواست شما
    text = "👋 Welcome! \n 👋 خوش آمدید!\n\nplease select your language:\nلطفاً زبان خود را انتخاب کنید:"
    
    # استفاده از کیبورد مخصوص استارت (start_lang)
    markup = await user_menu.language_selection_start()
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)


# =============================================================================
# 2. هندلر انتخاب زبان (مخصوص Start)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('start_lang:'))
async def start_language_callback(call: types.CallbackQuery):
    """زبان انتخاب شد -> نمایش منوی انتخاب (ورود / سرویس جدید)"""
    user_id = call.from_user.id
    lang_code = call.data.split(':')[1]
    
    # ذخیره زبان در دیتابیس
    await db.set_user_language(user_id, lang_code)
    
    # پیام تأیید و درخواست انتخاب مسیر
    welcome_text = get_string('welcome_choose_option', lang_code)
    
    # نمایش دکمه‌های "ورود با UUID" و "اکانت جدید"
    markup = await user_menu.auth_selection(lang_code)
    
    await _safe_edit(user_id, call.message.message_id, welcome_text, reply_markup=markup)


# =============================================================================
# 3. هندلر انتخاب مسیر (ورود یا اکانت جدید)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('auth:'))
async def auth_choice_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    action = call.data.split(':')[1]
    lang = await db.get_user_language(user_id)
    
    if action == 'login':
        # --- گزینه ۱: ورود با UUID ---
        if not hasattr(bot, 'user_states'): bot.user_states = {}
        # تنظیم استیت برای دریافت پیام متنی
        bot.user_states[user_id] = {'step': 'waiting_for_uuid', 'msg_id': call.message.message_id}
        
        text = get_string('send_uuid_prompt', lang)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(user_menu.btn(f"🔙 {get_string('back', lang)}", "start_reset"))
        
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        
    elif action == 'new':
        # --- گزینه ۲: ساخت سرویس جدید (انتخاب کشور) ---
        try:
            # دریافت لیست کشورها (کتگوری‌ها)
            categories = await db.get_server_categories()
            
            if not categories:
                await bot.answer_callback_query(call.id, "❌ هیچ کشوری فعال نیست.", show_alert=True)
                return

            text = get_string('select_country_prompt')
            
            markup = await user_menu.country_selection(categories, lang)
            await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            await bot.answer_callback_query(call.id, "Error loading list.")


# =============================================================================
# 4. هندلر ساخت اکانت تستی (پس از انتخاب کشور)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('new_acc_country:'))
async def create_test_account_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    country_code = call.data.split(':')[1]
    lang = await db.get_user_language(user_id)
    
    # نمایش پیام "در حال ساخت..."
    processing_text = get_string('processing_create', lang)
    await _safe_edit(user_id, call.message.message_id, processing_text, reply_markup=None)
    
    try:
        # 1. دریافت لیست پنل‌های فعال
        active_panels = await db.get_active_panels()
        
        # 2. فیلتر کردن پنل‌ها بر اساس کشور انتخاب شده
        # پنل‌هایی که category آنها با کد کشور یکی باشد
        candidate_panels = [p for p in active_panels if p.get('category') == country_code]
        
        if not candidate_panels:
            # اگر پنلی با آن کتگوری پیدا نشد، از همه پنل‌های فعال استفاده کن (Fallback)
            candidate_panels = active_panels
        
        if not candidate_panels:
            raise Exception("No active panels found")

        # انتخاب تصادفی یک پنل (Load Balancing)
        target_panel_data = random.choice(candidate_panels)
        
        # 3. اتصال به پنل
        panel_inst = await PanelFactory.get_panel(target_panel_data['name'])
        
        # مشخصات سرویس تست (می‌توانید به کانفیگ منتقل کنید)
        TEST_GIGS = 0.2  # 200 مگابایت
        TEST_DAYS = 1    # 1 روز
        new_uuid = str(uuid.uuid4())
        username = f"Test_{user_id}_{random.randint(100,999)}"
        
        # 4. درخواست ساخت کاربر در پنل
        result = await panel_inst.add_user(
            name=username,
            limit_gb=TEST_GIGS,
            expire_days=TEST_DAYS,
            uuid=new_uuid
        )
        
        if result:
            # 5. ثبت موفق در دیتابیس بات
            # نام نمایشی شامل پرچم کشور باشد
            acc_name = f"Test Service {country_code.upper()}"
            await db.add_uuid(user_id, new_uuid, acc_name)
            
            # محدود کردن دسترسی فقط به همین کشور (اگر سیستم دسترسی دارید)
            if hasattr(db, 'set_uuid_access_categories'):
                await db.set_uuid_access_categories(new_uuid, [country_code])
            
            # 6. نمایش نتیجه نهایی (لیست اکانت‌ها)
            success_text = get_string('test_account_created', lang)
            
            # دریافت لیست اکانت‌های کاربر
            user_uuids = await db.uuids(user_id)
            markup = await user_menu.accounts(user_uuids, lang)
            
            final_text = f"{success_text}\n\n{get_string('account_list_title', lang)}"
            await _safe_edit(user_id, call.message.message_id, final_text, reply_markup=markup)
            
        else:
            raise Exception("Panel returned False")

    except Exception as e:
        logger.error(f"Error creating test account: {e}")
        err_msg = "❌ متأسفانه خطایی در ساخت سرویس رخ داد. لطفاً با پشتیبانی تماس بگیرید."
        markup = types.InlineKeyboardMarkup()
        markup.add(user_menu.back_btn("start_reset", lang))
        await _safe_edit(user_id, call.message.message_id, err_msg, reply_markup=markup)


# =============================================================================
# 5. هندلر دریافت UUID متنی (وقتی کاربر گزینه ورود را انتخاب کرده)
# =============================================================================

@bot.message_handler(func=lambda m: (
    (hasattr(bot, 'user_states') and m.from_user.id in bot.user_states and bot.user_states[m.from_user.id].get('step') == 'waiting_for_uuid') 
    or _UUID_RE.match(m.text or "")
))
async def handle_uuid_login(message: types.Message):
    """مدیریت دریافت UUID از کاربر"""
    user_id = message.from_user.id
    input_text = message.text.strip() if message.text else ""
    lang = await db.get_user_language(user_id)
    
    state = getattr(bot, 'user_states', {}).get(user_id)
    menu_msg_id = state.get('msg_id') if state else None

    # حذف پیام ارسالی کاربر برای تمیزی چت
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except: pass

    # اعتبارسنجی
    if not _UUID_RE.match(input_text):
        if menu_msg_id:
            try:
                err_text = get_string('uuid_invalid', lang)
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("start_reset", lang))
                await bot.edit_message_text(err_text, message.chat.id, menu_msg_id, reply_markup=markup)
            except: pass
        return

    # پیام "در حال بررسی"
    wait_text = "⏳ ..."
    target_msg_id = menu_msg_id
    if not target_msg_id:
        msg = await bot.send_message(message.chat.id, wait_text)
        target_msg_id = msg.message_id
    else:
        try:
            await bot.edit_message_text(wait_text, message.chat.id, target_msg_id)
        except: pass

    # استعلام از پنل‌ها
    try:
        uuid_str = input_text
        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if info:
            # موفقیت: ثبت در دیتابیس
            name = info.get('name') or message.from_user.first_name or "My Config"
            result = await db.add_uuid(user_id, uuid_str, name)
            
            # پاک کردن استیت
            if user_id in getattr(bot, 'user_states', {}):
                del bot.user_states[user_id]
            
            # نمایش لیست اکانت‌ها
            success_text = get_string('db_msg_uuid_added', lang)
            user_uuids = await db.uuids(user_id)
            markup = await user_menu.accounts(user_uuids, lang)
            
            final_text = f"{success_text}\n\n{get_string('account_list_title', lang)}"
            await bot.edit_message_text(final_text, message.chat.id, target_msg_id, reply_markup=markup)
            
        else:
            # یافت نشد
            not_found = get_string('uuid_not_found', lang)
            markup = types.InlineKeyboardMarkup()
            markup.add(user_menu.back_btn("start_reset", lang))
            await bot.edit_message_text(not_found, message.chat.id, target_msg_id, reply_markup=markup)

    except Exception as e:
        logger.error(f"Login Error: {e}")
        await bot.edit_message_text("❌ Error.", message.chat.id, target_msg_id)


# =============================================================================
# 6. دکمه بازگشت به اول (Reset)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "start_reset")
async def reset_start_flow(call: types.CallbackQuery):
    await start_command(call.message)

# =============================================================================
# 2. هندلر ورود با کانفیگ (UUID Login)
# =============================================================================

@bot.message_handler(func=lambda m: (
    (hasattr(bot, 'user_states') and m.from_user.id in bot.user_states and bot.user_states[m.from_user.id].get('step') == 'waiting_for_uuid') 
    or _UUID_RE.match(m.text or "")
))
async def handle_uuid_login(message: types.Message):
    """
    مدیریت ورودی کانفیگ/UUID.
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
    if not _UUID_RE.match(input_text):
        if is_in_add_flow and menu_msg_id:
            try:
                error_text = "❌ فرمت UUID اشتباه است.\nلطفاً UUID صحیح را ارسال کنید:"
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                
                await bot.edit_message_text(error_text, message.chat.id, menu_msg_id, reply_markup=markup)
            except Exception as e:
                logger.error(f"Error editing menu for invalid input: {e}")
        return

    # 4. آماده‌سازی پیام "در حال بررسی"
    wait_text = "⏳ در حال بررسی ..."
    target_msg_id = None

    if is_in_add_flow and menu_msg_id:
        try:
            await bot.edit_message_text(wait_text, message.chat.id, menu_msg_id)
            target_msg_id = menu_msg_id
        except:
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
                if accounts:
                    for acc in accounts:
                        try:
                            # تلاش برای دریافت اطلاعات از کش
                            u_str = str(acc['uuid'])
                            cached_info = await combined_handler.get_combined_user_info(u_str)
                            
                            if cached_info:
                                # 1. تنظیم درصد مصرف
                                acc['usage_percentage'] = cached_info.get('usage_percentage', 0)
                                
                                # --- اصلاحیه هوشمند تاریخ انقضا ---
                                raw_expire = cached_info.get('expire')
                                
                                # تبدیل رشته به عدد (اگر پنل تاریخ را به صورت رشته فرستاده باشد)
                                if isinstance(raw_expire, str):
                                    # حذف اعشار احتمالی و بررسی عددی بودن
                                    clean_raw = raw_expire.split('.')[0]
                                    if clean_raw.isdigit():
                                        raw_expire = int(clean_raw)

                                # لاگ برای دیباگ دقیق
                                logger.info(f"User: {acc.get('name')} | Final Raw Expire: {raw_expire} | Type: {type(raw_expire)}")

                                # حالت ۱: تایم‌استمپ (عدد بزرگ)
                                if isinstance(raw_expire, (int, float)) and raw_expire > 100_000_000:
                                    try:
                                        expire_dt = datetime.fromtimestamp(raw_expire)
                                        now = datetime.now()
                                        rem_days = (expire_dt - now).days
                                        acc['expire'] = max(0, rem_days) # جلوگیری از عدد منفی
                                    except:
                                        acc['expire'] = '?'

                                # حالت ۲: تعداد روز (عدد کوچک)
                                elif isinstance(raw_expire, (int, float)):
                                    acc['expire'] = int(raw_expire)
                                
                                # حالت ۳: نامحدود یا نامشخص
                                else:
                                    acc['expire'] = None
                                # ----------------------------------
                            else:
                                acc['usage_percentage'] = 0
                                acc['expire'] = None
                                
                        except Exception as e:
                            logger.error(f"Error calculating stats for menu: {e}")
                            acc['usage_percentage'] = 0
                            acc['expire'] = None
                
                # ساخت منوی لیست اکانت‌ها
                markup = await user_menu.accounts(accounts, lang)
                final_text = f"✅ {success_text}\n\n{get_string('account_list_title', lang)}"
                
                # ویرایش پیام نهایی
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