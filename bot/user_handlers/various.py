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
from bot.utils import escape_markdown, _safe_edit, to_shamsi
from bot.language import get_string

# ✅ تغییر مهم: ایمپورت user_formatter به جای توابع قدیمی
from bot.formatters import user_formatter 

from bot.config import (
    ADMIN_IDS, ADMIN_SUPPORT_CONTACT, TUTORIAL_LINKS, 
    ACHIEVEMENTS, ACHIEVEMENT_SHOP_ITEMS, ENABLE_REFERRAL_SYSTEM, REFERRAL_REWARD_GB
)
from bot import combined_handler
from bot.services.panels.hiddify import HiddifyPanel
from bot.services.panels.marzban import MarzbanPanel

# تنظیم لاگر
logger = logging.getLogger(__name__)

# --- تنظیمات گردونه شانس ---
SPIN_COST = 50  # هزینه هر بار چرخش
REWARDS_CONFIG = [
    {"name": "پوچ 😢",           "weight": 40, "type": "none"},
    {"name": "۲۰ سکه بازگشت 🪙", "weight": 30, "type": "points", "value": 20},
    {"name": "۵۰۰ مگابایت حجم 🎁", "weight": 20, "type": "volume", "value": 0.5},
    {"name": "۱ گیگابایت حجم 🔥",  "weight": 10, "type": "volume", "value": 1.0},
]

user_conversations = {}

# =============================================================================
# 1. Start Command & Main Menus
# =============================================================================

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
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
    
    text = get_string('start_prompt', lang)
    markup = await user_menu.main(is_admin, lang)
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "back")
async def back_to_main_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    is_admin = user_id in ADMIN_IDS
    
    text = get_string('main_menu_title', lang)
    markup = await user_menu.main(is_admin, lang)
    
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_start_menu")
async def back_to_start_menu(call: types.CallbackQuery):
    await back_to_main_menu_handler(call)

# =============================================================================
# 2. Daily Check-in & Lucky Spin
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "daily_checkin")
async def daily_checkin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    result = await db.claim_daily_checkin(user_id)
    
    if result['status'] == 'success':
        msg = f"✅ تبریک! شما {result['points']} امتیاز دریافت کردید.\n🔥 تعداد روزهای متوالی: {result['streak']}"
        await bot.answer_callback_query(call.id, msg, show_alert=True)
    elif result['status'] == 'already_claimed':
        msg = f"⏳ شما امروز قبلاً امتیاز خود را دریافت کرده‌اید. فردا دوباره سر بزنید!"
        await bot.answer_callback_query(call.id, msg, show_alert=True)
    else:
        await bot.answer_callback_query(call.id, "❌ خطایی رخ داد.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data == "lucky_spin_menu")
async def lucky_spin_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    user_data = await db.user(user_id)
    current_points = user_data.get('achievement_points', 0) if user_data else 0
    
    msg = (
        f"🎰 **گردونه شانس**\n\n"
        f"💰 موجودی شما: *{current_points} سکه*\n"
        f"💎 هزینه هر چرخش: *{SPIN_COST} سکه*\n\n"
        f"🎁 **جوایز احتمالی:**\n"
        f"▫️ حجم اضافه (تا ۱ گیگ)\n"
        f"▫️ سکه رایگان\n"
        f"▫️ و شاید هم پوچ!\n\n"
        f"آیا شانست رو امتحان می‌کنی؟"
    )
    
    kb = types.InlineKeyboardMarkup()
    if current_points >= SPIN_COST:
        kb.add(types.InlineKeyboardButton("🎲 بچرخون! (50- سکه)", callback_data="do_spin"))
    else:
        kb.add(types.InlineKeyboardButton("❌ موجودی ناکافی", callback_data="shop:main"))
    
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop:main"))
    
    await _safe_edit(user_id, call.message.message_id, msg, reply_markup=kb, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "do_spin")
async def do_spin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    
    if not await db.spend_achievement_points(user_id, SPIN_COST):
        await bot.answer_callback_query(call.id, "موجودی شما کافی نیست!", show_alert=True)
        return

    try:
        await bot.edit_message_text("🎰 در حال چرخش... 🎲", call.message.chat.id, call.message.message_id)
        time.sleep(1.0) 
    except:
        pass

    reward = random.choices(REWARDS_CONFIG, weights=[r['weight'] for r in REWARDS_CONFIG], k=1)[0]
    result_msg = ""
    
    if reward['type'] == "none":
        result_msg = f"😢 اوه! {reward['name']}\nشانس بعدی شاید بهتر باشه."
        
    elif reward['type'] == "points":
        await db.add_achievement_points(user_id, reward['value'])
        result_msg = f"🎉 تبریک! برنده شدی:\n**{reward['name']}**"
        
    elif reward['type'] == "volume":
        user_uuids = await db.uuids(user_id)
        if user_uuids:
            first_uuid = user_uuids[0]['uuid']
            success = await combined_handler.modify_user_on_all_panels(first_uuid, add_gb=reward['value'], add_days=0)
            
            if success:
                result_msg = f"🔥 عالیه! برنده شدی:\n**{reward['name']}**\n(به سرویس شما اضافه شد)"
            else:
                await db.add_achievement_points(user_id, SPIN_COST)
                result_msg = "❌ خطا در واریز حجم. سکه‌های شما برگشت داده شد."
        else:
            await db.add_achievement_points(user_id, SPIN_COST)
            result_msg = "❌ سرویس فعالی برای دریافت حجم ندارید. سکه‌ها برگشت داده شد."

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🎲 دوباره بچرخون", callback_data="lucky_spin_menu"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop:main"))
    
    await _safe_edit(user_id, call.message.message_id, result_msg, reply_markup=kb, parse_mode="Markdown")

# =============================================================================
# 3. Referral System
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "referral:info")
async def referral_info_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang_code = await db.get_user_language(user_id)
    bot_username = (await bot.get_me()).username
    
    # ✅ اصلاح شده: استفاده از متد async کلاس user_formatter
    text = await user_formatter.referral_page(user_id, bot_username, lang_code)
    
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
    )
    await _safe_edit(user_id, call.message.message_id, text, reply_markup=kb, parse_mode="Markdown")

# =============================================================================
# 4. Support System
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def handle_support_request(call: types.CallbackQuery):
    uid, msg_id = call.from_user.id, call.message.message_id
    lang_code = await db.get_user_language(uid)
    
    prompt = (
        f"*{escape_markdown('📝 ارسال تیکت پشتیبانی')}*\n\n"
        f"{escape_markdown('لطفاً پیام خود را (متن، عکس و...) ارسال کنید.')}\n\n"
        f"{escape_markdown('⚠️ پیام شما مستقیم برای ادمین ارسال می‌شود.')}"
    )
    
    kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)
    bot.register_next_step_handler(call.message, get_support_ticket_message, original_msg_id=msg_id)

async def get_support_ticket_message(message: types.Message, original_msg_id: int):
    uid = message.from_user.id
    lang_code = await db.get_user_language(uid)

    await _safe_edit(uid, original_msg_id, "⏳ در حال ارسال...", reply_markup=None)

    try:
        user_info = message.from_user
        user_data = await db.user(uid)
        wallet_balance = user_data.get('wallet_balance', 0.0) if user_data else 0.0
        
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
                fwd = await bot.forward_message(admin_id, uid, message.message_id)
                adm_msg = await bot.send_message(admin_id, admin_caption, parse_mode="MarkdownV2", reply_to_message_id=fwd.message_id)
                admin_message_ids[admin_id] = adm_msg.message_id
            except Exception as e:
                logger.error(f"Support forward error admin {admin_id}: {e}")

        if admin_message_ids:
            first_msg_id = list(admin_message_ids.values())[0]
            ticket_id = await db.create_support_ticket(uid, first_msg_id)
            
            kb_admin = types.InlineKeyboardMarkup()
            kb_admin.add(types.InlineKeyboardButton(
                "✍️ پاسخ به این تیکت", 
                callback_data=f"admin:support_reply:{ticket_id}:{uid}"
            ))
            
            final_caption = f"🎫 *تیکت شماره:* `{ticket_id}`\n" + admin_caption
            
            for admin_id, msg_id in admin_message_ids.items():
                try:
                    await bot.edit_message_text(final_caption, admin_id, msg_id, parse_mode="MarkdownV2", reply_markup=kb_admin)
                except: pass

        success_text = escape_markdown("✅ پیام شما ارسال شد. منتظر پاسخ باشید.")
        kb_back = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
        )
        await _safe_edit(uid, original_msg_id, success_text, reply_markup=kb_back, parse_mode="MarkdownV2")

    except Exception as e:
        logger.error(f"Support Error: {e}")
        await _safe_edit(uid, original_msg_id, "❌ خطا در ارسال.", reply_markup=None)

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
        text = f"✅ آموزش {app_display} آماده است.\n\n👇 روی دکمه زیر کلیک کنید:"
        
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(get_string("btn_view_tutorial", lang), url=link))
        kb.add(types.InlineKeyboardButton(get_string("btn_back_to_apps", lang), callback_data=f"tutorial_os:{os_type}"))
        
        await _safe_edit(call.from_user.id, call.message.message_id, text, reply_markup=kb)
    else:
        await bot.answer_callback_query(call.id, "لینک یافت نشد.", show_alert=True)

# =============================================================================
# 6. Birthday Gift
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "birthday_gift")
async def handle_birthday_gift_request(call: types.CallbackQuery):
    uid, msg_id = call.from_user.id, call.message.message_id
    lang_code = await db.get_user_language(uid)
    user_data = await db.user(uid)
    
    if user_data and user_data.get('birthday'):
        # ✅ اصلاح شده: استفاده از فرمت دستی چون متد در کلاس نیست (یا در صورت وجود، استفاده از آن)
        bday_date = user_data.get('birthday')
        bday_str = to_shamsi(bday_date)
        text = f"🎂 تاریخ تولد شما: {bday_str}\n\n🎁 در روز تولدتان هدیه دریافت خواهید کرد!"
        
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back"))
        await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="Markdown")
    else:
        raw_text = get_string("prompt_birthday", lang_code)
        prompt = escape_markdown(raw_text).replace("YYYY/MM/DD", "`YYYY/MM/DD`")
        kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
        await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
        bot.register_next_step_handler(call.message, get_birthday_step, original_msg_id=msg_id)

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
        bot.register_next_step_handler(message, get_birthday_step, original_msg_id=original_msg_id)

# =============================================================================
# 7. Achievements (Badges)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "achievements")
async def show_achievements_page(call: types.CallbackQuery):
    uid, msg_id = call.from_user.id, call.message.message_id
    user_achievements = await db.get_user_achievements(uid)
    
    total_points = sum(ACHIEVEMENTS.get(ach, {}).get('points', 0) for ach in user_achievements)
    
    level = "تازه‌کار"
    if total_points >= 1000: level = "اسطوره"
    elif total_points >= 500: level = "افسانه"
    elif total_points >= 250: level = "حرفه‌ای"
    elif total_points >= 100: level = "باتجربه"

    categories = {
        "ورزشی": ["bodybuilder", "water_athlete", "aerialist", "swimming_champion"],
        "اجتماعی": ["media_partner", "ambassador", "support_contributor"],
        "وفاداری": ["veteran", "loyal_supporter"],
        "عملکرد": ["pro_consumer", "weekly_champion", "night_owl", "early_bird"],
        "ویژه": ["legend", "vip_friend", "lucky_one"]
    }
    
    text = f"🏅 *دستاوردها*\n🏆 سطح: *{level}*\n⭐ امتیاز: *{total_points}*\n───────────────\n\n"
    
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
        text += escape_markdown("هنوز هیچ نشانی دریافت نکرده‌اید. با فعالیت بیشتر، نشان‌ها را کشف کنید!")

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
    await _safe_edit(call.from_user.id, call.message.message_id, "رشته ورزشی خود را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("achievements:req:"))
async def handle_badge_request(call: types.CallbackQuery):
    badge_code = call.data.split(":")[2]
    uid = call.from_user.id
    
    user_achievements = await db.get_user_achievements(uid)
    if badge_code in user_achievements:
        await bot.answer_callback_query(call.id, "قبلاً این نشان را دارید!", show_alert=True)
        return

    req_id = await db.add_achievement_request(uid, badge_code)
    
    user = call.from_user
    badge_name = ACHIEVEMENTS.get(badge_code, {}).get('name', badge_code)
    admin_msg = f"🏅 *درخواست نشان*\n👤 {escape_markdown(user.first_name)}\nنشان: {escape_markdown(badge_name)}"
    
    admin_kb = types.InlineKeyboardMarkup()
    admin_kb.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin:ach_approve:{req_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin:ach_reject:{req_id}")
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_msg, parse_mode="MarkdownV2", reply_markup=admin_kb)
        except: pass

    await _safe_edit(uid, call.message.message_id, "✅ درخواست شما ثبت شد.", reply_markup=None)
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="achievements"))
    await bot.send_message(uid, "نتیجه بررسی به شما اطلاع داده می‌شود.", reply_markup=kb)

# =============================================================================
# 8. Achievement Shop
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "shop:main")
async def shop_main_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    user_data = await db.user(uid)
    points = user_data.get('achievement_points', 0) if user_data else 0
    access = await db.get_user_access_rights(uid)
    
    text = f"🛍️ *فروشگاه*\nموجودی شما: *{points} امتیاز*\n\nجوایز قابل خرید:"
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
        await bot.answer_callback_query(call.id, "سرویس فعال ندارید.", show_alert=True)
        return
    
    main_uuid = user_uuids[0]['uuid']
    info_before = await combined_handler.get_combined_user_info(main_uuid)
    
    info_after = copy.deepcopy(info_before)
    add_gb = item.get('gb', 0)
    add_days = item.get('days', 0)
    
    info_after['usage_limit_GB'] += add_gb
    if info_after.get('expire') and add_days:
        info_after['expire'] += add_days

    # ✅ اصلاح شده: استفاده از متد async کلاس
    summary = await user_formatter.purchase_summary(info_before, info_after, {"name": item['name']}, lang)
    
    text = (
        f"❓ *تایید خرید*\n\n"
        f"آیتم: {escape_markdown(item['name'])}\n"
        f"هزینه: {item['cost']} امتیاز\n\n"
        f"{summary}\n\n"
        "آیا مطمئن هستید؟"
    )
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ بله، خرید", callback_data=f"shop:exec:{item_id}"),
        types.InlineKeyboardButton("❌ خیر", callback_data="shop:main")
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
                await bot.answer_callback_query(call.id, "✅ خرید انجام شد.", show_alert=True)
                await shop_main_handler(call)
                try:
                    for aid in ADMIN_IDS:
                        await bot.send_message(aid, f"🛍 کاربر {uid} آیتم {item['name']} را خرید.")
                except: pass
                return

        await db.add_achievement_points(uid, item['cost'])
        await bot.answer_callback_query(call.id, "❌ خطا در اعمال جایزه.", show_alert=True)
    else:
        await bot.answer_callback_query(call.id, "❌ موجودی کافی نیست.", show_alert=True)

# =============================================================================
# 9. Connection Doctor
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "connection_doctor")
async def connection_doctor_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    lang = await db.get_user_language(uid)
    
    await _safe_edit(uid, call.message.message_id, "🩺 در حال بررسی...", reply_markup=None)
    
    report = [f"*{escape_markdown(get_string('doctor_report_title', lang))}*", "`──────────────────`"]
    
    user_uuids = await db.uuids(uid)
    is_user_ok = False
    if user_uuids:
        info = await combined_handler.get_combined_user_info(user_uuids[0]['uuid'])
        if info and info.get('is_active'):
            is_user_ok = True
            
    status = "✅ فعال" if is_user_ok else "🔴 غیرفعال"
    report.append(f"وضعیت اکانت: {status}")
    
    active_panels = await db.get_active_panels()
    for p in active_panels:
        handler = None
        if p['panel_type'] == 'hiddify':
            handler = HiddifyPanel(p['api_url'], p['api_token1'], {'proxy_path': p['api_token2']})
        else:
            handler = MarzbanPanel(p['api_url'], p['api_token1'], p['api_token2'])
            
        is_online = await handler.check_connection()
        icon = "✅" if is_online else "⚠️"
        report.append(f"{icon} سرور {escape_markdown(p['name'])}")

    report.append("`──────────────────`")
    if is_user_ok:
        report.append("اگر متصل نمی‌شوید، لینک را آپدیت کنید.")
    else:
        report.append("اکانت شما غیرفعال است. لطفا تمدید کنید.")
        
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    
    await _safe_edit(uid, call.message.message_id, "\n".join(report), reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "coming_soon")
async def coming_soon(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id, "🔜 به زودی...", show_alert=True)

# =============================================================================
# 10. Initial Menus Handlers
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "show_features_guide")
async def show_features_guide_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    lang = await db.get_user_language(uid)
    text = get_string("features_guide_body", lang)
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    await _safe_edit(uid, call.message.message_id, escape_markdown(text), reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "request_service")
async def request_service_handler(call: types.CallbackQuery):
    uid = call.from_user.id
    user = call.from_user
    msg = f"👤 درخواست سرویس جدید از:\n{user.first_name} (@{user.username})\nID: {uid}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg)
        except: pass
        
    await bot.answer_callback_query(call.id, "✅ درخواست شما برای ادمین ارسال شد.", show_alert=True)