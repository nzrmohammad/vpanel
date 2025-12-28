# bot/user_handlers/settings.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user as user_menu
from bot.database import db
from bot.language import get_string

@bot.callback_query_handler(func=lambda call: call.data == "settings")
async def settings_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    settings = await db.get_user_settings(user_id)
    access = await db.get_user_access_rights(user_id)
    
    await bot.edit_message_text(
        get_string('settings_title', lang),
        user_id,
        call.message.message_id,
        reply_markup=await user_menu.settings(settings, lang, access)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle:"))
async def toggle_setting_handler(call: types.CallbackQuery):
    setting_key = call.data.split(":")[1]
    user_id = call.from_user.id
    
    current_settings = await db.get_user_settings(user_id)
    current_val = current_settings.get(setting_key, True)
    
    await db.update_user_setting(user_id, setting_key, not current_val)
    
    lang = await db.get_user_language(user_id)
    settings = await db.get_user_settings(user_id)
    access = await db.get_user_access_rights(user_id)
    
    try:
        await bot.edit_message_reply_markup(
            user_id,
            call.message.message_id,
            reply_markup=await user_menu.settings(settings, lang, access)
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == "change_language")
async def change_language_handler(call: types.CallbackQuery):
    markup = await user_menu.language_change_menu()
    
    await bot.edit_message_text("Language / زبان:", call.from_user.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang:"))
async def set_language_confirm(call: types.CallbackQuery):
    new_lang = call.data.split(":")[1]
    await db.set_user_language(call.from_user.id, new_lang)
    
    await bot.answer_callback_query(call.id, "Language updated! / زبان تغییر کرد.")
    await settings_menu_handler(call)