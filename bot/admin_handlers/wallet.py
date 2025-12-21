# bot/admin_handlers/wallet.py

import logging
from telebot import types
from sqlalchemy import select
from bot.database import db
from bot.db.base import User, ChargeRequest
from bot.utils import escape_markdown, _safe_edit
from bot.keyboards import user as user_menu
from bot.keyboards import admin as admin_menu

logger = logging.getLogger(__name__)
bot = None
admin_conversations = None

def initialize_wallet_handlers(b, conv_dict):
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

# ---------------------------------------------------------
# 1. مدیریت رسیدهای واریزی (Charge Request)
# ---------------------------------------------------------

async def handle_charge_request_callback(call: types.CallbackQuery, params: list):
    """
    پاسخ ادمین به درخواست شارژ.
    Format: admin:charge_req:<decision>:<request_id>
    """
    admin_id = call.from_user.id
    
    try:
        # params: [decision, request_id]
        if len(params) < 2: raise ValueError
        decision = params[0] # 'confirm' or 'reject'
        request_id = int(params[1])
    except:
        await bot.answer_callback_query(call.id, "خطا در پارامترها.", show_alert=True)
        return

    async with db.get_session() as session:
        # قفل کردن ردیف برای جلوگیری از تداخل
        stmt = select(ChargeRequest).where(ChargeRequest.id == request_id).with_for_update()
        result = await session.execute(stmt)
        charge_req = result.scalar_one_or_none()

        if not charge_req:
            await bot.answer_callback_query(call.id, "❌ درخواست یافت نشد.", show_alert=True)
            return

        if not charge_req.is_pending:
            await bot.answer_callback_query(call.id, "⚠️ قبلاً پردازش شده است.", show_alert=True)
            await _update_admin_message_status(call, "⚠️ قبلاً پردازش شده")
            return

        user_id = charge_req.user_id
        amount = charge_req.amount
        user_message_id = charge_req.message_id
        
        user = await session.get(User, user_id)
        if not user: return
        lang_code = user.lang_code or 'fa'

        try:
            if decision == 'confirm':
                # --- تایید شارژ ---
                success = await db.update_wallet_balance(
                    user_id, amount, 'deposit', 
                    f"شارژ توسط مدیریت (درخواست #{request_id})",
                    session=session
                )
                
                if success:
                    charge_req.is_pending = False
                    await session.commit()
                    
                    amount_str = f"{amount:,.0f}"
                    success_text = (
                        f"✅ حساب شما به مبلغ *{amount_str} تومان* شارژ شد\\.\n\n"
                        f"هم‌اکنون می‌توانید سرویس مورد نظر را خریداری کنید\\."
                    )
                    
                    # ✅ نمایش منوی کامل شامل دکمه "مشاهده سرویس‌ها"
                    try:
                        post_charge_kb = await user_menu.post_charge_menu(lang_code)
                        await _safe_edit(user_id, user_message_id, success_text, reply_markup=post_charge_kb)
                    except Exception:
                        try:
                            post_charge_kb = await user_menu.post_charge_menu(lang_code)
                            await bot.send_message(user_id, success_text, reply_markup=post_charge_kb, parse_mode="MarkdownV2")
                        except: pass
                    
                    await bot.answer_callback_query(call.id, "✅ تایید شد.", show_alert=False)
                    await _update_admin_message_status(call, f"✅ تایید شد توسط {call.from_user.first_name}")
                else:
                    await session.rollback()
                    await bot.answer_callback_query(call.id, "❌ خطا در دیتابیس.", show_alert=True)

            elif decision == 'reject':
                # --- رد درخواست ---
                charge_req.is_pending = False
                await session.commit()
                
                # ✅ دریافت آیدی پشتیبانی از تنظیمات
                support_id = await db.get_config('support_id')
                
                reject_text = (
                    "❌ درخواست شارژ حساب شما توسط ادمین رد شد.\n"
                    "لطفاً در صورت اشتباه با پشتیبانی تماس بگیرید."
                )
                
                # ساخت کیبورد اختصاصی
                kb = types.InlineKeyboardMarkup()
                
                # اگر آیدی پشتیبانی تنظیم شده باشد، دکمه نمایش داده می‌شود
                if support_id:
                    clean_id = support_id.replace('@', '').strip()
                    kb.add(types.InlineKeyboardButton("📞 تماس با پشتیبانی", url=f"https://t.me/{clean_id}"))
                
                kb.add(types.InlineKeyboardButton("✖️ بازگشت به کیف پول", callback_data="wallet:main"))

                try:
                    await _safe_edit(user_id, user_message_id, reject_text, reply_markup=kb)
                except:
                    try:
                        await bot.send_message(user_id, reject_text, reply_markup=kb)
                    except: pass

                await bot.answer_callback_query(call.id, "❌ رد شد.", show_alert=False)
                await _update_admin_message_status(call, f"❌ رد شد توسط {call.from_user.first_name}")
                
        except Exception as e:
            logger.error(f"Error handling charge request {request_id}: {e}", exc_info=True)
            await session.rollback()
            await bot.answer_callback_query(call.id, "خطای سیستمی.", show_alert=False)

async def _update_admin_message_status(call: types.CallbackQuery, status_text: str):
    """آپدیت کپشن پیام ادمین و حذف دکمه‌ها"""
    try:
        original_caption = call.message.caption or ""
        new_caption = f"{original_caption}\n\n──────────────\n{status_text}"
        await bot.edit_message_caption(
            caption=new_caption,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.warning(f"Failed to update admin message: {e}")

# --- شارژ دستی و برداشت (بدون تغییر نسبت به قبل) ---

async def handle_manual_charge_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    context = "search" if len(params) > 1 and params[1] == 'search' else None
    
    prompt = "💰 لطفاً مبلغ مورد نظر برای *شارژ دستی* کیف پول کاربر را به تومان وارد کنید:"
    
    admin_conversations[uid] = {
        'action_type': 'manual_charge',
        'msg_id': msg_id,
        'identifier': identifier,
        'context': context,
        'next_handler': _get_manual_charge_amount
    }
    
    back_cb = f"admin:user_details:{identifier}" if identifier.isdigit() else "admin:user_manage"
    await _safe_edit(uid, msg_id, prompt, reply_markup=await admin_menu.cancel_action(back_cb))

async def _get_manual_charge_amount(message: types.Message):
    admin_id, text = message.from_user.id, message.text.strip()
    try: await bot.delete_message(admin_id, message.message_id)
    except: pass

    if admin_id not in admin_conversations: return
    convo = admin_conversations[admin_id]
    
    try:
        amount = float(text)
        convo['amount'] = amount
        async with db.get_session() as session:
            identifier = convo['identifier']
            user = None
            if identifier.isdigit():
                user = await session.get(User, int(identifier))
            if not user:
                from bot.db.base import UserUUID
                stmt = select(User).outerjoin(UserUUID).where((User.username == identifier) | (UserUUID.uuid == identifier)).limit(1)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
            
            if not user:
                await _safe_edit(admin_id, convo['msg_id'], "❌ کاربر یافت نشد.", reply_markup=await admin_menu.main())
                return

            convo['target_user_id'] = user.user_id
            user_name = user.first_name or user.username or "کاربر"
        
        confirm_prompt = (f"❓ آیا از شارژ کیف پول کاربر *{escape_markdown(user_name)}* \\(`{user.user_id}`\\) "
                          f"به مبلغ *{amount:,.0f} تومان* اطمینان دارید؟")
        
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ بله، تایید", callback_data="admin:manual_charge_exec"),
            types.InlineKeyboardButton("❌ خیر، لغو", callback_data="admin:manual_charge_cancel")
        )
        await _safe_edit(admin_id, convo['msg_id'], confirm_prompt, reply_markup=kb)

    except ValueError:
        back_cb = f"admin:user_details:{convo['identifier']}" if convo['identifier'].isdigit() else "admin:user_manage"
        await _safe_edit(admin_id, convo['msg_id'], "❌ مقدار نامعتبر.", reply_markup=await admin_menu.cancel_action(back_cb))
    except Exception as e:
        logger.error(f"Manual charge error: {e}")
        await _safe_edit(admin_id, convo['msg_id'], "❌ خطا.", reply_markup=await admin_menu.main())

async def handle_manual_charge_execution(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id, {})
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    amount = convo.get('amount')

    if not all([msg_id, target_user_id, amount]): return
        
    if await db.update_wallet_balance(target_user_id, amount, 'deposit', "شارژ دستی توسط مدیریت"):
        success_msg = f"✅ کیف پول کاربر با موفقیت به مبلغ *{amount:,.0f} تومان* شارژ شد\\."
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت به پروفایل کاربر", callback_data=f"admin:us:{target_user_id}"))
        await _safe_edit(admin_id, msg_id, success_msg, reply_markup=kb)
        try:
            user_notification = f"✅ حساب شما به مبلغ *{amount:,.0f} تومان* توسط مدیریت شارژ شد\\."
            await bot.send_message(target_user_id, user_notification, parse_mode="MarkdownV2")
        except: pass
    else:
        await _safe_edit(admin_id, msg_id, "❌ خطا در ثبت تراکنش.", reply_markup=await admin_menu.main())

async def handle_manual_charge_cancel(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    convo = admin_conversations.pop(admin_id)
    back_target = f"admin:us:{convo.get('target_user_id')}" if convo.get('target_user_id') else "admin:management_menu"
    await _safe_edit(admin_id, convo.get('msg_id'), "❌ عملیات لغو شد.", reply_markup=await admin_menu.cancel_action(back_target))

async def handle_manual_withdraw_request(call: types.CallbackQuery, params: list):
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0]
    try: user_id = int(identifier)
    except: return

    async with db.get_session() as session:
        user = await session.get(User, user_id)
        if not user: return
        balance = user.wallet_balance or 0.0

    if balance <= 0:
        await bot.answer_callback_query(call.id, "موجودی صفر/منفی است.", show_alert=True)
        return

    admin_conversations[uid] = {
        'action_type': 'manual_withdraw',
        'msg_id': msg_id,
        'target_user_id': user_id,
        'current_balance': balance
    }
    
    safe_name = escape_markdown(user.first_name or 'User')
    prompt = (f"موجودی فعلی کاربر *{safe_name}* مبلغ *{balance:,.0f} تومان* است\\.\n\n"
              f"آیا از صفر کردن موجودی \\(برداشت کل مبلغ\\) اطمینان دارید؟")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ بله، صفر کن", callback_data="admin:manual_withdraw_exec"),
        types.InlineKeyboardButton("❌ خیر", callback_data="admin:manual_withdraw_cancel")
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_manual_withdraw_execution(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id, {})
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    amount_to_withdraw = convo.get('current_balance', 0.0)

    if not all([msg_id, target_user_id]): return
    
    if await db.update_wallet_balance(target_user_id, -amount_to_withdraw, 'withdraw', "برداشت/صفر کردن توسط مدیریت"):
        success_msg = escape_markdown(f"✅ موجودی کاربر صفر شد. (برداشت {amount_to_withdraw:,.0f} تومان)")
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت به پروفایل کاربر", callback_data=f"admin:us:{target_user_id}"))
        await _safe_edit(admin_id, msg_id, success_msg, reply_markup=kb)
        try:
            user_msg = f"✅ مبلغ {amount_to_withdraw:,.0f} تومان از کیف پول شما کسر و موجودی صفر شد."
            await bot.send_message(target_user_id, escape_markdown(user_msg), parse_mode="MarkdownV2")
        except: pass
    else:
        await _safe_edit(admin_id, msg_id, "❌ خطا.", reply_markup=await admin_menu.main())

async def handle_manual_withdraw_cancel(call: types.CallbackQuery, params: list):
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    convo = admin_conversations.pop(admin_id)
    back_target = f"admin:us:{convo.get('target_user_id')}" if convo.get('target_user_id') else "admin:management_menu"
    await _safe_edit(admin_id, convo.get('msg_id'), "❌ لغو شد.", reply_markup=await admin_menu.cancel_action(back_target))