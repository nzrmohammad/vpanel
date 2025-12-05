# bot/user_handlers/feedback.py
from telebot import types
from bot.bot_instance import bot
from bot.keyboards import user
from bot.database import db

@bot.callback_query_handler(func=lambda call: call.data.startswith("feedback:rating:"))
async def submit_rating(call: types.CallbackQuery):
    score = int(call.data.split(":")[2])
    db.save_feedback(call.from_user.id, score) # فقط امتیاز
    
    await bot.edit_message_text(
        "🙏 با تشکر از امتیاز شما.\nاگر نظر متنی دارید، همین الان بنویسید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=None # حذف کیبورد
    )
    # رجیستر کردن هندلر پیام بعدی برای دریافت متن نظر
    bot.register_next_step_handler(call.message, submit_feedback_text)

async def submit_feedback_text(message):
    db.save_feedback_text(message.from_user.id, message.text)
    await bot.send_message(message.chat.id, "✅ نظر شما ثبت شد. متشکریم!")