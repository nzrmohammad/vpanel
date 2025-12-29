# bot/user_handlers/info.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user_menu
from bot.database import db
from bot.language import get_string
from bot.config import TUTORIAL_LINKS

@bot.callback_query_handler(func=lambda call: call.data == "tutorials")
async def tutorials_menu(call: types.CallbackQuery):
    # ✅ اصلاح نام و افزودن await
    lang = await db.get_user_language(call.from_user.id)
    
    # ✅ افزودن await برای کیبورد
    markup = await user_menu.tutorial_main_menu(lang)
    
    await bot.edit_message_text(
        get_string('prompt_select_os', lang),
        call.from_user.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_os:"))
async def tutorial_os_handler(call: types.CallbackQuery):
    os_type = call.data.split(":")[1]
    lang = await db.get_user_language(call.from_user.id) # ✅ await
    
    # ✅ افزودن await برای کیبورد
    markup = await user_menu.tutorial_os_menu(os_type, lang)
    
    await bot.edit_message_text(
        get_string('prompt_select_app', lang),
        call.from_user.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_app:"))
async def show_tutorial_link(call: types.CallbackQuery):
    parts = call.data.split(":")
    os_type, app_key = parts[1], parts[2]
    lang = await db.get_user_language(call.from_user.id) # ✅ await
    
    link = TUTORIAL_LINKS.get(os_type, {}).get(app_key)
    
    if link:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(get_string('btn_view_tutorial', lang), url=link))
        # دکمه back_btn سینک است و نیاز به await ندارد
        markup.add(user_menu.back_btn(f"tutorial_os:{os_type}", lang))
        
        await bot.edit_message_text(
            get_string('tutorial_ready_header', lang),
            call.from_user.id,
            call.message.message_id,
            reply_markup=markup
        )
    else:
        await bot.answer_callback_query(call.id, "Link not found.")