# bot/user_handlers/various.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.database import db
from bot.language import get_string
from bot.config import ENABLE_REFERRAL_SYSTEM, REFERRAL_REWARD_GB

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    
    # 1. ثبت نام یا آپدیت کاربر در دیتابیس
    if not db.user_exists(user_id):
        # بررسی کد دعوت (Deep Link)
        args = message.text.split()
        referrer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
        
        db.add_telegram_user(user_id, message.from_user.first_name, referrer_id)
    
    lang = db.get_user_lang(user_id)
    is_admin = db.is_admin(user_id)
    
    text = get_string('start_prompt', lang)
    markup = user.main(is_admin, lang)
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "daily_checkin")
async def daily_checkin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    result = db.perform_daily_checkin(user_id) # باید True/False یا مقدار پاداش برگرداند
    
    if result['success']:
        msg = f"✅ تبریک! شما {result['reward']} امتیاز دریافت کردید."
    else:
        msg = f"⏳ شما امروز قبلاً امتیاز گرفته‌اید. زمان باقی‌مانده: {result['hours_left']} ساعت"
        
    await bot.answer_callback_query(call.id, msg, show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "referral:info")
async def referral_info_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = db.get_user_lang(user_id)
    
    if not ENABLE_REFERRAL_SYSTEM:
        await bot.answer_callback_query(call.id, "این سیستم غیرفعال است.")
        return

    link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    stats = db.get_referral_stats(user_id)
    
    text = (
        f"👥 <b>سیستم دعوت از دوستان</b>\n\n"
        f"🔗 <b>لینک اختصاصی شما:</b>\n<code>{link}</code>\n\n"
        f"🎁 <b>پاداش:</b> {REFERRAL_REWARD_GB} گیگابایت برای هر نفر\n"
        f"📊 <b>تعداد دعوت‌ها:</b> {stats['count']} نفر"
    )
    
    await bot.edit_message_text(
        text, user_id, call.message.message_id,
        reply_markup=user_menu.back_btn("back", lang),
        parse_mode='HTML'
    )