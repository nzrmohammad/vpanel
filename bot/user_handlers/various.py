# bot/user_handlers/various.py

import logging
import random
import time
import copy
import jdatetime
from datetime import datetime
from telebot import types

# --- Imports ---
from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils import escape_markdown, _safe_edit, _UUID_RE
from bot.language import get_string
from bot.formatters import user_formatter
from bot.config import (
    ADMIN_IDS, ADMIN_SUPPORT_CONTACT, TUTORIAL_LINKS, 
    ACHIEVEMENTS, ACHIEVEMENT_SHOP_ITEMS, ENABLE_REFERRAL_SYSTEM, REFERRAL_REWARD_GB
)
from bot import combined_handler
from bot.services.panels import PanelFactory

logger = logging.getLogger(__name__)

# User states (non-admin)
user_conversations = {}

# =============================================================================
# 0. Global Step Handler (جایگزین register_next_step_handler)
# =============================================================================

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice'], func=lambda m: m.from_user.id in user_conversations)
async def conversation_step_handler(message: types.Message):
    """مدیریت مراحل مکالمه برای کاربرانی که در user_conversations هستند."""
    uid = message.from_user.id
    
    # اگر کاربر دستور لغو یا استارت فرستاد، استیت را پاک کن
    if message.text and (message.text == '/start' or message.text == '/cancel'):
        if uid in user_conversations:
            del user_conversations[uid]
        # اجازه بده هندلرهای اصلی اجرا شوند (با return نکردن یا فراخوانی مجدد)
        # اما چون اینجا هندلر است، بهتر است همینجا پردازش استارت را انجام دهیم یا کاربر دوباره بزند
        if message.text == '/start':
            await start_command(message)
        return

    if uid in user_conversations:
        step_data = user_conversations.pop(uid) # حذف استیت (یکبار مصرف)
        handler = step_data.get('handler')
        kwargs = step_data.get('kwargs', {})
        
        if handler:
            try:
                await handler(message, **kwargs)
            except Exception as e:
                logger.error(f"Error in step handler: {e}")
                await bot.send_message(uid, "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")

# =============================================================================
# 1. Start Command & Main Menus
# =============================================================================

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
    # پاک کردن استیت‌های قبلی اگر وجود داشته باشد
    if message.from_user.id in user_conversations:
        del user_conversations[message.from_user.id]

    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    await db.add_or_update_user(user_id, username, first_name, last_name)
    
    args = message.text.split()
    if len(args) > 1 and ENABLE_REFERRAL_SYSTEM:
        referral_code = args[1]
        referrer_info = await db.get_referrer_info(user_id)
        if not referrer_info:
            await db.set_referrer(user_id, referral_code)

    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    user_uuids = await db.uuids(user_id)
    
    if user_uuids or is_admin:
        text = get_string('main_menu_title', lang)
        markup = await user_menu.main(is_admin, lang)
    else:
        text = get_string('start_prompt', lang)
        markup = types.ReplyKeyboardRemove()
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.message_handler(regexp=_UUID_RE.pattern)
async def handle_uuid_login(message: types.Message):
    """Handler for UUID login."""
    user_id = message.from_user.id
    
    # جلوگیری از تداخل با عملیات ادمین
    if user_id in ADMIN_IDS and hasattr(bot, 'context_state') and user_id in bot.context_state:
        return 

    # --- دریافت اطلاعات پیام قبلی (برای ادیت) ---
    state = getattr(bot, 'user_states', {}).get(user_id, {})
    menu_msg_id = state.get('msg_id') if state.get('step') == 'waiting_for_uuid' else None

    uuid_str = message.text.strip()
    lang = await db.get_user_language(user_id)
    
    # ۱. حذف پیام ارسالی کاربر (UUID) برای تمیز ماندن چت
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

    # ۲. نمایش وضعیت "در حال بررسی" روی همان پیام قبلی (ادیت)
    wait_text = "⏳ در حال بررسی ..."
    target_msg_id = None

    if menu_msg_id:
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

    try:
        info = await combined_handler.get_combined_user_info(uuid_str)
        if info:
            name = info.get('name') or message.from_user.first_name or "My Config"
            result = await db.add_uuid(user_id, uuid_str, name)
            
            if result in ["db_msg_uuid_added", "db_msg_uuid_reactivated"]:
                success_text = get_string(result, lang)
                
                # --- تغییر مهم: ساخت لیست اکانت‌ها به جای منوی اصلی ---
                
                # الف) دریافت لیست اکانت‌ها از دیتابیس
                accounts = await db.uuids(user_id)
                
                # ب) محاسبه درصد مصرف (مشابه فایل account.py)
                if accounts:
                    for acc in accounts:
                        try:
                            u_str = str(acc['uuid'])
                            u_info = await combined_handler.get_combined_user_info(u_str)
                            if u_info:
                                acc['usage_percentage'] = u_info.get('usage_percentage', 0)
                                acc['expire'] = u_info.get('expire')
                            else:
                                acc['usage_percentage'] = 0
                        except:
                            acc['usage_percentage'] = 0
                
                # ج) ساخت منوی لیست اکانت‌ها
                markup = await user_menu.accounts(accounts, lang)
                
                # د) ترکیب پیام موفقیت با تیتر لیست اکانت‌ها
                # متن: ✅ اکانت اضافه شد. \n\n لیست اکانت‌ها
                final_text = f"✅ {success_text}\n\n{get_string('account_list_title', lang)}"
                
                # ه) ویرایش پیام نهایی
                await bot.edit_message_text(
                    final_text, 
                    message.chat.id, 
                    target_msg_id, 
                    reply_markup=markup,
                    parse_mode="Markdown" # یا HTML بسته به فرمت متن‌ها
                )
                
                # پاک کردن استیت
                if hasattr(bot, 'user_states') and user_id in bot.user_states:
                    del bot.user_states[user_id]
                    
            elif result == "db_err_uuid_already_active_self":
                await bot.edit_message_text(get_string(result, lang), message.chat.id, target_msg_id)
            else:
                await bot.edit_message_text("❌ This UUID is already registered.", message.chat.id, target_msg_id)
        else:
            await bot.edit_message_text(get_string("uuid_not_found", lang), message.chat.id, target_msg_id)
    except Exception as e:
        logger.error(f"UUID Login Error: {e}")
        await bot.edit_message_text("❌ An error occurred.", message.chat.id, target_msg_id)

@bot.callback_query_handler(func=lambda call: call.data == "back")
async def back_to_main_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    if user_id in user_conversations: del user_conversations[user_id] # لغو هر عملیاتی

    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    text = get_string('main_menu_title', lang)
    markup = await user_menu.main(is_admin, lang)
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)

# =============================================================================
# 2. Daily Check-in & Lucky Spin
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "daily_checkin")
async def daily_checkin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    result = await db.claim_daily_checkin(user_id)
    
    if result['status'] == 'success':
        msg = f"✅ Congrats! You received {result['points']} points.\n🔥 Streak: {result['streak']}"
        await bot.answer_callback_query(call.id, msg, show_alert=True)
    elif result['status'] == 'already_claimed':
        msg = f"⏳ You have already claimed your daily points. Come back tomorrow!"
        await bot.answer_callback_query(call.id, msg, show_alert=True)
    else:
        await bot.answer_callback_query(call.id, "❌ An error occurred.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "lucky_spin_menu")
async def lucky_spin_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await db.user(user_id)
    current_points = user_data.get('achievement_points', 0) if user_data else 0
    SPIN_COST = 50
    
    msg = (
        f"🎰 **Lucky Spin**\n\n"
        f"💰 Your Balance: *{current_points} coins*\n"
        f"💎 Cost per spin: *{SPIN_COST} coins*\n\n"
        f"🎁 **Prizes:**\n"
        f"▫️ Extra Volume\n"
        f"▫️ Free Coins\n"
        f"▫️ Or nothing!\n\n"
        f"Do you want to try your luck?"
    )
    
    kb = types.InlineKeyboardMarkup()
    if current_points >= SPIN_COST:
        kb.add(types.InlineKeyboardButton("🎲 Spin! (-50 coins)", callback_data="do_spin"))
    else:
        kb.add(types.InlineKeyboardButton("❌ Insufficient Balance", callback_data="shop:main"))
    
    kb.add(types.InlineKeyboardButton("🔙 Back to Shop", callback_data="shop:main"))
    
    await _safe_edit(user_id, call.message.message_id, msg, reply_markup=kb, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "do_spin")
async def do_spin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    SPIN_COST = 50
    REWARDS_CONFIG = [
        {"name": "Nothing 😢",           "weight": 40, "type": "none"},
        {"name": "20 Coins Back 🪙", "weight": 30, "type": "points", "value": 20},
        {"name": "500MB Data 🎁", "weight": 20, "type": "volume", "value": 0.5},
        {"name": "1GB Data 🔥",  "weight": 10, "type": "volume", "value": 1.0},
    ]
    
    if not await db.spend_achievement_points(user_id, SPIN_COST):
        await bot.answer_callback_query(call.id, "Insufficient balance!", show_alert=True)
        return

    try:
        await bot.edit_message_text("🎰 Spinning... 🎲", call.message.chat.id, call.message.message_id)
        time.sleep(1.0) 
    except:
        pass

    reward = random.choices(REWARDS_CONFIG, weights=[r['weight'] for r in REWARDS_CONFIG], k=1)[0]
    result_msg = ""
    
    if reward['type'] == "none":
        result_msg = f"😢 Oh! {reward['name']}\nMaybe next time."
        
    elif reward['type'] == "points":
        await db.add_achievement_points(user_id, reward['value'])
        result_msg = f"🎉 Congrats! You won:\n**{reward['name']}**"
        
    elif reward['type'] == "volume":
        user_uuids = await db.uuids(user_id)
        if user_uuids:
            first_uuid = user_uuids[0]['uuid']
            success = await combined_handler.modify_user_on_all_panels(first_uuid, add_gb=reward['value'], add_days=0)
            
            if success:
                result_msg = f"🔥 Awesome! You won:\n**{reward['name']}**\n(Added to your service)"
            else:
                await db.add_achievement_points(user_id, SPIN_COST)
                result_msg = "❌ Error adding volume. Coins refunded."
        else:
            await db.add_achievement_points(user_id, SPIN_COST)
            result_msg = "❌ No active service to receive volume. Coins refunded."

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎲 Spin Again", callback_data="lucky_spin_menu"))
    kb.add(types.InlineKeyboardButton("🔙 Back to Shop", callback_data="shop:main"))
    
    await _safe_edit(user_id, call.message.message_id, result_msg, reply_markup=kb, parse_mode="MarkdownV2")

# =============================================================================
# 3. Referral System
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "referral:info")
async def referral_info_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang_code = await db.get_user_language(user_id)
    bot_username = (await bot.get_me()).username
    
    text = await user_formatter.referral_page(user_id, bot_username, lang_code)
    
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
    )
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

# =============================================================================
# 4. Support System (Fixed)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def handle_support_request(call: types.CallbackQuery):
    uid = call.from_user.id
    msg_id = call.message.message_id
    lang_code = await db.get_user_language(uid)
    
    prompt = (
        f"*{escape_markdown('📝 تیکت پشتیبانی جدید')}*\n\n"
        f"{escape_markdown('لطفاً پیام خود را (متن، عکس، ویدیو و...) در همین چت ارسال کنید.')}\n\n"
        f"{escape_markdown('⚠️ پیام شما مستقیماً برای مدیریت ارسال خواهد شد.')}"
    )
    
    kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
    
    # ✅ FIX: Use manual state dictionary instead of register_next_step_handler
    user_conversations[uid] = {
        'handler': get_support_ticket_message,
        'kwargs': {'original_msg_id': msg_id}
    }

async def get_support_ticket_message(message: types.Message, original_msg_id: int):
    uid = message.from_user.id
    lang_code = await db.get_user_language(uid)

    await _safe_edit(uid, original_msg_id, "⏳ در حال ارسال...", reply_markup=None)

    try:
        user_info = message.from_user
        user_data = await db.user(uid)
        wallet_balance = user_data.get('wallet_balance', 0.0) if user_data else 0.0
        
        # متن پیام برای ادمین
        caption_lines = [
            f"💬 *تیکت جدید*",
            f"👤 {escape_markdown(user_info.first_name)}",
            f"🆔 `{uid}`",
            f"💰 موجودی: {wallet_balance:,.0f}"
        ]
        if user_info.username:
            caption_lines.insert(2, f"🔗 @{escape_markdown(user_info.username)}")
            
        admin_caption = "\n".join(caption_lines)
        
        admin_message_ids = {}
        for admin_id in ADMIN_IDS:
            try:
                # فروارد پیام کاربر به ادمین
                fwd = await bot.forward_message(admin_id, uid, message.message_id)
                # ارسال اطلاعات کاربر به عنوان ریپلای روی پیام فروارد شده
                adm_msg = await bot.send_message(admin_id, admin_caption, parse_mode="MarkdownV2", reply_to_message_id=fwd.message_id)
                admin_message_ids[admin_id] = adm_msg.message_id
            except Exception as e:
                logger.error(f"Support forward error admin {admin_id}: {e}")

        if admin_message_ids:
            first_msg_id = list(admin_message_ids.values())[0]
            # ثبت تیکت در دیتابیس
            ticket_id = await db.create_support_ticket(uid, first_msg_id)
            
            kb_admin = types.InlineKeyboardMarkup()
            kb_admin.add(types.InlineKeyboardButton(
                "✍️ پاسخ به این تیکت", 
                callback_data=f"admin:support_reply:{ticket_id}:{uid}"
            ))
            
            final_caption = f"🎫 *شماره تیکت:* `{ticket_id}`\n" + admin_caption
            
            for admin_id, msg_id in admin_message_ids.items():
                try:
                    await bot.edit_message_text(final_caption, admin_id, msg_id, parse_mode="MarkdownV2", reply_markup=kb_admin)
                except: pass

        success_text = escape_markdown("✅ پیام شما با موفقیت ارسال شد. لطفاً منتظر پاسخ بمانید.")
        kb_back = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
        )
        await _safe_edit(uid, original_msg_id, success_text, reply_markup=kb_back, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Support Error: {e}")
        await _safe_edit(uid, original_msg_id, "❌ خطا در ارسال پیام.", reply_markup=None)

# =============================================================================
# 5. Tutorials
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "tutorials")
async def show_tutorial_main_menu(call: types.CallbackQuery):
    lang = await db.get_user_language(call.from_user.id)
    await _safe_edit(
        call.from_user.id, call.message.message_id,
        get_string("prompt_select_os", lang),
        reply_markup=await user_menu.tutorial_main_menu(lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_os:"))
async def show_tutorial_os_menu(call: types.CallbackQuery):
    os_type = call.data.split(":")[1]
    lang = await db.get_user_language(call.from_user.id)
    await _safe_edit(
        call.from_user.id, call.message.message_id,
        get_string("prompt_select_app", lang),
        reply_markup=await user_menu.tutorial_os_menu(os_type, lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_app:"))
async def send_tutorial_link(call: types.CallbackQuery):
    _, os_type, app_name = call.data.split(":")
    lang = await db.get_user_language(call.from_user.id)
    
    link = TUTORIAL_LINKS.get(os_type, {}).get(app_name)
    if link:
        app_display = f"{os_type.capitalize()} - {app_name.capitalize()}"
        
        header_raw = get_string('tutorial_ready_header', lang).format(app_display_name=app_display)
        body_raw = get_string('tutorial_ready_body', lang) if get_string('tutorial_ready_body', lang) else "Click below:"

        full_text = f"{header_raw}\n\n👇 {body_raw}"
        safe_text = escape_markdown(full_text)
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(get_string("btn_view_tutorial", lang), url=link))
        kb.add(types.InlineKeyboardButton(get_string("btn_back_to_apps", lang), callback_data=f"tutorial_os:{os_type}"))
        
        await _safe_edit(call.from_user.id, call.message.message_id, safe_text, reply_markup=kb)
    else:
        await bot.answer_callback_query(call.id, "Link not found.", show_alert=True)

# =============================================================================
# 6. Birthday Gift (Fixed)
# =============================================================================

def _fmt_birthday_info(user_data, lang_code):
    bday = user_data.get('birthday')
    if not bday:
        return "No birthday registered."
    return f"🎂 Registered Birthday: {bday}"

@bot.callback_query_handler(func=lambda call: call.data == "birthday_gift")
async def handle_birthday_gift_request(call: types.CallbackQuery):
    uid = call.from_user.id
    msg_id = call.message.message_id
    lang_code = await db.get_user_language(uid)
    user_data = await db.user(uid)
    
    if user_data and user_data.get('birthday'):
        text = _fmt_birthday_info(user_data, lang_code=lang_code)
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")
    else:
        raw_text = get_string("prompt_birthday", lang_code)
        prompt = escape_markdown(raw_text).replace("YYYY/MM/DD", "`YYYY/MM/DD`")
        kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
        await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
        
        # ✅ FIX: Use manual state dictionary
        user_conversations[uid] = {
            'handler': get_birthday_step,
            'kwargs': {'original_msg_id': msg_id}
        }

async def get_birthday_step(message: types.Message, original_msg_id: int):
    uid, text = message.from_user.id, message.text.strip()
    lang_code = await db.get_user_language(uid)
    
    try:
        await bot.delete_message(uid, message.message_id)
    except: pass

    try:
        gregorian_date = jdatetime.datetime.strptime(text, '%Y/%m/%d').togregorian().date()
        await db.update_user_birthday(uid, gregorian_date)
        
        success = escape_markdown(get_string("birthday_success", lang_code))
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back"))
        await _safe_edit(uid, original_msg_id, success, reply_markup=kb, parse_mode="MarkdownV2")
    except ValueError:
        error = escape_markdown(get_string("birthday_invalid_format", lang_code))
        await _safe_edit(uid, original_msg_id, error, parse_mode="MarkdownV2")
        
        # در صورت خطا، دوباره منتظر ورودی بمان
        user_conversations[uid] = {
            'handler': get_birthday_step,
            'kwargs': {'original_msg_id': original_msg_id}
        }

# =============================================================================
# 7. Achievements (Badges)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "achievements")
async def show_achievements_page(call: types.CallbackQuery):
    uid, msg_id = call.from_user.id, call.message.message_id
    user_achievements = await db.get_user_achievements(uid)
    
    total_points = sum(ACHIEVEMENTS.get(ach, {}).get('points', 0) for ach in user_achievements)
    
    # محاسبه سطح کاربر
    level = "تازه‌کار"
    if total_points >= 1000: level = "افسانه"
    elif total_points >= 500: level = "اسطوره"
    elif total_points >= 250: level = "حرفه‌ای"
    elif total_points >= 100: level = "باتجربه"

    # دسته‌بندی فارسی
    categories = {
        "🏅 ورزشی": ["bodybuilder", "water_athlete", "aerialist", "swimming_champion"],
        "🗣 اجتماعی": ["media_partner", "ambassador", "support_contributor"],
        "💎 وفاداری": ["veteran", "loyal_supporter"],
        "📊 عملکرد": ["pro_consumer", "weekly_champion", "night_owl", "early_bird"],
        "🌟 ویژه": ["legend", "vip_friend", "lucky_one"]
    }
    
    text = f"🏅 *دستاوردها و نشان‌ها*\n🏆 سطح: *{level}*\n⭐ امتیاز کل: *{total_points}*\n───────────────\n\n"
    
    has_any = False
    for cat_name, codes in categories.items():
        user_has_in_cat = [c for c in codes if c in user_achievements]
        if user_has_in_cat:
            has_any = True
            text += f"*{escape_markdown(cat_name)}*:\n"
            for c in user_has_in_cat:
                info = ACHIEVEMENTS.get(c, {})
                text += f"{info.get('icon','')} {escape_markdown(info.get('name',''))}\n"
            text += "\n"
            
    if not has_any:
        text += escape_markdown("شما هنوز نشانی دریافت نکرده‌اید. به فعالیت خود ادامه دهید تا نشان‌ها را کشف کنید!")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🏅 درخواست نشان ورزشی", callback_data="achievements:req_menu"),
        types.InlineKeyboardButton("ℹ️ راهنما", callback_data="achievements:info")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "achievements:info")
async def show_achievements_info(call: types.CallbackQuery):
    uid = call.from_user.id
    text = "ℹ️ *راهنمای نشان‌ها*\n\n"
    
    for code, info in ACHIEVEMENTS.items():
        text += f"{info['icon']} *{escape_markdown(info['name'])}* ({info['points']} امتیاز):\n"
        text += f"{escape_markdown(info['description'])}\n\n"
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="achievements"))
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "achievements:req_menu")
async def request_badge_menu_handler(call: types.CallbackQuery):
    markup = await user_menu.request_badge_menu()
    await _safe_edit(call.from_user.id, call.message.message_id, "Select your sport:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("achievements:req:"))
async def handle_badge_request(call: types.CallbackQuery):
    badge_code = call.data.split(":")[2]
    uid = call.from_user.id
    
    user_achievements = await db.get_user_achievements(uid)
    if badge_code in user_achievements:
        await bot.answer_callback_query(call.id, "You already have this badge!", show_alert=True)
        return

    req_id = await db.add_achievement_request(uid, badge_code)
    
    user = call.from_user
    badge_name = ACHIEVEMENTS.get(badge_code, {}).get('name', badge_code)
    admin_msg = f"🏅 *Badge Request*\n👤 {escape_markdown(user.first_name)}\nBadge: {escape_markdown(badge_name)}"
    
    admin_kb = types.InlineKeyboardMarkup()
    admin_kb.add(
        types.InlineKeyboardButton("✅ Approve", callback_data=f"admin:ach_approve:{req_id}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"admin:ach_reject:{req_id}")
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_msg, parse_mode="MarkdownV2", reply_markup=admin_kb)
        except: pass

    await _safe_edit(uid, call.message.message_id, "✅ Request sent.", reply_markup=None)
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="achievements"))
    await bot.send_message(uid, "You will be notified of the result.", reply_markup=kb)

# =============================================================================
# 8. Achievement Shop
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "shop:main")
async def shop_main_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    user_data = await db.user(uid)
    points = user_data.get('achievement_points', 0) if user_data else 0
    access = await db.get_user_access_rights(uid)
    
    text = f"🛍️ *Shop*\nBalance: *{points} points*\n\nAvailable items:"
    markup = await user_menu.achievement_shop_menu(points, access, list(ACHIEVEMENT_SHOP_ITEMS.values()))
    
    await _safe_edit(uid, call.message.message_id, text, reply_markup=markup, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop:confirm:"))
async def shop_confirm_handler(call: types.CallbackQuery):
    item_id = call.data.split(":")[2]
    item = ACHIEVEMENT_SHOP_ITEMS.get(item_id)
    if not item: return

    uid = call.from_user.id
    lang = await db.get_user_language(uid)
    
    user_uuids = await db.uuids(uid)
    if not user_uuids:
        await bot.answer_callback_query(call.id, "No active service.", show_alert=True)
        return
    
    main_uuid = user_uuids[0]['uuid']
    info_before = await combined_handler.get_combined_user_info(main_uuid)
    
    info_after = copy.deepcopy(info_before)
    
    add_gb = item.get('gb', 0)
    add_days = item.get('days', 0)
    
    info_after['usage_limit_GB'] += add_gb
    if info_after.get('expire') and add_days:
        info_after['expire'] += add_days

    summary = await user_formatter.purchase_summary(info_before, info_after, {"name": item['name']}, lang)
    
    text = (
        f"❓ *Confirm Purchase*\n\n"
        f"Item: {escape_markdown(item['name'])}\n"
        f"Cost: {item['cost']} points\n\n"
        f"{summary}\n\n"
        "Are you sure?"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Yes", callback_data=f"shop:exec:{item_id}"),
        types.InlineKeyboardButton("❌ No", callback_data="shop:main")
    )
    
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data.startswith("shop:exec:"))
async def shop_execute_handler(call: types.CallbackQuery):
    item_key = call.data.split(":")[2]
    item = ACHIEVEMENT_SHOP_ITEMS.get(item_key)
    uid = call.from_user.id
    
    if await db.spend_achievement_points(uid, item['cost']):
        user_uuids = await db.uuids(uid)
        if user_uuids:
            uuid = user_uuids[0]['uuid']
            
            target_type = None
            t = item.get('target')
            if t == 'de': target_type = 'hiddify'
            elif t in ['fr', 'tr', 'us']: target_type = 'marzban'
            
            success = await combined_handler.modify_user_on_all_panels(
                identifier=uuid,
                add_gb=item.get('gb', 0),
                add_days=item.get('days', 0),
                target_panel_type=target_type
            )
            
            if success:
                await db.log_shop_purchase(uid, item_key, item['cost'])
                await bot.answer_callback_query(call.id, "✅ Purchase successful.", show_alert=True)
                await shop_main_handler(call)
                try:
                    for aid in ADMIN_IDS:
                        await bot.send_message(aid, f"🛍 User {uid} bought {item['name']}.")
                except: pass
                return

        await db.add_achievement_points(uid, item['cost'])
        await bot.answer_callback_query(call.id, "❌ Error applying reward.", show_alert=True)
    else:
        await bot.answer_callback_query(call.id, "❌ Insufficient balance.", show_alert=True)

# =============================================================================
# 9. Connection Doctor
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "connection_doctor")
async def connection_doctor_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    
    # 0. نمایش پیام انتظار
    await _safe_edit(uid, call.message.message_id, "🩺 ...", reply_markup=None)
    
    # 1. بررسی وضعیت اکانت کاربر
    user_uuids = await db.uuids(uid)
    is_user_active = False
    if user_uuids:
        active_uuid = next((u for u in user_uuids if u['is_active']), None)
        if active_uuid:
            info = await combined_handler.get_combined_user_info(str(active_uuid['uuid']))
            if info and info.get('is_active'):
                is_user_active = True

    # 2. بررسی وضعیت سرورها
    active_panels = await db.get_active_panels()
    server_categories = await db.get_server_categories()
    cat_map = {c['code']: c for c in server_categories}
    
    panel_status_lines = []
    category_stats = {} 

    for p in active_panels:
        p_name = p['name']
        p_cat = p.get('category')
        
        try:
            handler = await PanelFactory.get_panel(p_name)
            stats = await handler.get_system_stats()
            
            if stats:
                status_text = "آنلاین و پایدار"
                icon = "✅"
                cpu = stats.get('cpu_usage') or stats.get('cpu') or 0
                if p_cat:
                    if p_cat not in category_stats: category_stats[p_cat] = []
                    category_stats[p_cat].append(float(cpu))
            else:
                status_text = "آفلاین یا دارای اختلال"
                icon = "❌"
        except Exception:
            status_text = "عدم برقراری ارتباط"
            icon = "❌"

        safe_p_name = escape_markdown(p_name)
        safe_status = escape_markdown(status_text)
        label = escape_markdown(f"وضعیت سرور «{p_name}»")
        panel_status_lines.append(f"{icon} {label}: {safe_status}")

    # 3. تحلیل هوشمند بار سرور
    load_analysis_lines = []
    
    if category_stats:
        for cat_code, loads in category_stats.items():
            if not loads: continue
            avg_load = sum(loads) / len(loads)
            
            if avg_load < 30:
                status_label = "خلوت"
                status_icon = "🟢"
            elif avg_load < 75:
                status_label = "عادی"
                status_icon = "🟡"
            else:
                status_label = "شلوغ"
                status_icon = "🔴"
            
            cat_info = cat_map.get(cat_code)
            if cat_info:
                cat_name = escape_markdown(cat_info.get('name', cat_code))
                cat_emoji = cat_info.get('emoji', '')
            else:
                cat_name = escape_markdown(cat_code.upper())
                cat_emoji = ""
            
            safe_label = escape_markdown(status_label)
            server_word = escape_markdown("سرور")
            load_analysis_lines.append(f" {status_icon} {server_word} {cat_name} {cat_emoji}: {safe_label}")
    else:
        load_analysis_lines.append(escape_markdown("اطلاعاتی در دسترس نیست."))

    # 4. ساخت پیام نهایی با هدر و فوتر
    acc_status = escape_markdown("فعال" if is_user_active else "غیرفعال")
    acc_icon = "✅" if is_user_active else "❌"
    
    separator = escape_markdown("──────────────────")

    msg_lines = [
        escape_markdown("گزارش پزشک اتصال:"),
        separator,
        f"{acc_icon} {escape_markdown('وضعیت اکانت شما:')} {acc_status}",
    ]
    
    msg_lines.extend(panel_status_lines)
    
    msg_lines.append(separator)
    msg_lines.append(escape_markdown("📈 تحلیل هوشمند بار سرور (۱۵ دقیقه اخیر):"))
    msg_lines.extend(load_analysis_lines)
    
    msg_lines.append(separator)
    msg_lines.append(escape_markdown("💡 پیشنهاد:"))
    
    suggestion_text = (
        "اگر اکانت و سرورها فعال هستند اما همچنان با کندی مواجه‌اید، "
        "لطفاً یک بار اتصال خود را قطع و وصل کرده و به سرور دیگری متصل شوید. "
        "در صورت ادامه مشکل، با پشتیبانی تماس بگیرید."
    )
    msg_lines.append(escape_markdown(suggestion_text))
    
    final_text = "\n".join(msg_lines)
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    
    await _safe_edit(uid, call.message.message_id, final_text, reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "coming_soon")
async def coming_soon(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 Coming soon...", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "show_features_guide")
async def show_features_guide_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    lang = await db.get_user_language(uid)
    text = get_string("features_guide_body", lang)
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="back"))
    await _safe_edit(uid, call.message.message_id, escape_markdown(text), reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "request_service")
async def request_service_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    user = call.from_user
    msg = f"👤 Service Request from:\n{user.first_name} (@{user.username})\nID: {uid}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg)
        except: pass
        
    await bot.answer_callback_query(call.id, "✅ Request sent to admin.", show_alert=True)