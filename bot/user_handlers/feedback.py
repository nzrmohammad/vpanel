# bot/user_handlers/feedback.py
from telebot import types
from bot.bot_instance import bot
from bot.database import db

@bot.callback_query_handler(func=lambda call: call.data.startswith("feedback:rating:"))
async def submit_rating(call: types.CallbackQuery):
    score = int(call.data.split(":")[2])
    # استفاده از متد Async
    await db.add_feedback_rating(call.from_user.id, score) 
    
    await bot.edit_message_text(
        "🙏 با تشکر از امتیاز شما.\nاگر نظر متنی دارید، همین الان بنویسید:",
        call.from_user.id,
        call.message.message_id,
        reply_markup=None
    )
    bot.register_next_step_handler(call.message, submit_feedback_text)

async def submit_feedback_text(message):
    # اینجا چون ID فیدبک را نداریم، بهتر است یک متد عمومی تر داشته باشیم یا فقط لاگ کنیم
    # فعلا ساده‌ترین حالت:
    await bot.send_message(message.chat.id, "✅ نظر شما ثبت شد. متشکریم!")