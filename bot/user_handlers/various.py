# bot/user_handlers/various.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.database import db
from bot.language import get_string
from bot.config import ENABLE_REFERRAL_SYSTEM, REFERRAL_REWARD_GB, ADMIN_IDS

@bot.message_handler(commands=['start'])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # 1. بررسی وجود کاربر و ثبت‌نام
    # متد user_exists وجود ندارد، از get_user_by_telegram_id استفاده می‌کنیم
    existing_user = await db.get_user_by_telegram_id(user_id)
    
    if not existing_user:
        # ثبت نام کاربر جدید
        await db.add_or_update_user(user_id, username, first_name, last_name)
        
        # بررسی کد دعوت (Deep Link)
        args = message.text.split()
        if len(args) > 1:
            referral_code = args[1]
            # اگر کد دعوت معتبر باشد، معرف را ست می‌کنیم
            # (نکته: در دیتابیس شما متد set_referrer کد معرف را می‌گیرد)
            await db.set_referrer(user_id, referral_code)
    else:
        # آپدیت اطلاعات کاربر (مثلاً اگر یوزرنیم تغییر کرده باشد)
        await db.add_or_update_user(user_id, username, first_name, last_name)
    
    lang = await db.get_user_language(user_id)
    
    # بررسی ادمین بودن (از کانفیگ خوانده می‌شود چون در دیتابیس متد is_admin نداریم)
    is_admin = user_id in ADMIN_IDS
    
    text = get_string('start_prompt', lang)
    markup = await user.main(is_admin, lang) # منوی اصلی هم async است
    
    await bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "daily_checkin")
async def daily_checkin_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    # lang = await db.get_user_language(user_id) # اگر نیاز شد
    
    # استفاده از متد صحیح claim_daily_checkin
    result = await db.claim_daily_checkin(user_id) 
    
    if result['status'] == 'success':
        msg = f"✅ تبریک! شما {result['points']} امتیاز دریافت کردید.\nتعداد روزهای متوالی: {result['streak']}"
    elif result['status'] == 'already_claimed':
        msg = f"⏳ شما امروز قبلاً امتیاز خود را دریافت کرده‌اید. فردا دوباره سر بزنید!"
    else:
        msg = "❌ خطایی رخ داد."
        
    await bot.answer_callback_query(call.id, msg, show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "referral:info")
async def referral_info_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    lang = await db.get_user_language(user_id)
    
    if not ENABLE_REFERRAL_SYSTEM:
        await bot.answer_callback_query(call.id, "این سیستم غیرفعال است.")
        return

    # دریافت کد رفرال اختصاصی کاربر
    my_ref_code = await db.get_or_create_referral_code(user_id)
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={my_ref_code}"
    
    # دریافت لیست زیرمجموعه‌ها برای شمارش
    referred_users = await db.get_referred_users(user_id)
    count = len(referred_users)
    
    text = (
        f"👥 <b>سیستم دعوت از دوستان</b>\n\n"
        f"🔗 <b>لینک اختصاصی شما:</b>\n<code>{link}</code>\n\n"
        f"🎁 <b>پاداش:</b> {REFERRAL_REWARD_GB} گیگابایت برای هر نفر\n"
        f"📊 <b>تعداد دعوت‌ها:</b> {count} نفر"
    )
    
    await bot.edit_message_text(
        text, user_id, call.message.message_id,
        reply_markup=user.back_btn("back", lang),
        parse_mode='HTML'
    )