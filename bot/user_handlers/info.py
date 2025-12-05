# bot/user_handlers/info.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.database import db
from bot.language import get_string
from bot.config import ADMIN_SUPPORT_CONTACT, TUTORIAL_LINKS

@bot.callback_query_handler(func=lambda call: call.data == "tutorials")
async def tutorials_menu(call: types.CallbackQuery):
    lang = db.get_user_lang(call.from_user.id)
    await bot.edit_message_text(
        get_string('prompt_select_os', lang),
        call.from_user.id,
        call.message.message_id,
        reply_markup=user.tutorial_main_menu(lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_os:"))
async def tutorial_os_handler(call: types.CallbackQuery):
    os_type = call.data.split(":")[1]
    lang = db.get_user_lang(call.from_user.id)
    
    await bot.edit_message_text(
        get_string('prompt_select_app', lang),
        call.from_user.id,
        call.message.message_id,
        reply_markup=user.tutorial_os_menu(os_type, lang)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("tutorial_app:"))
async def show_tutorial_link(call: types.CallbackQuery):
    # tutorial_app:android:v2rayng
    parts = call.data.split(":")
    os_type, app_key = parts[1], parts[2]
    lang = db.get_user_lang(call.from_user.id)
    
    link = TUTORIAL_LINKS.get(os_type, {}).get(app_key)
    
    if link:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(get_string('btn_view_tutorial', lang), url=link))
        markup.add(user.back_btn(f"tutorial_os:{os_type}", lang))
        
        await bot.edit_message_text(
            get_string('tutorial_ready_header', lang),
            call.from_user.id,
            call.message.message_id,
            reply_markup=markup
        )
    else:
        await bot.answer_callback_query(call.id, "Link not found.")

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def support_info(call: types.CallbackQuery):
    lang = db.get_user_lang(call.from_user.id)
    text = get_string('support_guidance_body', lang).format(admin_contact=ADMIN_SUPPORT_CONTACT)
    
    await bot.edit_message_text(
        text,
        call.from_user.id,
        call.message.message_id,
        reply_markup=user.back_btn("back", lang)
    )