# bot/user_handlers/achievements.py

import logging
from telebot import types

from bot.bot_instance import bot
from bot.database import db
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.constants.achievements import ACHIEVEMENTS

logger = logging.getLogger(__name__)

@bot.callback_query_handler(func=lambda call: call.data == "achievements")
async def show_achievements_page(call: types.CallbackQuery):
    """نمایش لیست مدال‌ها و سطح کاربر"""
    uid, msg_id = call.from_user.id, call.message.message_id
    user_achievements = await db.get_user_achievements(uid)
    
    total_points = sum(ACHIEVEMENTS.get(ach, {}).get('points', 0) for ach in user_achievements)
    
    # محاسبه سطح کاربر
    level = "تازه‌کار"
    if total_points >= 1000: level = "افسانه"
    elif total_points >= 500: level = "اسطوره"
    elif total_points >= 250: level = "حرفه‌ای"
    elif total_points >= 100: level = "باتجربه"

    # دسته‌بندی فارسی برای نمایش
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
    kb.add(types.InlineKeyboardButton("ℹ️ راهنما", callback_data="achievements:info"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
    
    await _safe_edit(uid, msg_id, text, reply_markup=kb, parse_mode="MarkdownV2")

@bot.callback_query_handler(func=lambda call: call.data == "achievements:info")
async def show_achievements_info(call: types.CallbackQuery):
    """نمایش راهنمای دریافت مدال‌ها (اصلاح شده برای رفع خطای پارس)."""
    uid = call.from_user.id
    text = "ℹ️ *راهنمای نشان‌ها*\n\n"
    
    for code, info in ACHIEVEMENTS.items():
        text += f"{info['icon']} *{escape_markdown(info['name'])}* \\({info['points']} امتیاز\\):\n"
        text += f"{escape_markdown(info['description'])}\n\n"
        
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="achievements"))
    
    await _safe_edit(uid, call.message.message_id, text, reply_markup=kb, parse_mode="MarkdownV2")