# bot/admin_handlers/wallet/charge_requests.py

import logging
import asyncio
from telebot import types
from sqlalchemy import select
from bot.database import db
from bot.db.base import User, ChargeRequest
from bot.utils.formatters import escape_markdown
from bot.utils.network import _safe_edit, delete_message_delayed
from bot.keyboards import user as user_menu
from bot.bot_instance import bot

logger = logging.getLogger(__name__)

async def handle_charge_request_callback(call: types.CallbackQuery, params: list):
    """پاسخ ادمین به درخواست شارژ (رسید ارسالی کاربر)"""
    try:
        decision = params[0]  # confirm یا reject
        request_id = int(params[1])
    except (IndexError, ValueError):
        await bot.answer_callback_query(call.id, "خطا در پارامترها.", show_alert=True)
        return

    async with db.get_session() as session:
        # دریافت درخواست شارژ
        stmt = select(ChargeRequest).where(ChargeRequest.id == request_id)
        result = await session.execute(stmt)
        charge_req = result.scalar_one_or_none()

        # بررسی اعتبار درخواست
        if not charge_req or not charge_req.is_pending:
            await bot.answer_callback_query(call.id, "این درخواست قبلاً پردازش شده است.", show_alert=True)
            try:
                await bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
            except:
                pass
            return

        user_id = charge_req.user_id
        amount = charge_req.amount
        user_message_id = charge_req.message_id
        
        # دریافت اطلاعات کاربر برای تعیین زبان
        user = await session.get(User, user_id)
        lang_code = user.lang_code if user else 'fa'

        try:
            # حالت تایید (Confirm)
            # ===============================================================
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
                        f"✅ *واریزی شما تایید شد\\!* \n\n"
                        f"💰 مبلغ: `{amount_str} تومان`\n"
                        f"💳 موجودی فعلی: `{int(user.wallet_balance):,} تومان`\n\n"
                        f"👇 حالا می‌توانید سرویس مورد نظر خود را خریداری کنید:"
                    )
                    
                    # اطلاع به کاربر + ارسال منوی خرید
                    try:
                        post_charge_kb = await user_menu.post_charge_menu(lang_code)
                        # تلاش برای ویرایش پیام قبلی
                        await _safe_edit(user_id, user_message_id, success_text, reply_markup=post_charge_kb)
                    except Exception:
                        # اگر ویرایش نشد (مثلاً پیام قدیمی است)، پیام جدید ارسال کن
                        try:
                            post_charge_kb = await user_menu.post_charge_menu(lang_code)
                            await bot.send_message(user_id, success_text, reply_markup=post_charge_kb, parse_mode="MarkdownV2")
                        except: pass
                    
                    # --- مدیریت پیام ادمین (ویرایش + حذف با تاخیر) ---
                    try: 
                        status_text = f"✅ تایید شد توسط {call.from_user.first_name}"
                        if call.message.caption:
                            await bot.edit_message_caption(
                                chat_id=call.message.chat.id, 
                                message_id=call.message.message_id, 
                                caption=status_text, 
                                reply_markup=None
                            )
                        else:
                            await bot.edit_message_text(
                                chat_id=call.message.chat.id, 
                                message_id=call.message.message_id, 
                                text=status_text, 
                                reply_markup=None
                            )
                    except Exception as e: 
                        logger.warning(f"Admin msg edit error: {e}")

                    # زمان‌بندی برای حذف پیام ادمین
                    delete_delay = int(await db.get_config('ticket_auto_delete_time', 60))
                    asyncio.create_task(
                        delete_message_delayed(call.message.chat.id, call.message.message_id, delete_delay)
                    )

                    await bot.answer_callback_query(call.id, "✅ تایید شد.")
                else:
                    await bot.answer_callback_query(call.id, "❌ خطا در دیتابیس.", show_alert=True)

            # ===============================================================
            # حالت رد (Reject)
            # ===============================================================
            elif decision == 'reject':
                charge_req.is_pending = False
                await session.commit()
                
                # متن پیام رد (فرمت MarkdownV2 برای بولد شدن صحیح)
                reject_text = (
                    "❌ *درخواست شارژ شما رد شد\\.*\n\n"
                    "علت: عدم تایید تراکنش توسط مدیریت\\.\n"
                    "در صورت وجود مشکل، لطفاً با پشتیبانی تماس بگیرید\\."
                )
                
                # ساخت دکمه‌های زیر پیام کاربر
                try:
                    support_id = await db.get_config('support_username')
                    kb = types.InlineKeyboardMarkup()
                    kb.add(types.InlineKeyboardButton("🔙 بازگشت به کیف پول", callback_data="wallet:main"))
                    
                    # اگر آیدی پشتیبانی در تنظیمات باشد، دکمه آن نمایش داده می‌شود
                    if support_id:
                        kb.add(types.InlineKeyboardButton("📞 تماس با پشتیبانی", url=f"https://t.me/{support_id.replace('@', '').strip()}"))
                    
                    # ویرایش پیام کاربر
                    await _safe_edit(user_id, user_message_id, reject_text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"Error sending reject msg to user: {e}")

                # مدیریت پیام ادمین (تغییر وضعیت + حذف با تأخیر)
                try:
                    # 1. تغییر متن یا کپشن پیام ادمین برای نشان دادن وضعیت "رد شده"
                    status_text = f"❌ رد شد توسط {call.from_user.first_name}"
                    if call.message.caption:
                        await bot.edit_message_caption(
                            chat_id=call.message.chat.id, 
                            message_id=call.message.message_id, 
                            caption=status_text, 
                            reply_markup=None
                        )
                    else:
                        await bot.edit_message_text(
                            chat_id=call.message.chat.id, 
                            message_id=call.message.message_id, 
                            text=status_text, 
                            reply_markup=None
                        )
                except: pass

                # 2. زمان‌بندی برای حذف پیام ادمین
                delete_delay = int(await db.get_config('ticket_auto_delete_time', 60))
                
                # استفاده از تابع عمومی که در utils/network.py تعریف کردید
                asyncio.create_task(
                    delete_message_delayed(call.message.chat.id, call.message.message_id, delete_delay)
                )
                
                await bot.answer_callback_query(call.id, "❌ رد شد.")
                
        except Exception as e:
            logger.error(f"Error handling charge request {request_id}: {e}")
            await bot.answer_callback_query(call.id, "خطای سیستمی.", show_alert=False)