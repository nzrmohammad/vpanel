# bot/user_handlers/main_menu.py

import logging
from datetime import datetime
from telebot import types
from sqlalchemy import select

# --- Imports ---
from bot.bot_instance import bot
from bot.database import db
from bot.db.base import UserUUID
from bot.keyboards.user import user_keyboard as user_menu
from bot.utils.network import _safe_edit
from bot.utils.parsers import _UUID_RE
from bot.utils.formatters import escape_markdown
from bot.language import get_string
from bot.config import ADMIN_IDS
from bot import combined_handler
from bot.user_handlers.sharing import handle_uuid_conflict
from bot.services.account_service import account_service

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

    # 3. پاک کردن استیت‌های قبلی
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
        return

    raw_text = "👋 Welcome!\n 👋 خوش آمدید!\n\nplease select your language:\nلطفاً زبان خود را انتخاب کنید:"
    text = escape_markdown(raw_text)
    markup = await user_menu.language_selection_start()
    
    try:
        await bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='MarkdownV2')
    except Exception as e:
        logger.error(f"Error in start_command: {e}")

# =============================================================================
# 2. هندلر انتخاب زبان (مخصوص Start)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('start_lang:'))
async def start_language_callback(call: types.CallbackQuery):
    """زبان انتخاب شد -> نمایش منوی انتخاب (ورود / سرویس جدید)"""
    user_id = call.from_user.id
    lang_code = call.data.split(':')[1]
    await db.set_user_language(user_id, lang_code)

    # اگر کاربر ادمین است، مستقیم به منوی اصلی برود
    if user_id in ADMIN_IDS:
        text = get_string('main_menu_title', lang_code)
        markup = await user_menu.main(True, lang_code)
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        return

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
        text = escape_markdown(raw_text)
        
        markup = types.InlineKeyboardMarkup()
        markup.add(user_menu.btn(f"🔙 {get_string('back', lang)}", "back_to_welcome"))
        
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        
    elif action == 'new':
        # --- گزینه ۲: دریافت سرویس تست ---
        has_history = await db.has_ever_had_account(user_id)
        if has_history:
            await bot.answer_callback_query(call.id, "❌ اکانت تست فقط برای کاربران جدید است.", show_alert=True)
            return

        try:
            # دریافت لیست کشورهایی که سرور فعال دارند
            all_categories = await db.get_server_categories()
            
            try:
                active_codes = await db.get_active_location_codes()
            except AttributeError:
                # Fallback اگر متد get_active_location_codes وجود نداشت
                active_panels = await db.get_active_panels()
                active_codes = set(p['category'] for p in active_panels if p.get('category'))

            filtered_categories = [
                cat for cat in all_categories 
                if cat['code'] in active_codes
            ]
            
            if not filtered_categories:
                await bot.answer_callback_query(call.id, "❌ در حال حاضر هیچ سرور فعالی برای تست موجود نیست.", show_alert=True)
                return

            raw_text = get_string('select_country_prompt')
            text = escape_markdown(raw_text)
            
            markup = await user_menu.country_selection(filtered_categories, lang)
            
            await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            await bot.answer_callback_query(call.id, "Error loading list.")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_welcome")
async def back_to_welcome_handler(call: types.CallbackQuery):
    """بازگشت به منوی انتخاب مسیر"""
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)

    if user_id in ADMIN_IDS:
        text = get_string('main_menu_title', lang)
        markup = await user_menu.main(True, lang)
        await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)
        return

    welcome_text = get_string('welcome_choose_option', lang)
    markup = await user_menu.auth_selection(lang)
    
    change_lang_txt = f"🌐 {get_string('change_language', lang)}"
    markup.add(types.InlineKeyboardButton(change_lang_txt, callback_data="start_reset"))
    
    await _safe_edit(user_id, call.message.message_id, welcome_text, reply_markup=markup)

# =============================================================================
# 4. هندلر درخواست نام برای اکانت تستی (پس از انتخاب کشور)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('new_acc_country:'))
async def create_test_account_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    country_code = call.data.split(':')[1]
    lang = await db.get_user_language(user_id)
    
    if not hasattr(bot, 'user_states'):
        bot.user_states = {}
    
    bot.user_states[user_id] = {
        'step': 'waiting_for_test_name',
        'country': country_code,
        'msg_id': call.message.message_id
    }

    text = (
        "📛 **انتخاب نام سرویس**\n\n"
        "لطفاً یک نام دلخواه برای سرویس خود ارسال کنید.\n"
        "⚠️ شرایط نام:\n"
        "▫️ بین ۳ تا ۱۲ کاراکتر باشد.\n"
        "▫️ فقط شامل حروف انگلیسی و اعداد باشد.\n\n"
        "✍️ نام مورد نظر را تایپ کنید:"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(user_menu.btn(f"🔙 {get_string('back', lang)}", "back_to_welcome"))

    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='Markdown')

# =============================================================================
# 5. هندلر دریافت نام سرویس تست و ساخت نهایی (Refactored)
# =============================================================================

@bot.message_handler(func=lambda m: (
    hasattr(bot, 'user_states') and 
    m.from_user.id in bot.user_states and 
    bot.user_states[m.from_user.id].get('step') == 'waiting_for_test_name'
))
async def handle_test_name_input(message: types.Message):
    user_id = message.from_user.id
    state = bot.user_states[user_id]
    msg_id = state.get('msg_id')
    country_code = state.get('country')
    input_name = message.text.strip()
    lang = await db.get_user_language(user_id)

    # 1. تمیزکاری چت
    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass

    # 2. اعتبارسنجی ورودی
    if not (3 <= len(input_name) <= 12) or not input_name.replace('_', '').isalnum():
        error_text = get_string('err_invalid_test_name', lang)
        markup = await user_menu.simple_back_menu("back_to_welcome", lang)
        try:
            await bot.edit_message_text(error_text, message.chat.id, msg_id, reply_markup=markup, parse_mode='Markdown')
        except: pass
        return

    # 3. نمایش پیام پردازش
    processing_text = escape_markdown(get_string('processing_create', lang))
    try:
        await bot.edit_message_text(processing_text, message.chat.id, msg_id, reply_markup=None)
    except: pass
    
    # 4. استفاده از سرویس جدید برای ساخت اکانت (حذف کد اسپاگتی)
    # -------------------------------------------------------------------------
    result = await account_service.create_test_account(user_id, input_name, country_code)
    # -------------------------------------------------------------------------

    if result['success']:
        # پایان کار - پاک کردن استیت
        del bot.user_states[user_id]
        
        success_msg = get_string('test_account_created', lang)
        list_title = get_string('account_list_title', lang)
        final_text = escape_markdown(f"{success_msg}\n\n{list_title}")
        
        user_uuids = await db.uuids(user_id)
        markup = await user_menu.accounts(user_uuids, lang)
        
        await _safe_edit(user_id, msg_id, final_text, reply_markup=markup)
        
    else:
        # مدیریت خطاها
        error_code = result.get('error')
        if error_code == "no_panel_for_country":
            err_raw = "❌ متأسفانه در حال حاضر سروری برای کشور انتخاب شده موجود نیست."
        elif error_code == "panel_api_failed":
             err_raw = "❌ خطا در برقراری ارتباط با پنل. لطفاً دقایقی دیگر تلاش کنید."
        else:
             err_raw = "❌ نام انتخابی تکراری یا نامعتبر است. لطفاً نام دیگری انتخاب کنید."

        markup = types.InlineKeyboardMarkup()
        markup.add(user_menu.back_btn("start_reset", lang))
        
        await _safe_edit(user_id, msg_id, escape_markdown(err_raw), reply_markup=markup)

# =============================================================================
# 6. دکمه بازگشت به اول (Reset)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "start_reset")
async def reset_start_flow(call: types.CallbackQuery):
    user_id = call.from_user.id
    if hasattr(bot, 'user_states') and user_id in bot.user_states:
        del bot.user_states[user_id]
    
    raw_text = "👋 Welcome!\n 👋 خوش آمدید!\n\nplease select your language:\nلطفاً زبان خود را انتخاب کنید:"
    text = escape_markdown(raw_text)
    
    markup = await user_menu.language_selection_start()
    
    success = await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup, parse_mode='MarkdownV2')
    if not success:
        logger.error(f"Failed to edit message in reset_start_flow for user {user_id}")

# =============================================================================
# 7. هندلر ورود با کانفیگ (UUID Login)
# =============================================================================

@bot.message_handler(func=lambda m: (
    (hasattr(bot, 'user_states') and m.from_user.id in bot.user_states and bot.user_states[m.from_user.id].get('step') == 'waiting_for_uuid') 
    or _UUID_RE.match(m.text or "")
))
async def handle_uuid_login(message: types.Message):
    """مدیریت ورودی کانفیگ/UUID."""
    user_id = message.from_user.id
    input_text = message.text.strip() if message.text else ""
    lang = await db.get_user_language(user_id)
    
    state = getattr(bot, 'user_states', {}).get(user_id)
    is_in_add_flow = state and state.get('step') == 'waiting_for_uuid'
    menu_msg_id = state.get('msg_id') if is_in_add_flow else None

    try: await bot.delete_message(message.chat.id, message.message_id)
    except: pass

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

    try:
        uuid_str = input_text
        
        # بررسی تکراری بودن UUID
        async with db.get_session() as session:
             stmt = select(UserUUID).where(UserUUID.uuid == uuid_str)
             res = await session.execute(stmt)
             existing_uuid_obj = res.scalars().first()
             
             if existing_uuid_obj:
                 if existing_uuid_obj.user_id != user_id:
                     try: await bot.delete_message(message.chat.id, target_msg_id)
                     except: pass
                     
                     await handle_uuid_conflict(message, uuid_str)
                     
                     if is_in_add_flow and hasattr(bot, 'user_states'):
                        del bot.user_states[user_id]
                     return
                 else:
                     pass

        info = await combined_handler.get_combined_user_info(uuid_str)
        
        if info:
            name = info.get('name') or message.from_user.first_name or "My Config"
            result = await db.add_uuid(user_id, uuid_str, name)
            
            if result in ["db_msg_uuid_added", "db_msg_uuid_reactivated"]:
                success_text = get_string(result, lang)
                
                if is_in_add_flow and hasattr(bot, 'user_states'):
                    del bot.user_states[user_id]

                accounts = await db.uuids(user_id)
                if accounts:
                    for acc in accounts:
                        try:
                            u_str = str(acc['uuid'])
                            cached_info = await combined_handler.get_combined_user_info(u_str)
                            
                            if cached_info:
                                acc['usage_percentage'] = cached_info.get('usage_percentage', 0)
                                raw_expire = cached_info.get('expire')
                                if isinstance(raw_expire, str) and raw_expire.split('.')[0].isdigit():
                                    raw_expire = int(raw_expire.split('.')[0])

                                if isinstance(raw_expire, (int, float)) and raw_expire > 100_000_000:
                                    try:
                                        expire_dt = datetime.fromtimestamp(raw_expire)
                                        now = datetime.now()
                                        rem_days = (expire_dt - now).days
                                        acc['expire'] = max(0, rem_days)
                                    except:
                                        acc['expire'] = '?'
                                elif isinstance(raw_expire, (int, float)):
                                    acc['expire'] = int(raw_expire)
                                else:
                                    acc['expire'] = None
                            else:
                                acc['usage_percentage'] = 0
                                acc['expire'] = None
                        except Exception as e:
                            logger.error(f"Error calculating stats: {e}")
                            acc['usage_percentage'] = 0
                            acc['expire'] = None
                
                markup = await user_menu.accounts(accounts, lang)
                final_text = f"✅ {success_text}\n\n{get_string('account_list_title', lang)}"
                
                await bot.edit_message_text(
                    final_text, 
                    message.chat.id, 
                    target_msg_id, 
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
                    
            elif result == "db_err_uuid_already_active_self":
                err_txt = get_string(result, lang)
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                await bot.edit_message_text(err_txt, message.chat.id, target_msg_id, reply_markup=markup)
            else:
                markup = types.InlineKeyboardMarkup()
                markup.add(user_menu.back_btn("manage", lang))
                await bot.edit_message_text("❌ خطا در ثبت اطلاعات.", message.chat.id, target_msg_id, reply_markup=markup)
        else:
            not_found_txt = get_string("uuid_not_found", lang)
            markup = types.InlineKeyboardMarkup()
            markup.add(user_menu.back_btn("manage", lang))
            await bot.edit_message_text(not_found_txt, message.chat.id, target_msg_id, reply_markup=markup)

    except Exception as e:
        logger.error(f"UUID Login Error: {e}")
        try:
            await bot.edit_message_text("❌ خطای غیرمنتظره رخ داد.", message.chat.id, target_msg_id)
        except: pass

@bot.callback_query_handler(func=lambda call: call.data == "back")
async def back_to_main_menu_handler(call: types.CallbackQuery):
    """بازگشت به منوی اصلی"""
    user_id = call.from_user.id
    
    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    text = get_string('main_menu_title', lang)
    markup = await user_menu.main(is_admin, lang)
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)