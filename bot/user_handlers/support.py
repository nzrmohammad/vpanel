# bot/user_handlers/support.py

import logging
from telebot import types

from bot.bot_instance import bot
from bot.database import db
from bot.keyboards import user as user_menu
from bot.utils.network import _safe_edit
from bot.utils.formatters import escape_markdown
from bot.language import get_string
from bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

# دیکشنری برای مدیریت وضعیت کاربرانی که در حال ارسال تیکت هستند
# Format: {user_id: {'msg_id': 123, ...}}
support_states = {}

@bot.callback_query_handler(func=lambda call: call.data == "support:new")
async def handle_support_request(call: types.CallbackQuery):
    """شروع پروسه ارسال تیکت پشتیبانی"""
    uid = call.from_user.id
    msg_id = call.message.message_id
    lang_code = await db.get_user_language(uid)
    
    prompt = (
        f"*{escape_markdown('📝 تیکت پشتیبانی جدید')}*\n\n"
        f"{escape_markdown('لطفاً پیام خود را (متن، عکس، ویدیو و...) در همین چت ارسال کنید.')}\n\n"
        f"{escape_markdown('⚠️ پیام شما مستقیماً برای مدیریت ارسال خواهد شد.')}"
    )
    
    # دکمه انصراف
    kb = await user_menu.user_cancel_action(back_callback="back", lang_code=lang_code)
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb, parse_mode="MarkdownV2")
    
    # ذخیره وضعیت کاربر برای دریافت پیام بعدی
    support_states[uid] = {
        'original_msg_id': msg_id
    }

@bot.message_handler(content_types=['text', 'photo', 'video', 'document', 'voice'], func=lambda m: m.from_user.id in support_states)
async def process_support_ticket(message: types.Message):
    """دریافت پیام کاربر و ارسال برای ادمین"""
    uid = message.from_user.id
    
    # اگر کاربر دستور لغو یا استارت فرستاد
    if message.text and message.text.startswith('/'):
        if uid in support_states:
            del support_states[uid]
        return # اجازه میدهیم هندلرهای اصلی (مثل start) اجرا شوند

    state = support_states.pop(uid) # دریافت و حذف وضعیت (یکبار مصرف)
    original_msg_id = state.get('original_msg_id')
    lang_code = await db.get_user_language(uid)

    # نمایش وضعیت "در حال ارسال"
    await _safe_edit(uid, original_msg_id, "⏳ در حال ارسال...", reply_markup=None)

    try:
        user_info = message.from_user
        user_data = await db.user(uid)
        wallet_balance = user_data.get('wallet_balance', 0.0) if user_data else 0.0
        
        # ساخت کپشن برای ادمین
        caption_lines = [
            f"💬 *تیکت جدید*",
            f"👤 {escape_markdown(user_info.first_name)}",
            f"🆔 `{uid}`",
            f"💰 موجودی: {wallet_balance:,.0f}"
        ]
        if user_info.username:
            caption_lines.insert(2, f"🔗 @{escape_markdown(user_info.username)}")
            
        admin_caption = "\n".join(caption_lines)
        
        # ارسال برای همه ادمین‌ها
        admin_message_ids = {}
        for admin_id in ADMIN_IDS:
            try:
                # 1. فروارد پیام کاربر
                fwd = await bot.forward_message(admin_id, uid, message.message_id)
                # 2. ارسال اطلاعات کاربر به صورت ریپلای روی پیام فروارد شده
                adm_msg = await bot.send_message(
                    admin_id, 
                    admin_caption, 
                    parse_mode="MarkdownV2", 
                    reply_to_message_id=fwd.message_id
                )
                admin_message_ids[admin_id] = adm_msg.message_id
            except Exception as e:
                logger.error(f"Support forward error admin {admin_id}: {e}")

        # ثبت در دیتابیس (اگر حداقل برای یک ادمین رفت)
        if admin_message_ids:
            first_msg_id = list(admin_message_ids.values())[0]
            ticket_id = await db.create_support_ticket(uid, first_msg_id)
            
            # اضافه کردن دکمه "پاسخ" برای ادمین
            kb_admin = types.InlineKeyboardMarkup()
            kb_admin.add(types.InlineKeyboardButton(
                "✍️ پاسخ به این تیکت", 
                callback_data=f"admin:support_reply:{ticket_id}:{uid}"
            ))
            
            final_caption = f"🎫 *شماره تیکت:* `{ticket_id}`\n" + admin_caption
            
            # آپدیت پیام ادمین‌ها با شماره تیکت و دکمه
            for admin_id, msg_id in admin_message_ids.items():
                try:
                    await bot.edit_message_text(final_caption, admin_id, msg_id, parse_mode="MarkdownV2", reply_markup=kb_admin)
                except: pass

            # پیام موفقیت به کاربر
            success_text = escape_markdown("✅ پیام شما با موفقیت ارسال شد. لطفاً منتظر پاسخ بمانید.")
            kb_back = types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(f"🔙 {get_string('back', lang_code)}", callback_data="back")
            )
            await _safe_edit(uid, original_msg_id, success_text, reply_markup=kb_back, parse_mode="MarkdownV2")
            
    except Exception as e:
        logger.error(f"Support Error: {e}")
        await _safe_edit(uid, original_msg_id, "❌ خطا در ارسال پیام.", reply_markup=None)