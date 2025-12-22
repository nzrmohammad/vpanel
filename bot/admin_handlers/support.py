# bot/admin_handlers/support.py

import logging
from telebot import types
from bot.database import db
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)
bot = None
admin_conversations = None

def initialize_support_handlers(b, conv_dict):
    """مقادیر bot و admin_conversations را دریافت می‌کند."""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def prompt_for_reply(call: types.CallbackQuery, params: list):
    """
    هندلر کلیک روی دکمه '✍️ پاسخ به این تیکت'.
    از ادمین می‌خواهد پاسخ را تایپ کند.
    """
    admin_id = call.from_user.id
    msg_id = call.message.message_id
    
    try:
        # params[0] = ticket_id, params[1] = user_id
        ticket_id = int(params[0])
        user_id_to_reply = int(params[1])
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "خطا: اطلاعات دکمه ناقص است.", show_alert=True)
        return

    # دریافت متن اصلی پیام تیکت برای استفاده بعدی (چون بعداً نمی‌توانیم متن را فچ کنیم)
    original_text = call.message.text or call.message.caption or "متن تیکت در دسترس نیست"

    # ذخیره وضعیت برای گام بعدی
    admin_conversations[admin_id] = {
        'action': 'support_reply',
        'user_id': user_id_to_reply,
        'ticket_id': ticket_id,
        'original_msg_id': msg_id, # شناسه پیام تیکت در چت ادمین
        'original_text': original_text # ذخیره متن برای ویرایش نهایی
    }

    # دکمه را موقتاً حذف می‌کنیم تا دوباره کلیک نشود
    try:
        await bot.edit_message_reply_markup(admin_id, msg_id, reply_markup=None)
    except Exception:
        pass 

    # از ادمین می‌خواهیم که پاسخ را تایپ کند
    await bot.send_message(admin_id, 
                     f"✍️ لطفاً پاسخ خود را برای تیکت شماره `{ticket_id}` تایپ و ارسال کنید\\.\n\\(برای لغو، دستور /cancel را ارسال کنید\\)",
                     parse_mode="MarkdownV2")
    
    # ثبت هندلر برای دریافت پیام بعدی ادمین
    bot.register_next_step_handler(call.message, send_reply_to_user)

async def send_reply_to_user(message: types.Message):
    """
    پاسخ متنی ادمین را دریافت کرده و برای کاربر ارسال می‌کند.
    """
    admin_id = message.from_user.id
    
    # بررسی دستور لغو
    if message.text == '/cancel':
        if admin_id in admin_conversations:
            convo_data = admin_conversations.pop(admin_id, None)
            # دکمه را به پیام تیکت بازمی‌گردانیم
            try:
                if convo_data:
                    kb_admin = types.InlineKeyboardMarkup()
                    kb_admin.add(types.InlineKeyboardButton(
                        "✍️ پاسخ به این تیکت", 
                        callback_data=f"admin:support_reply:{convo_data['ticket_id']}:{convo_data['user_id']}"
                    ))
                    await bot.edit_message_reply_markup(admin_id, convo_data['original_msg_id'], reply_markup=kb_admin)
            except Exception:
                pass
        await bot.send_message(admin_id, "عملیات لغو شد. تیکت دوباره باز شد.")
        return

    # بررسی اینکه آیا ادمین در وضعیت «پاسخ به تیکت» است یا خیر
    if admin_id not in admin_conversations or admin_conversations[admin_id].get('action') != 'support_reply':
        return 

    convo_data = admin_conversations.pop(admin_id, None)
    if not convo_data:
        return

    user_id_to_reply = convo_data['user_id']
    ticket_id = convo_data['ticket_id']
    original_msg_id = convo_data['original_msg_id']
    original_text = convo_data.get('original_text', '')
    admin_name = escape_markdown(message.from_user.first_name)
    
    try:
        # فرمت کردن پیام برای کاربر
        reply_text_lines = [
            f"💬 *پاسخ پشتیبانی از طرف {admin_name}*",
            f"`──────────────────`",
            f"{escape_markdown(message.text)}"
        ]
        reply_text = "\n".join(reply_text_lines)

        # ارسال پاسخ به کاربر
        await bot.send_message(user_id_to_reply, reply_text, parse_mode="MarkdownV2")
        
        # تایید ارسال برای ادمین (ریپلای روی پیام ادمین)
        await bot.reply_to(message, "✅ پاسخ شما با موفقیت به کاربر ارسال شد.")
        
        # بستن تیکت در دیتابیس
        await db.close_ticket(ticket_id)
        
        # ویرایش پیام اصلی تیکت در چت ادمین برای نشان دادن اینکه بسته شده
        try:
            # اضافه کردن برچسب بسته شده به متن ذخیره شده
            closed_prefix = "✅ (بسته شد)\n\n"
            
            # اگر پیام اصلی کپشن داشت
            if original_text and len(original_text) > 0:
                 new_text = closed_prefix + original_text
            else:
                 new_text = closed_prefix + "تیکت بسته شد"

            # تلاش برای ادیت (بسته به نوع پیام ممکن است text یا caption باشد)
            try:
                await bot.edit_message_caption(caption=new_text, chat_id=admin_id, message_id=original_msg_id, reply_markup=None)
            except:
                await bot.edit_message_text(text=new_text, chat_id=admin_id, message_id=original_msg_id, reply_markup=None)
                
        except Exception as e:
            logger.warning(f"Could not update original ticket message: {e}")

    except Exception as e:
        logger.error(f"Failed to send admin reply to user {user_id_to_reply}: {e}")
        await bot.reply_to(message, "❌ خطایی در ارسال پاسخ به کاربر رخ داد. لطفاً دوباره تلاش کنید.")
        
        # بازگرداندن وضعیت مکالمه برای تلاش مجدد
        admin_conversations[admin_id] = convo_data
        bot.register_next_step_handler(message, send_reply_to_user)