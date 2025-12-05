import logging
from telebot import types
from sqlalchemy import select, update, and_
from bot.bot_instance import bot
from bot.database import db
from bot.db.base import User, UserUUID, ChargeRequest
from bot.utils import escape_markdown, _safe_edit
from bot.keyboards import admin

logger = logging.getLogger(__name__)
bot, admin_conversations = None, None

def initialize_wallet_handlers(b, conv_dict):
    """مقادیر bot و admin_conversations را از فایل اصلی دریافت می‌کند."""
    global bot, admin_conversations
    bot = b
    admin_conversations = conv_dict

async def handle_charge_request_callback(call: types.CallbackQuery, params: list):
    """پاسخ ادمین به درخواست شارژ را مدیریت می‌کند."""
    admin_id = call.from_user.id
    original_caption = call.message.caption or ""
    
    action_parts = call.data.split(':')
    decision = action_parts[1] # charge_confirm or charge_reject
    request_id = int(action_parts[2])

    async with db.get_session() as session:
        # دریافت درخواست شارژ
        stmt = select(ChargeRequest).where(ChargeRequest.id == request_id)
        result = await session.execute(stmt)
        charge_req = result.scalar_one_or_none()

        if not charge_req or not charge_req.is_pending:
            await bot.answer_callback_query(call.id, "این درخواست قبلاً پردازش شده است.", show_alert=True)
            try:
                await bot.edit_message_caption(
                    caption=f"{original_caption}\n\n⚠️ این درخواست قبلا پردازش شده است.",
                    chat_id=admin_id,
                    message_id=call.message.message_id
                )
            except:
                pass
            return

        user_id = charge_req.user_id
        amount = charge_req.amount
        user_message_id = charge_req.message_id
        
        # دریافت زبان کاربر (پیش‌فرض فارسی)
        user = await session.get(User, user_id)
        lang_code = user.lang_code if user else 'fa'

        try:
            if decision == 'charge_confirm':
                # استفاده از متد WalletDB برای آپدیت موجودی و ثبت تراکنش
                success = await db.update_wallet_balance(
                    user_id, amount, 'deposit', 
                    f"شارژ توسط مدیریت (درخواست #{request_id})",
                    session=session # پاس دادن سشن برای اتمیک بودن
                )
                
                if success:
                    # آپدیت وضعیت درخواست
                    charge_req.is_pending = False
                    await session.commit()
                    
                    amount_str = f"{amount:,.0f}"
                    success_text = (
                        f"✅ حساب شما به مبلغ *{amount_str} تومان* با موفقیت شارژ شد\\.\n\n"
                        f"حالا می‌توانید سرویس مورد نظر خود را از بخش «سرویس‌ها» خریداری یا تمدید کنید\\."
                    )
                    
                    # اطلاع به کاربر
                    await _safe_edit(user_id, user_message_id, success_text, reply_markup=admin.post_charge_menu(lang_code))
                    
                    # آپدیت پیام ادمین
                    await bot.edit_message_caption(
                        caption=f"{original_caption}\n\n✅ تایید شد توسط شما.",
                        chat_id=admin_id, 
                        message_id=call.message.message_id
                    )
                    await bot.answer_callback_query(call.id, "شارژ حساب کاربر تایید شد.", show_alert=True)
                else:
                    await bot.answer_callback_query(call.id, "❌ خطا در عملیات دیتابیس.", show_alert=True)

            elif decision == 'charge_reject':
                charge_req.is_pending = False
                await session.commit()
                
                reject_text = "❌ درخواست شارژ حساب شما توسط ادمین رد شد. لطفاً با پشتیبانی تماس بگیرید."
                await _safe_edit(user_id, user_message_id, escape_markdown(reject_text), reply_markup=admin.user_cancel_action("wallet:main", lang_code))

                await bot.edit_message_caption(
                    caption=f"{original_caption}\n\n❌ توسط شما رد شد.",
                    chat_id=admin_id,
                    message_id=call.message.message_id
                )
                await bot.answer_callback_query(call.id, "درخواست شارژ کاربر رد شد.", show_alert=True)
                
        except Exception as e:
            logger.error(f"Error handling charge request {request_id}: {e}")
            await bot.answer_callback_query(call.id, "خطای سیستمی رخ داد.", show_alert=False)

# --- شارژ دستی (Manual Charge) ---

async def handle_manual_charge_request(call: types.CallbackQuery, params: list):
    """شروع فرآیند شارژ دستی کیف پول توسط ادمین."""
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0] # UUID یا username یا UserID
    context = "search" if len(params) > 1 and params[1] == 'search' else None
    
    prompt = "لطفاً مبلغ مورد نظر برای شارژ دستی کیف پول کاربر را به تومان وارد کنید:"
    admin_conversations[uid] = {
        'action_type': 'manual_charge',
        'msg_id': msg_id,
        'identifier': identifier,
        'context': context
    }
    
    # دکمه بازگشت هوشمند
    back_cb = f"admin:user_details:{identifier}" if identifier.isdigit() else "admin:user_manage"
    
    await _safe_edit(uid, msg_id, prompt, reply_markup=admin.admin_cancel_action(back_cb))
    bot.register_next_step_handler(call.message, _get_manual_charge_amount)

async def _get_manual_charge_amount(message: types.Message):
    """مبلغ شارژ دستی را دریافت و تاییدیه می‌گیرد."""
    admin_id, text = message.from_user.id, message.text.strip()
    try:
        await bot.delete_message(admin_id, message.message_id)
    except: pass

    if admin_id not in admin_conversations: return
    
    convo = admin_conversations[admin_id]
    msg_id = convo['msg_id']
    identifier = convo['identifier']
    
    try:
        amount = float(text)
        convo['amount'] = amount
        
        # پیدا کردن کاربر از دیتابیس
        async with db.get_session() as session:
            user = None
            if identifier.isdigit():
                user = await session.get(User, int(identifier))
            
            if not user:
                # جستجو با یوزرنیم یا UUID
                stmt = select(User).outerjoin(UserUUID).where(
                    (User.username == identifier) | (UserUUID.uuid == identifier)
                ).limit(1)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
            
            if not user:
                await _safe_edit(admin_id, msg_id, "❌ کاربر یافت نشد.", reply_markup=admin.admin_panel())
                return

            convo['target_user_id'] = user.user_id
            user_name = user.first_name or user.username or "کاربر"
        
        confirm_prompt = (f"آیا از شارژ کیف پول کاربر *{escape_markdown(user_name)}* \\(`{user.user_id}`\\) "
                          f"به مبلغ *{amount:,.0f} تومان* اطمینان دارید؟")
        
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ بله، تایید", callback_data="admin:manual_charge_exec"),
            types.InlineKeyboardButton("❌ خیر، لغو", callback_data="admin:manual_charge_cancel")
        )
        await _safe_edit(admin_id, msg_id, confirm_prompt, reply_markup=kb)

    except ValueError:
        await _safe_edit(admin_id, msg_id, "❌ مقدار نامعتبر. فقط عدد وارد کنید.", reply_markup=admin.admin_panel())
    except Exception as e:
        logger.error(f"Manual charge error: {e}")
        await _safe_edit(admin_id, msg_id, "❌ خطای سیستمی.", reply_markup=admin.admin_panel())

async def handle_manual_charge_execution(call: types.CallbackQuery, params: list):
    """شارژ دستی را نهایی می‌کند."""
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id, {})
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    amount = convo.get('amount')

    if not all([msg_id, target_user_id, amount]):
        return
        
    if await db.update_wallet_balance(target_user_id, amount, 'deposit', "شارژ دستی توسط مدیریت"):
        
        success_msg = f"✅ کیف پول کاربر با موفقیت به مبلغ *{amount:,.0f} تومان* شارژ شد\\."
        # دکمه بازگشت به جزئیات کاربر
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت به پروفایل کاربر", callback_data=f"admin:user_details:{target_user_id}"))
        
        await _safe_edit(admin_id, msg_id, success_msg, reply_markup=kb)
        
        try:
            user_notification = f"✅ حساب شما به مبلغ *{amount:,.0f} تومان* توسط مدیریت شارژ شد\\."
            await bot.send_message(target_user_id, user_notification, parse_mode="MarkdownV2")
        except:
            pass
    else:
        await _safe_edit(admin_id, msg_id, "❌ خطا در ثبت تراکنش.", reply_markup=admin.admin_panel())

async def handle_manual_charge_cancel(call: types.CallbackQuery, params: list):
    """لغو عملیات شارژ دستی."""
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id)
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    
    await _safe_edit(admin_id, msg_id, "❌ عملیات لغو شد.", 
                     reply_markup=admin.admin_back_btn(f"admin:user_details:{target_user_id}" if target_user_id else "admin:user_manage"))

# --- برداشت دستی / صفر کردن موجودی (Manual Withdraw) ---

async def handle_manual_withdraw_request(call: types.CallbackQuery, params: list):
    """شروع فرآیند برداشت وجه / صفر کردن موجودی."""
    uid, msg_id = call.from_user.id, call.message.message_id
    identifier = params[0] # UserID
    
    try:
        user_id = int(identifier)
    except:
        await bot.answer_callback_query(call.id, "ID نامعتبر است.", show_alert=True)
        return

    async with db.get_session() as session:
        user = await session.get(User, user_id)
        if not user:
            await bot.answer_callback_query(call.id, "کاربر یافت نشد.", show_alert=True)
            return
        
        balance = user.wallet_balance or 0.0

    if balance <= 0:
        await bot.answer_callback_query(call.id, "موجودی کاربر صفر یا منفی است.", show_alert=True)
        return

    admin_conversations[uid] = {
        'action_type': 'manual_withdraw',
        'msg_id': msg_id,
        'target_user_id': user_id,
        'current_balance': balance
    }
    
    prompt = (f"موجودی فعلی کاربر *{escape_markdown(user.first_name or 'User')}* مبلغ *{balance:,.0f} تومان* است\\.\n\n"
              f"آیا از صفر کردن موجودی (برداشت کل مبلغ) اطمینان دارید؟")

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ بله، صفر کن", callback_data="admin:manual_withdraw_exec"),
        types.InlineKeyboardButton("❌ خیر", callback_data="admin:manual_withdraw_cancel")
    )
    await _safe_edit(uid, msg_id, prompt, reply_markup=kb)

async def handle_manual_withdraw_execution(call: types.CallbackQuery, params: list):
    """برداشت وجه را نهایی می‌کند."""
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id, {})
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    amount_to_withdraw = convo.get('current_balance', 0.0)

    if not all([msg_id, target_user_id]):
        return
    
    # برای صفر کردن، به اندازه موجودی فعلی، برداشت می‌زنیم (مقدار منفی)
    if await db.update_wallet_balance(target_user_id, -amount_to_withdraw, 'withdraw', "برداشت/صفر کردن توسط مدیریت"):
        
        success_msg = escape_markdown(f"✅ موجودی کاربر صفر شد. (برداشت {amount_to_withdraw:,.0f} تومان)")
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("👤 بازگشت به پروفایل کاربر", callback_data=f"admin:user_details:{target_user_id}"))
        
        await _safe_edit(admin_id, msg_id, success_msg, reply_markup=kb)
        
        try:
            user_msg = f"✅ مبلغ {amount_to_withdraw:,.0f} تومان از کیف پول شما کسر و موجودی صفر شد."
            await bot.send_message(target_user_id, escape_markdown(user_msg), parse_mode="MarkdownV2")
        except:
            pass
    else:
        await _safe_edit(admin_id, msg_id, "❌ خطا در عملیات.", reply_markup=admin.admin_panel())

async def handle_manual_withdraw_cancel(call: types.CallbackQuery, params: list):
    """لغو عملیات برداشت."""
    admin_id = call.from_user.id
    if admin_id not in admin_conversations: return
    
    convo = admin_conversations.pop(admin_id)
    msg_id = convo.get('msg_id')
    target_user_id = convo.get('target_user_id')
    
    await _safe_edit(admin_id, msg_id, "❌ عملیات لغو شد.", 
                     reply_markup=admin.admin_back_btn(f"admin:user_details:{target_user_id}"))