# bot/user_handlers/settings.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.database import db
from bot.language import get_string

@bot.callback_query_handler(func=lambda call: call.data == "settings")
async def settings_menu_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    # دریافت تنظیمات فعلی کاربر
    settings = db.get_user_settings(user_id)
    # دریافت دسترسی‌ها (برای نمایش دکمه‌های خاص)
    access = db.get_user_access(user_id)
    
    await bot.edit_message_text(
        get_string('settings_title', lang),
        user_id,
        call.message.message_id,
        reply_markup=user.settings(settings, lang, access)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
async def toggle_setting_handler(call: types.CallbackQuery):
    setting_key = call.data.replace("toggle_", "")
    user_id = call.from_user.id
    
    # تغییر در دیتابیس
    new_value = db.toggle_user_setting(user_id, setting_key)
    
    # رفرش منو برای تغییر ایموجی ✅/❌
    lang = db.get_user_lang(user_id)
    settings = db.get_user_settings(user_id)
    access = db.get_user_access(user_id)
    
    await bot.edit_message_text(
        get_string('settings_updated', lang),
        user_id,
        call.message.message_id,
        reply_markup=user.settings(settings, lang, access)
    )

@bot.callback_query_handler(func=lambda call: call.data == "change_language")
async def change_language_handler(call: types.CallbackQuery):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🇮🇷 فارسی", callback_data="set_lang:fa"))
    markup.add(types.InlineKeyboardButton("🇺🇸 English", callback_data="set_lang:en"))
    
    await bot.edit_message_text("Language / زبان:", call.from_user.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_lang:"))
async def set_language_confirm(call: types.CallbackQuery):
    new_lang = call.data.split(":")[1]
    db.set_user_lang(call.from_user.id, new_lang)
    
    await bot.answer_callback_query(call.id, "Language updated! / زبان تغییر کرد.")
    # بازگشت به منوی اصلی با زبان جدید
    await bot.delete_message(call.from_user.id, call.message.message_id)
    # اینجا بهتر است تابع start را دوباره صدا بزنید یا منوی اصلی را بفرستید