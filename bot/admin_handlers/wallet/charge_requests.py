# bot/admin_handlers/wallet/charge_requests.py

import logging
from telebot import types
from sqlalchemy import select
from bot.database import db
from bot.db.base import User, ChargeRequest
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit
from bot.keyboards import user as user_menu
from bot.bot_instance import bot

logger = logging.getLogger(__name__)

async def handle_charge_request_callback(call: types.CallbackQuery, params: list):
    """پاسخ ادمین به درخواست شارژ (رسید ارسالی کاربر)"""
    try:
        decision = params[0] # confirm یا reject
        request_id = int(params[1])
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "خطا در پارامترها.", show_alert=True)
        return

    async with db.get_session() as session:
        # دریافت درخواست شارژ
        stmt = select(ChargeRequest).where(ChargeRequest.id == request_id)
        result = await session.execute(stmt)
        charge_req = result.scalar_one_or_none()

        if not charge_req or not charge_req.is_pending:
            await bot.answer_callback_query(call.id, "این درخواست قبلاً پردازش شده است.", show_alert=True)
            # تلاش برای حذف پیام اگر قبلاً پردازش شده
            try: await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
            except: pass
            return

        user_id = charge_req.user_id
        amount = charge_req.amount
        user_message_id = charge_req.message_id
        
        # دریافت اطلاعات کاربر
        user = await session.get(User, user_id)
        lang_code = user.lang_code if user else 'fa'

        try:
            if decision == 'confirm':
                success = await db.update_wallet_balance(
                    user_id, amount, 'deposit', 
                    f"تایید واریزی (درخواست #{request_id})",
                    session=session
                )
                
                if success:
                    charge_req.is_pending = False
                    await session.commit()
                    
                    amount_str = f"{amount:,.0f}"
                    success_text = (
                        f"✅ *واریزی شما تایید شد!* \n\n"
                        f"💰 مبلغ: `{amount_str} تومان`\n"
                        f"💳 موجودی فعلی: `{int(user.wallet_balance):,} تومان`\n\n"
                        f"👇 حالا می‌توانید سرویس مورد نظر خود را خریداری کنید:"
                    )
                    
                    # اطلاع به کاربر + دکمه خرید سرویس
                    try:
                        post_charge_kb = await user_menu.post_charge_menu(lang_code)
                        await _safe_edit(user_id, user_message_id, success_text, reply_markup=post_charge_kb)
                    except Exception:
                        try:
                            post_charge_kb = await user_menu.post_charge_menu(lang_code)
                            await bot.send_message(user_id, success_text, reply_markup=post_charge_kb, parse_mode="MarkdownV2")
                        except: pass
                    
                    # ✅ حذف پیام از گروه مدیریت (طبق درخواست شما)
                    try: await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
                    except Exception as e: logger.warning(f"Admin msg delete error: {e}")

                    await bot.answer_callback_query(call.id, "✅ تایید شد.")
                else:
                    await bot.answer_callback_query(call.id, "❌ خطا در دیتابیس.", show_alert=True)

            elif decision == 'reject':
                charge_req.is_pending = False
                await session.commit()
                
                reject_text = (
                    "❌ *درخواست شارژ شما رد شد.*\n\n"
                    "علت: عدم تایید تراکنش توسط مدیریت.\n"
                    "در صورت وجود مشکل، لطفاً با پشتیبانی تماس بگیرید."
                )
                
                # اطلاع به کاربر
                try:
                    support_id = await db.get_config('support_username')
                    kb = types.InlineKeyboardMarkup()
                    kb.add(types.InlineKeyboardButton("🔙 بازگشت به کیف پول", callback_data="wallet:main"))
                    if support_id:
                        kb.add(types.InlineKeyboardButton("📞 تماس با پشتیبانی", url=f"https://t.me/{support_id.replace('@', '').strip()}"))
                    
                    await _safe_edit(user_id, user_message_id, escape_markdown(reject_text), reply_markup=kb)
                except: pass

                # ✅ حذف پیام از گروه مدیریت
                try: await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
                except Exception as e: logger.warning(f"Admin msg delete error: {e}")
                
                await bot.answer_callback_query(call.id, "❌ رد شد.")
                
        except Exception as e:
            logger.error(f"Error handling charge request {request_id}: {e}")
            await bot.answer_callback_query(call.id, "خطای سیستمی.", show_alert=False)