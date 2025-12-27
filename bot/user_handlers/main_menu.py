# bot/user_handlers/main_menu.py

import logging
import uuid
import random
from telebot import types
from datetime import datetime
from bot.services import cache_manager
import asyncio

# --- Imports ---
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.parsers import _UUID_RE
from bot.utils.formatters import escape_markdown
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
    """نقطه ورود: نمایش منوی زبان یا منوی اصلی (اگر کاربر سابقه داشته باشد)"""
    user_id = message.from_user.id
    
    # 1. ثبت یا بروزرسانی اطلاعات پایه کاربر
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

    # 3. پاک کردن استیت‌های قبلی (برای جلوگیری از باگ)
    if not hasattr(bot, 'user_states'):
        bot.user_states = {}
    if user_id in bot.user_states:
        del bot.user_states[user_id]

    has_history = await db.has_ever_had_account(user_id)
    
    if has_history:
        lang = await db.get_user_language(user_id)
        is_admin = user_id in ADMIN_IDS
        
        text = get_string('main_menu_title', lang)
        markup = await user_menu.main(is_admin, lang)
        
        await bot.send_message(message.chat.id, text, reply_markup=markup)
        return  # خروج از تابع

    text = "👋 Welcome\\! \n 👋 خوش آمدید\\!\n\nplease select your language:\nلطفاً زبان خود را انتخاب کنید:"
    
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
    await db.set_user_language(user_id, lang_code)

    # --- بررسی دسترسی ادمین ---
    # اگر کاربر ادمین است، مستقیم به منوی اصلی برود تا بتواند پنل را مدیریت کند
    if user_id in ADMIN_IDS:
        text = get_string('main_menu_title', lang_code)
        # فراخوانی منوی اصلی با دسترسی ادمین (True)
        markup = await user_menu.main(True, lang_code)
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        return
    # -------------------------

    welcome_text = get_string('welcome_choose_option', lang_code)
    markup = await user_menu.auth_selection(lang_code)
    
    change_lang_txt = f"🌐 {get_string('change_language', lang_code)}"
    markup.add(types.InlineKeyboardButton(change_lang_txt, callback_data="start_reset"))
    
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
        bot.user_states[user_id] = {'step': 'waiting_for_uuid', 'msg_id': call.message.message_id}
        
        raw_text = get_string('send_uuid_prompt', lang)
        # استفاده از escape_markdown برای جلوگیری از ارور
        text = escape_markdown(raw_text)
        
        markup = types.InlineKeyboardMarkup()
        # بازگشت به back_to_welcome
        markup.add(user_menu.btn(f"🔙 {get_string('back', lang)}", "back_to_welcome"))
        
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        
    # --- گزینه ۲: دریافت سرویس تست ---
    elif action == 'new':
        
        # بررسی سابقه
        has_history = await db.has_ever_had_account(user_id)
        if has_history:
            await bot.answer_callback_query(call.id, "❌ اکانت تست فقط برای کاربران جدید است.", show_alert=True)
            return

        try:
            # 1. دریافت همه کشورها
            all_categories = await db.get_server_categories()
            
            # 2. دریافت لیست کدهای فعال (کشورهایی که پنل دارند)
            try:
                active_codes = await db.get_active_location_codes()
            except AttributeError:
                active_panels = await db.get_active_panels()
                active_codes = set(p['category'] for p in active_panels if p.get('category'))

            # 3. فیلتر کردن: فقط کشورهایی که در لیست فعال‌ها هستند
            filtered_categories = [
                cat for cat in all_categories 
                if cat['code'] in active_codes
            ]
            
            if not filtered_categories:
                await bot.answer_callback_query(call.id, "❌ در حال حاضر هیچ سرور فعالی برای تست موجود نیست.", show_alert=True)
                return

            # آماده‌سازی متن
            raw_text = get_string('select_country_prompt')
            text = escape_markdown(raw_text)
            
            # ارسال لیست فیلتر شده به کیبورد
            markup = await user_menu.country_selection(filtered_categories, lang)
            
            await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            await bot.answer_callback_query(call.id, "Error loading list.")


@bot.callback_query_handler(func=lambda call: call.data == "back_to_welcome")
async def back_to_welcome_handler(call: types.CallbackQuery):
    """بازگشت به منوی انتخاب مسیر (بعد از تایید زبان)"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)

    # --- بررسی دسترسی ادمین در بازگشت ---
    if user_id in ADMIN_IDS:
        text = get_string('main_menu_title', lang)
        markup = await user_menu.main(True, lang)
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        return
    # -----------------------------------

    welcome_text = get_string('welcome_choose_option', lang)
    
    markup = await user_menu.auth_selection(lang)
    
    change_lang_txt = f"🌐 {get_string('change_language', lang)}"
    markup.add(types.InlineKeyboardButton(change_lang_txt, callback_data="start_reset"))
    
    await _safe_edit(user_id, call.message.message_id, welcome_text, reply_markup=markup)

# =============================================================================
# 4. هندلر ساخت اکانت تستی (پس از انتخاب کشور)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('new_acc_country:'))
async def create_test_account_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    country_code = call.data.split(':')[1]
    lang = await db.get_user_language(user_id)
    
    raw_processing = get_string('processing_create', lang)
    processing_text = escape_markdown(raw_processing)
    
    await _safe_edit(user_id, call.message.message_id, processing_text, reply_markup=None)
    
    try:
        # دریافت لیست پنل‌های فعال
        active_panels = await db.get_active_panels()
        
        # فیلتر کردن پنل‌ها بر اساس کشور
        candidate_panels = [p for p in active_panels if p.get('category') == country_code]
        
        # اگر پنلی برای آن کشور نبود، از همه پنل‌ها استفاده کن
        if not candidate_panels:
            candidate_panels = active_panels
        
        if not candidate_panels:
            raise Exception("No active panels found")

        # انتخاب تصادفی پنل
        target_panel_data = random.choice(candidate_panels)
        
        # اتصال به پنل
        panel_inst = await PanelFactory.get_panel(target_panel_data['name'])
        
        # مشخصات سرویس تست
        TEST_GIGS = 0.2  # 200 مگابایت
        TEST_DAYS = 1    # 1 روز
        new_uuid = str(uuid.uuid4())
        username = f"Test_{user_id}_{random.randint(100,999)}"
        
        # ساخت کاربر در پنل
        result = await panel_inst.add_user(
            name=username,
            limit_gb=TEST_GIGS,
            expire_days=TEST_DAYS,
            uuid=new_uuid
        )
        
        if result:
            # ثبت در دیتابیس ربات
            acc_name = f"Test Service {country_code.upper()}"
            await db.add_uuid(user_id, new_uuid, acc_name)
            
            # محدود کردن دسترسی (اگر فعال است)
            if hasattr(db, 'set_uuid_access_categories'):
                await db.set_uuid_access_categories(new_uuid, [country_code])

            asyncio.create_task(cache_manager.fetch_and_update_cache())
            
            # رفع ارور علامت تعجب (!) در پیام موفقیت
            raw_success = get_string('test_account_created', lang)
            raw_title = get_string('account_list_title', lang)
            
            # ترکیب متن‌ها و سپس اسکیپ کردن کل آن
            final_raw_text = f"{raw_success}\n\n{raw_title}"
            final_text = escape_markdown(final_raw_text)
            
            # دریافت لیست اکانت‌ها و ساخت کیبورد
            user_uuids = await db.uuids(user_id)
            markup = await user_menu.accounts(user_uuids, lang)
            
            await _safe_edit(user_id, call.message.message_id, final_text, reply_markup=markup)
            
        else:
            raise Exception("Panel returned False")

    except Exception as e:
        logger.error(f"Error creating test account: {e}")
        # پیام خطا را هم اسکیپ می‌کنیم تا مطمئن شویم ارور نمی‌دهد
        err_raw = "❌ متأسفانه خطایی در ساخت سرویس رخ داد. لطفاً با پشتیبانی تماس بگیرید."
        err_msg = escape_markdown(err_raw)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(user_menu.back_btn("start_reset", lang))
        await _safe_edit(user_id, call.message.message_id, err_msg, reply_markup=markup)


# =============================================================================
# 5. دکمه بازگشت به اول (Reset)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "start_reset")
async def reset_start_flow(call: types.CallbackQuery):
    """بازگشت به منوی انتخاب زبان (با فرمت MarkdownV2)"""
    user_id = call.from_user.id

    # 1. پاک کردن استیت‌های احتمالی
    if hasattr(bot, 'user_states') and user_id in bot.user_states:
        del bot.user_states[user_id]
    
    text = "👋 Welcome\\! \n 👋 خوش آمدید\\!\n\nplease select your language:\nلطفاً زبان خود را انتخاب کنید:"
    
    markup = await user_menu.language_selection_start()
    
    # 3. ویرایش پیام با حفظ حالت MarkdownV2
    await _safe_edit(
        user_id, 
        call.message.message_id, 
        text, 
        reply_markup=markup,
        parse_mode='MarkdownV2' 
    )

# =============================================================================
# 6. هندلر ورود با کانفیگ (UUID Login)
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
# 7. دکمه بازگشت (Back)
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