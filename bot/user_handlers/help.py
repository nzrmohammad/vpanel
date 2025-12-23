# bot/user_handlers/help.py

import logging
from telebot import types

from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.language import get_string
from bot.config import TUTORIAL_LINKS

logger = logging.getLogger(__name__)

# =============================================================================
# بخش آموزش‌های اتصال (Tutorials)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "tutorials")
async def show_tutorial_main_menu(call: types.CallbackQuery):
    """نمایش منوی انتخاب سیستم عامل برای آموزش"""
    lang = await db.get_user_language(call.from_user.id)
    await _safe_edit(
        call.from_user.id, call.message.message_id,
        get_string("prompt_select_os", lang),
        reply_markup=await user_menu.tutorial_main_menu(lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_os:"))
async def show_tutorial_os_menu(call: types.CallbackQuery):
    """نمایش لیست برنامه‌های موجود برای یک سیستم عامل خاص"""
    os_type = call.data.split(":")[1]
    lang = await db.get_user_language(call.from_user.id)
    
    await _safe_edit(
        call.from_user.id, call.message.message_id,
        get_string("prompt_select_app", lang),
        reply_markup=await user_menu.tutorial_os_menu(os_type, lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_app:"))
async def send_tutorial_link(call: types.CallbackQuery):
    """ارسال لینک و متن آموزش انتخاب شده"""
    _, os_type, app_name = call.data.split(":")
    lang = await db.get_user_language(call.from_user.id)
    
    # دریافت لینک از کانفیگ
    link = TUTORIAL_LINKS.get(os_type, {}).get(app_name)
    
    if link:
        app_display = f"{os_type.capitalize()} - {app_name.capitalize()}"
        
        # دریافت متن‌ها از فایل زبان
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
# راهنمای ویژگی‌ها (Features Guide)
# =============================================================================

@bot.callback_query_handler(func=lambda call: call.data == "show_features_guide")
async def show_features_guide_handler(call: types.CallbackQuery):
    """نمایش متن راهنمای ویژگی‌های ربات"""
    uid = call.from_user.id
    lang = await db.get_user_language(uid)
    
    # دریافت متن طولانی راهنما
    text = get_string("features_guide_body", lang)
    
    kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 Back", callback_data="back"))
    await _safe_edit(uid, call.message.message_id, escape_markdown(text), reply_markup=kb, parse_mode="MarkdownV2")